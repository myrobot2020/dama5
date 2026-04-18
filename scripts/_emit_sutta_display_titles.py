"""Emit sutta_display_titles.py from docs/sutta_id_chain.txt. Run from repo root: python scripts/_emit_sutta_display_titles.py"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from textwrap import dedent


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    p = root / "docs" / "sutta_id_chain.txt"
    text = p.read_text(encoding="utf-8")
    r = csv.DictReader(io.StringIO(text))
    out_en: dict[str, str] = {}
    out_pali: dict[str, str] = {}
    for row in r:
        c = row.get("Conceptual Chain") or ""
        en = (row.get("Sutta Name (English)") or "").strip()
        pl = (row.get("Sutta Name (Pali)") or "").strip()
        m = re.search(r"\b(\d+\.\d+(?:\.\d+)?)\b", c)
        if m and en:
            k = m.group(1)
            out_en[k] = en
            if pl:
                out_pali[k] = pl

    def sort_key(key: str) -> tuple:
        return tuple(int(x) for x in key.split("."))

    body_lines = [
        dedent(
            '''\
            """Sutta display names from docs/sutta_id_chain.txt (English + Pali). Nav uses English only."""
            from __future__ import annotations

            from typing import Optional


            def ensure_english_sutta_suffix(name: str) -> str:
                """If `name` already ends with 'sutta' (any case), return as-is; else append ' Sutta'."""
                s = (name or "").strip()
                if not s:
                    return s
                if s.lower().endswith("sutta"):
                    return s
                return s + " Sutta"


            def dotted_id_from_an_suttaid(suttaid: str) -> str:
                """Strip leading 'AN ' from normalized ids like 'AN 3.2.19' -> '3.2.19'."""
                s = (suttaid or "").strip()
                if s.upper().startswith("AN "):
                    return s[3:].strip()
                return s


            # Keys: dotted sutta id as in JSON (e.g. 3.2.19), from Conceptual Chain column.
            TITLE_EN: dict[str, str] = {
            '''
        ).rstrip()
    ]
    for k in sorted(out_en.keys(), key=sort_key):
        body_lines.append(f"    {k!r}: {out_en[k]!r},")
    body_lines.append("}")
    body_lines.append("")
    body_lines.append("")
    body_lines.append("TITLE_PALI: dict[str, str] = {")
    for k in sorted(out_pali.keys(), key=sort_key):
        body_lines.append(f"    {k!r}: {out_pali[k]!r},")
    body_lines.append("}")
    body_lines.append("")
    body_lines.append("")
    body_lines.append("def english_nav_title_for_dotted_id(dotted: str) -> Optional[str]:")
    body_lines.append('    """Return formatted English nav label if known, else None."""')
    body_lines.append("    raw = TITLE_EN.get((dotted or '').strip())")
    body_lines.append("    if raw is None:")
    body_lines.append("        return None")
    body_lines.append("    return ensure_english_sutta_suffix(raw)")
    body_lines.append("")
    body_lines.append("")
    body_lines.append("def pali_name_for_dotted_id(dotted: str) -> Optional[str]:")
    body_lines.append('    """Return Pali short name if known, else None."""')
    body_lines.append("    raw = TITLE_PALI.get((dotted or '').strip())")
    body_lines.append("    if raw is None:")
    body_lines.append("        return None")
    body_lines.append("    return raw")
    body_lines.append("")
    (root / "sutta_display_titles.py").write_text("\n".join(body_lines) + "\n", encoding="utf-8")
    print(f"wrote sutta_display_titles.py TITLE_EN={len(out_en)} TITLE_PALI={len(out_pali)}")


if __name__ == "__main__":
    main()
