#!/usr/bin/env python3
"""Set an1 sutta_name_en from the single chain item (Book of Ones: one item = title)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _extract_chain_mod():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("extract_chain_ollama", root / "scripts" / "extract_chain_ollama.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["extract_chain_ollama"] = mod
    spec.loader.exec_module(mod)
    return mod


def chain_first_item_title(obj: dict) -> str | None:
    ch = obj.get("chain")
    if not isinstance(ch, dict):
        return None
    items = ch.get("items")
    if not isinstance(items, list) or not items:
        return None
    first = items[0]
    if not isinstance(first, str):
        return None
    s = first.strip()
    return s if s else None


def main() -> int:
    mod = _extract_chain_mod()
    atomic_write_json = mod.atomic_write_json
    root = Path(__file__).resolve().parents[1]
    book1 = root / "an1" / "suttas"
    if not book1.is_dir():
        print("an1/suttas not found", file=sys.stderr)
        return 1
    updated = 0
    for path in sorted(book1.glob("*.json")):
        if path.name == "_index.json" or path.name.startswith("_"):
            continue
        obj = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            continue
        title = chain_first_item_title(obj)
        if title is None:
            continue
        if (obj.get("sutta_name_en") or "").strip() == title:
            continue
        obj["sutta_name_en"] = title
        atomic_write_json(path, obj)
        updated += 1
    print(f"synced sutta_name_en from chain for {updated} an1 files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
