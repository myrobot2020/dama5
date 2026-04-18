#!/usr/bin/env python3
"""Rebuild root-level an{N}.json from an{N}/suttas/*.json (valid JSON array)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _stem_key(stem: str) -> tuple[int, ...]:
    s = re.sub(r"^AN\s+", "", stem, flags=re.I).strip()
    parts = [p for p in s.split(".") if p]
    key: list[int] = []
    for p in parts:
        if p.isdigit():
            key.append(int(p))
        else:
            nums = re.findall(r"\d+", p)
            key.append(int(nums[0]) if nums else 0)
    return tuple(key) if key else (0,)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("book", type=int, help="Anguttara book number (e.g. 1..11)")
    ap.add_argument(
        "--out",
        default="",
        help="Output path (default: an{N}.json in repo root)",
    )
    ap.add_argument(
        "--strip-chain",
        action="store_true",
        help="Remove top-level 'chain' key from each object (for non-chain exports).",
    )
    args = ap.parse_args()
    book = int(args.book)
    root = Path(__file__).resolve().parents[1]
    sutta_dir = root / f"an{book}" / "suttas"
    if not sutta_dir.is_dir():
        raise SystemExit(f"Missing {sutta_dir}")
    out_path = Path(args.out) if args.out.strip() else root / f"an{book}.json"

    files = [p for p in sutta_dir.glob("*.json") if p.is_file() and p.name != "_index.json"]
    files.sort(key=lambda p: _stem_key(p.stem))
    arr: list[object] = []
    for f in files:
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SystemExit(f"Invalid JSON in {f}: {e}") from e
        if args.strip_chain and isinstance(obj, dict) and "chain" in obj:
            obj = {k: v for k, v in obj.items() if k != "chain"}
        arr.append(obj)

    out_path.write_text(json.dumps(arr, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_path} ({len(arr)} records)")


if __name__ == "__main__":
    main()
