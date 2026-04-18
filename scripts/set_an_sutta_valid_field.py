#!/usr/bin/env python3
"""Set `valid` on each an*/suttas/*.json using an_record_valid() from extract_chain_ollama."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


def _extract_chain_mod():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("extract_chain_ollama", root / "scripts" / "extract_chain_ollama.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["extract_chain_ollama"] = mod
    spec.loader.exec_module(mod)
    return mod


def _book_num_from_sutta_path(path: Path) -> int:
    # anN/suttas/x.json -> N
    m = re.match(r"^an(\d+)$", path.parent.parent.name)
    return int(m.group(1)) if m else 0


def main() -> int:
    mod = _extract_chain_mod()
    an_record_valid = mod.an_record_valid
    atomic_write_json = mod.atomic_write_json
    root = Path(__file__).resolve().parents[1]
    paths = sorted(
        p
        for p in root.glob("an*/suttas/*.json")
        if p.is_file() and p.name != "_index.json" and not p.name.startswith("_")
    )
    updated = 0
    by_book: dict[int, dict[str, int]] = defaultdict(lambda: {"true": 0, "false": 0})
    for path in paths:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"skip {path}: {exc}", file=sys.stderr)
            continue
        if not isinstance(obj, dict):
            continue
        v = an_record_valid(obj)
        bn = _book_num_from_sutta_path(path)
        if bn:
            by_book[bn]["true" if v else "false"] += 1
        if obj.get("valid") is v:
            continue
        obj["valid"] = v
        atomic_write_json(path, obj)
        updated += 1
    print(f"updated {updated} of {len(paths)} sutta JSON files")
    print("per book (valid true / valid false / total):")
    for bn in sorted(by_book):
        d = by_book[bn]
        t, f = d["true"], d["false"]
        label = "Book of Ones" if bn == 1 else ""
        extra = f" — {label}" if label else ""
        print(f"  an{bn}{extra}: {t} / {f} / {t + f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
