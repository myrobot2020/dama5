#!/usr/bin/env python3
"""Emit docs/sutta_id_chain.txt: valid suttas only — sutta_id | item1,item2,...

Valid means:
- eligible_record(..., require_audio_times=True): non-empty sutta, commentary, aud_file;
  numeric aud_start_s, aud_end_s.
- Anguttara chain: len(chain.items) == book number from sutta_id (first dotted segment),
  same rule as extract_chain_ollama with require_book_length (count must match when present).
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any


def _extract_chain_mod():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("extract_chain_ollama", root / "scripts" / "extract_chain_ollama.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # dataclass / imports need module in sys.modules for some Python versions
    sys.modules["extract_chain_ollama"] = mod
    spec.loader.exec_module(mod)
    return mod


def stem_key(path: Path) -> tuple[int, ...]:
    s = path.stem
    parts = [p for p in s.split(".") if p]
    key: list[int] = []
    for p in parts:
        if p.isdigit():
            key.append(int(p))
        else:
            nums = re.findall(r"\d+", p)
            key.append(int(nums[0]) if nums else 0)
    return tuple(key) if key else (0,)


def format_chain_csv(items: list[str]) -> str:
    """Comma-separate items; quote if needed (comma or quote inside item)."""
    out: list[str] = []
    for raw in items:
        it = str(raw).strip().replace("\n", " ")
        if not it:
            continue
        if "," in it or '"' in it:
            out.append('"' + it.replace('"', '""') + '"')
        else:
            out.append(it)
    return ",".join(out)


def _an_book_num(sutta_dir: Path) -> int:
    m = re.match(r"^an(\d+)$", sutta_dir.parent.name)
    return int(m.group(1)) if m else 0


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    mod = _extract_chain_mod()
    eligible_record = mod.eligible_record
    parse_book = mod.parse_anguttara_book_num
    anguttara_chain_matches_book = mod.anguttara_chain_matches_book
    lines_out: list[str] = []
    book_dirs = [p for p in root.glob("an*/suttas") if p.is_dir()]
    book_dirs.sort(key=_an_book_num)
    for book_dir in book_dirs:
        files = [p for p in book_dir.glob("*.json") if p.name != "_index.json"]
        files.sort(key=stem_key)
        for f in files:
            obj = json.loads(f.read_text(encoding="utf-8"))
            ok, _ = eligible_record(obj, require_audio_times=True)
            if not ok:
                continue
            sid = str(obj.get("sutta_id") or "").strip()
            book_num = parse_book(sid)
            if not anguttara_chain_matches_book(obj, book_num):
                continue
            ch = obj.get("chain")
            assert isinstance(ch, dict)
            items = [str(x) for x in ch["items"] if x is not None and str(x).strip()]
            rhs = format_chain_csv(items)
            lines_out.append(f"{sid} | {rhs}")

    out = root / "docs" / "sutta_id_chain.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines_out) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(lines_out)} lines)")


if __name__ == "__main__":
    main()
