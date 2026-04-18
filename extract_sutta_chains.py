"""
Walk an*/suttas/*.json and emit one record per file that has a structured `chain` object.

Chain shape (when present):
  "chain": {
    "items": [...],
    "count": int,
    "is_ordered": bool,
    "category": str
  }

Usage:
  python extract_sutta_chains.py > chains.jsonl
  python extract_sutta_chains.py --missing-list missing_no_chain.txt
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def iter_sutta_paths(repo: Path, books: list[int] | None = None) -> list[Path]:
    out: list[Path] = []
    for d in sorted(repo.glob("an*/suttas")):
        if not d.is_dir():
            continue
        name = d.parent.name  # e.g. an11
        if not name.startswith("an"):
            continue
        try:
            bk = int(name[2:])
        except ValueError:
            continue
        if books is not None and bk not in books:
            continue
        for f in sorted(d.glob("*.json")):
            if f.name.startswith("_"):
                continue
            out.append(f)
    return out


def normalize_chain(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    items = raw.get("items")
    if not isinstance(items, list) or not all(isinstance(x, str) for x in items):
        return None
    return {
        "items": items,
        "count": raw.get("count", len(items)),
        "is_ordered": bool(raw.get("is_ordered", False)),
        "category": str(raw.get("category") or ""),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument(
        "--books",
        type=int,
        nargs="+",
        help="Limit to these AN book numbers only (e.g. --books 11)",
    )
    ap.add_argument("--missing-list", type=Path, help="Write sutta_ids with no chain (one per line)")
    args = ap.parse_args()
    repo = args.repo.resolve()

    paths = iter_sutta_paths(repo, books=args.books)
    missing: list[str] = []

    for p in paths:
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(json.dumps({"error": str(e), "path": str(p)}, ensure_ascii=False), file=sys.stderr)
            continue
        if not isinstance(raw, dict):
            print(json.dumps({"error": "root_not_object", "path": str(p)}, ensure_ascii=False), file=sys.stderr)
            continue
        data = raw
        sid = str(data.get("sutta_id") or p.stem)
        ch = normalize_chain(data.get("chain"))
        if ch is None:
            missing.append(sid)
            continue
        try:
            rel = str(p.relative_to(repo))
        except ValueError:
            rel = str(p)
        row = {
            "sutta_id": sid,
            "path": rel,
            **ch,
        }
        if isinstance(data.get("alignment"), dict):
            row["alignment_chain_score"] = data["alignment"].get("scores_0_to_5", {}).get("chain")
        print(json.dumps(row, ensure_ascii=False))

    if args.missing_list:
        args.missing_list.write_text("\n".join(missing) + ("\n" if missing else ""), encoding="utf-8")


if __name__ == "__main__":
    main()
