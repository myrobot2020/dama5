import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PLAIN_QUERY = "lang=en&layout=plain&reference=none&notes=asterisk&highlight=false&script=latin"

TARGET_SUTTA_IDS = [
    "2.3.9",
    "2.4.1",
    "2.4.2",
    "2.11.2",
    "2.11.8",
    "2.11.9",
]

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


def build_sc_url(uid: str) -> str:
    uid = uid.strip().lower()
    return f"https://suttacentral.net/{urllib.parse.quote(uid)}/en/sujato?{PLAIN_QUERY}"


def clean_sutta_for_query(sutta: str) -> str:
    s = (sutta or "").strip()
    s = re.sub(r"^\s*\d+(?:\.\d+)+\s*", "", s).strip()
    return s


def keywords_query(text: str, *, max_terms: int = 10) -> str:
    ws = re.findall(r"[A-Za-z']+", (text or "").lower())
    terms = [w for w in ws if len(w) >= 4 and w not in STOPWORDS]
    seen = set()
    out: List[str] = []
    for t in terms:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= max_terms:
            break
    return " ".join(out)


def sc_instant_search(query: str) -> List[Dict[str, Any]]:
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
            "User-Agent": "dama5-sc-resolver/1.0 (+local script)",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        payload = resp.read().decode("utf-8", errors="replace")
    obj = json.loads(payload)
    hits = obj.get("hits") if isinstance(obj, dict) else None
    return hits if isinstance(hits, list) else []


def pick_an2_uid(hits: List[Dict[str, Any]]) -> Optional[str]:
    for h in hits:
        if not isinstance(h, dict):
            continue
        uid = str(h.get("uid") or "").strip().lower()
        if uid.startswith("an2."):
            return uid
    return None


def resolve_uid(entry: Dict[str, Any]) -> Tuple[Optional[str], str]:
    sutta_id = str(entry.get("sutta_id") or "").strip()
    sutta = clean_sutta_for_query(str(entry.get("sutta") or ""))

    chain = entry.get("chain") if isinstance(entry.get("chain"), dict) else {}
    items = chain.get("items") if isinstance(chain, dict) else []
    items = items if isinstance(items, list) else []

    # Try 1: keywords from sutta
    q1 = keywords_query(sutta, max_terms=10)
    if q1:
        uid = pick_an2_uid(sc_instant_search(q1))
        if uid:
            return uid, f"search:sutta_keywords:{q1}"

    # Try 2: chain items
    if items:
        q2 = " ".join(str(x) for x in items[:6] if x).strip()
        if q2:
            uid = pick_an2_uid(sc_instant_search(q2))
            if uid:
                return uid, f"search:chain_items:{q2}"

    # Try 3: literal AN token (sometimes works)
    q3 = f"AN {sutta_id}"
    uid = pick_an2_uid(sc_instant_search(q3))
    if uid:
        return uid, f"search:an_id:{q3}"

    return None, "unresolved"


def main() -> None:
    # Import fetcher from existing script (keeps behavior consistent)
    from backfill_sc_sutta_an2 import fetch_sc_translation

    path = Path("an2.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise TypeError("Expected top-level list in an2.json")

    updated: List[str] = []
    failed: List[str] = []

    for entry in data:
        if not isinstance(entry, dict):
            continue
        sid = str(entry.get("sutta_id") or "").strip()
        if sid not in TARGET_SUTTA_IDS:
            continue

        old_uid = str(entry.get("sc_id") or "").strip()
        try:
            uid, reason = resolve_uid(entry)
        except Exception as e:
            failed.append(f"{sid}: resolver_error:{type(e).__name__}:{e}")
            continue
        if not uid:
            failed.append(f"{sid}: {reason}")
            continue

        # Update sc_id/url and refresh sc_sutta
        entry["sc_id"] = uid
        entry["sc_url"] = build_sc_url(uid)
        try:
            txt = fetch_sc_translation(uid, "sujato", timeout_s=12)
        except Exception as e:
            failed.append(f"{sid}: fetch_error:{type(e).__name__}:{e}")
            continue
        if not str(txt).strip():
            failed.append(f"{sid}: empty_extract:{uid}")
            continue
        entry["sc_sutta"] = txt
        updated.append(f"{sid}: {old_uid} -> {uid} ({reason})")

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    rep = Path("resolve_sc_selected_an2.report.txt")
    lines = [
        f"updated={len(updated)}",
        f"failed={len(failed)}",
        "",
        "## updated",
        *updated,
        "",
        "## failed",
        *failed,
        "",
    ]
    rep.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

