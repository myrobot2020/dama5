import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PLAIN_QUERY = "lang=en&layout=plain&reference=none&notes=asterisk&highlight=false&script=latin"

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "but",
    "by",
    "do",
    "does",
    "for",
    "from",
    "have",
    "he",
    "her",
    "here",
    "him",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "may",
    "monk",
    "monks",
    "not",
    "of",
    "on",
    "or",
    "our",
    "should",
    "so",
    "that",
    "the",
    "their",
    "there",
    "these",
    "they",
    "this",
    "those",
    "to",
    "two",
    "unto",
    "up",
    "was",
    "we",
    "what",
    "when",
    "who",
    "will",
    "with",
    "you",
    "your",
}


def _http_get(url: str, *, timeout_s: int = 20) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "dama5-sc-linker/1.0 (+local script)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        body = resp.read()
    # SuttaCentral pages are UTF-8.
    return body.decode("utf-8", errors="replace")


def _first_n_words(text: str, n: int) -> str:
    words = re.findall(r"[A-Za-z']+", text)
    return " ".join(words[:n])


def _clean_sutta_for_query(sutta: str) -> str:
    # Strip leading internal numbering like "2.1.3" or "2.11.9"
    s = sutta.strip()
    s = re.sub(r"^\s*\d+(?:\.\d+)+\s*", "", s)
    return s.strip()


def _extract_first_uid_from_search_html(html: str) -> Optional[str]:
    """
    Extract the first UID (e.g. an2.2) from SuttaCentral search HTML.
    We look for href="/<uid>" patterns and take the earliest plausible match.
    """
    # Common link pattern in results: href="/an2.2" or href="/an2.2/en/sujato"
    # We'll prefer the plain UID if present.
    m = re.search(r'href="/(an\d+\.\d+)(?:/[^"]*)?"', html, flags=re.IGNORECASE)
    if m:
        return m.group(1).lower()
    return None


def _build_sc_url(uid: str) -> str:
    uid = uid.strip().lower()
    return f"https://suttacentral.net/{urllib.parse.quote(uid)}/en/sujato?{PLAIN_QUERY}"


def _search_sc_for_uid(query: str) -> Optional[str]:
    """
    Use SuttaCentral instant search API (HTML search is a JS shell).
    Returns the best matching an2.* uid if available.
    """
    params = {
        "limit": "10",
        "query": query,
        "language": "en",
        "restrict": "all",
        "matchpartial": "true",
    }
    url = "https://suttacentral.net/api/search/instant?" + urllib.parse.urlencode(params)
    body = json.dumps(["en"]).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "dama5-sc-linker/1.0 (+local script)",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        payload = resp.read().decode("utf-8", errors="replace")
    obj = json.loads(payload)
    hits = obj.get("hits") if isinstance(obj, dict) else None
    hits = hits if isinstance(hits, list) else []

    # Prefer AN2 hits
    for h in hits:
        if not isinstance(h, dict):
            continue
        uid = str(h.get("uid") or "").strip().lower()
        if uid.startswith("an2."):
            return uid
    return None


def _try_resolve_uid(entry: Dict[str, Any]) -> Tuple[Optional[str], str]:
    """
    At most 2 tries per entry.
    Returns (uid, reason).
    """
    sutta_id = str(entry.get("sutta_id") or "").strip()
    sutta = str(entry.get("sutta") or "").strip()
    chain = entry.get("chain") if isinstance(entry.get("chain"), dict) else {}
    chain_items = chain.get("items") if isinstance(chain, dict) else None
    chain_items = chain_items if isinstance(chain_items, list) else []

    def keywords_query(text: str, *, max_terms: int = 10) -> str:
        ws = re.findall(r"[A-Za-z']+", text.lower())
        terms = [w for w in ws if len(w) >= 4 and w not in STOPWORDS]
        # keep order, de-dupe
        seen = set()
        out = []
        for t in terms:
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
            if len(out) >= max_terms:
                break
        return " ".join(out)

    # Try 1: deterministic mapping from internal sutta_id to AN2 numbering.
    # Convention assumed: "2.<vagga>.<sutta>" -> an2.<(vagga-1)*10 + sutta>
    try:
        parts = [int(p) for p in sutta_id.split(".") if p.strip().isdigit()]
        if len(parts) >= 3 and parts[0] == 2:
            vagga = parts[1]
            sutta_n = parts[2]
            if vagga >= 1 and sutta_n >= 1:
                sc_n = (vagga - 1) * 10 + sutta_n
                if sc_n >= 1:
                    return f"an2.{sc_n}", "guess: sutta_id_vagga_x10_plus_n"
    except Exception:
        pass

    # Try 2: keyword query from sutta text (best-effort, may fail for paraphrases)
    cleaned = _clean_sutta_for_query(sutta)
    q1 = keywords_query(cleaned, max_terms=10)
    if q1:
        try:
            uid = _search_sc_for_uid(q1)
        except Exception:
            uid = None
        if uid:
            return uid, "search: sutta_keywords"

    # Fallback (still within the 2-tries spirit): use chain items if present, otherwise sutta_id token
    if chain_items:
        q2 = " ".join(str(x) for x in chain_items[:4] if x)
    else:
        # e.g. "AN 2.1.3" or just the id
        q2 = f"AN {sutta_id}" if sutta_id else ""
    q2 = q2.strip()
    if q2:
        try:
            uid = _search_sc_for_uid(q2)
        except Exception:
            uid = None
        if uid:
            return uid, "search: chain_or_id_fallback"

    return None, "unresolved"


def main() -> None:
    path = Path("an2.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise TypeError("Expected top-level list in an2.json")

    updated = 0
    unresolved: List[str] = []
    errors: List[str] = []

    for entry in data:
        if not isinstance(entry, dict):
            continue

        # Skip if already populated
        sc_id = str(entry.get("sc_id") or "").strip()
        if sc_id:
            if not str(entry.get("sc_url") or "").strip():
                entry["sc_url"] = _build_sc_url(sc_id)
                updated += 1
            continue

        try:
            uid, reason = _try_resolve_uid(entry)
        except Exception as e:
            uid, reason = None, "error"
            errors.append(f'{entry.get("sutta_id")}: {type(e).__name__}: {e}')
        if uid:
            entry["sc_id"] = uid
            entry["sc_url"] = _build_sc_url(uid)
            entry.setdefault("alignment", {})
            updated += 1
        else:
            unresolved.append(f'{entry.get("sutta_id")}: {reason}')

        # Keep it quick; hard cap is 2 tries/entry already.
        time.sleep(0.05)

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Reorder keys for readability if helper exists.
    reorder = Path("reorder_an2.py")
    if reorder.exists():
        import runpy

        runpy.run_path(str(reorder), run_name="__main__")

    # Emit a small report file
    report_path = Path("backfill_sc_links_an2.report.txt")
    report_lines = [f"updated_entries={updated}", f"unresolved_entries={len(unresolved)}", ""]
    report_lines.extend(unresolved)
    if errors:
        report_lines.extend(["", f"errors={len(errors)}", ""])
        report_lines.extend(errors)
    report_path.write_text("\n".join(report_lines), encoding="utf-8")


if __name__ == "__main__":
    main()

