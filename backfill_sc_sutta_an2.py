import json
import re
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class MainTextExtractor(HTMLParser):
    """
    Extract visible text primarily from the <main> region.
    Falls back to collecting from <body> if <main> never appears.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_main = False
        self._in_body = False
        self._skip_depth = 0  # for script/style/noscript
        self._saw_main = False
        self._chunks_main: List[str] = []
        self._chunks_body: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        t = tag.lower()
        if t == "main":
            self._in_main = True
            self._saw_main = True
        elif t == "body":
            self._in_body = True
        elif t in ("script", "style", "noscript"):
            self._skip_depth += 1

        # Add paragraph-ish breaks to preserve readability
        if self._skip_depth == 0 and (self._in_main or self._in_body):
            if t in ("p", "br", "div", "section", "article", "h1", "h2", "h3", "li"):
                self._emit("\n")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t == "main":
            self._in_main = False
        elif t == "body":
            self._in_body = False
        elif t in ("script", "style", "noscript"):
            self._skip_depth = max(0, self._skip_depth - 1)

        if self._skip_depth == 0 and (self._in_main or self._in_body):
            if t in ("p", "div", "section", "article", "li"):
                self._emit("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if not (self._in_main or self._in_body):
            return
        self._emit(data)

    def _emit(self, s: str) -> None:
        if self._in_main:
            self._chunks_main.append(s)
        elif self._in_body:
            self._chunks_body.append(s)

    def get_text(self) -> str:
        raw = "".join(self._chunks_main if self._saw_main else self._chunks_body)
        # Collapse whitespace, keep paragraph breaks
        raw = raw.replace("\r\n", "\n").replace("\r", "\n")
        # Trim each line, drop empty noise
        lines = [ln.strip() for ln in raw.split("\n")]
        # Remove empty lines but keep paragraph breaks by re-inserting single blanks
        out_lines: List[str] = []
        blank = False
        for ln in lines:
            if not ln:
                blank = True
                continue
            if blank and out_lines:
                out_lines.append("")
            blank = False
            out_lines.append(ln)
        txt = "\n".join(out_lines).strip()
        # Remove common UI crumbs
        txt = re.sub(r"\bSuttaCentral\b", "", txt).strip()
        return txt


BAD_MARKERS = [
    "unsupported browser",
    "ie will not be supported",
]


def _looks_bad(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return True
    return any(m in t for m in BAD_MARKERS)


def http_get(url: str, *, timeout_s: int = 12) -> str:
    req = urllib.request.Request(
        url,
        headers={
            # Use a mainstream UA; SC sometimes serves fallback messaging to non-browser UAs.
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        body = resp.read()
    return body.decode("utf-8", errors="replace")


def extract_main_text(html: str) -> str:
    p = MainTextExtractor()
    p.feed(html)
    return p.get_text()

class _StripTags(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        t = tag.lower()
        if t in ("script", "style", "noscript"):
            self._skip += 1
        if not self._skip and t in ("p", "br", "div", "section", "article", "h1", "h2", "h3", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("script", "style", "noscript"):
            self._skip = max(0, self._skip - 1)
        if not self._skip and t in ("p", "div", "section", "article", "li"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts).replace("\r\n", "\n").replace("\r", "\n")
        lines = [ln.strip() for ln in raw.split("\n")]
        out: List[str] = []
        blank = False
        for ln in lines:
            if not ln:
                blank = True
                continue
            if blank and out:
                out.append("")
            blank = False
            out.append(ln)
        return "\n".join(out).strip()


def strip_html(html: str) -> str:
    p = _StripTags()
    p.feed(html)
    return p.text()


def fetch_sc_translation(uid: str, translator: str = "sujato", *, timeout_s: int = 12) -> str:
    """
    Prefer extractsutta API (handles baked ranges); fall back to bilarasuttas.
    Returns plain text (joined translation segments).
    """
    uid = uid.strip().lower()
    translator = translator.strip().lower()

    def _get_json(url: str) -> Dict[str, Any]:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
        obj = json.loads(payload)
        if not isinstance(obj, dict):
            raise TypeError("Unexpected API response")
        return obj

    # 1) extractsutta
    url1 = f"https://suttacentral.net/api/extractsutta/{urllib.parse.quote(uid)}/{urllib.parse.quote(translator)}"
    obj = _get_json(url1)
    keys = obj.get("keys_order")
    trans = obj.get("translation_text")
    if isinstance(keys, list) and isinstance(trans, dict):
        parts = [str(trans.get(k) or "") for k in keys]
        joined = "".join(parts).strip()
        if joined:
            return joined

    # 2) bilarasuttas (fallback)
    url2 = f"https://suttacentral.net/api/bilarasuttas/{urllib.parse.quote(uid)}/{urllib.parse.quote(translator)}"
    obj = _get_json(url2)
    keys = obj.get("keys_order")
    trans = obj.get("translation_text")
    if isinstance(keys, list) and isinstance(trans, dict):
        parts = [str(trans.get(k) or "") for k in keys]
        joined = "".join(parts).strip()
        if joined:
            return joined

    # 3) last resort: try html_text wrapper (some responses omit translation_text)
    keys = obj.get("keys_order")
    html_text = obj.get("html_text")
    if isinstance(keys, list) and isinstance(html_text, dict):
        # Put empty placeholders in the html wrapper; we still get the text content from wrappers.
        html = "\n".join(str(html_text.get(k) or "") for k in keys)
        txt = strip_html(html)
        if txt:
            return txt

    return ""

def main() -> None:
    path = Path("an2.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise TypeError("Expected top-level list in an2.json")

    updated = 0
    skipped = 0
    failed: List[str] = []

    for entry in data:
        if not isinstance(entry, dict):
            continue
        sc_url = str(entry.get("sc_url") or "").strip()
        if not sc_url:
            failed.append(f'{entry.get("sutta_id")}: missing sc_url')
            continue

        cur = str(entry.get("sc_sutta") or "")
        # Skip good existing sc_sutta; overwrite only if empty or clearly bad.
        if cur.strip() and not _looks_bad(cur):
            skipped += 1
            continue

        try:
            uid = str(entry.get("sc_id") or "").strip()
            if not uid:
                failed.append(f'{entry.get("sutta_id")}: missing sc_id')
                continue

            txt = fetch_sc_translation(uid, "sujato", timeout_s=12)
            if _looks_bad(txt):
                failed.append(f'{entry.get("sutta_id")}: empty extract')
                continue
            entry["sc_sutta"] = txt
            updated += 1
        except Exception as e:
            failed.append(f'{entry.get("sutta_id")}: {type(e).__name__}: {e}')

        time.sleep(0.3)

    # Write back
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Keep key order consistent
    reorder = Path("reorder_an2.py")
    if reorder.exists():
        import runpy

        runpy.run_path(str(reorder), run_name="__main__")

    report = Path("backfill_sc_sutta_an2.report.txt")
    lines = [f"updated_entries={updated}", f"skipped_entries={skipped}", f"failed_entries={len(failed)}", ""]
    lines.extend(failed)
    report.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

