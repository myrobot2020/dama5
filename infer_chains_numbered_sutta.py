"""
Best-effort extraction of chain.items from sutta ASR text when the discourse uses
standalone digits 1..N as item markers (common in AN list suttas).

Does not use LLMs. Output is for review when commentary/sutta alignment matters.

Usage:
  python infer_chains_numbered_sutta.py --books 11
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def book_from_sutta_id(sid: str) -> int | None:
    part = str(sid).strip().split(".", 1)[0]
    try:
        return int(part)
    except ValueError:
        return None


def split_numbered_items(sutta: str, n: int) -> tuple[list[str], str]:
    """
    Split sutta text into N segments using standalone digit markers 2..N
    (item 1 is text from after 'what N' / 'these N' until marker 2).
    Markers must appear in order (each `` K `` found after the previous).
    """
    t = " ".join(sutta.lower().split())
    m = re.search(r"(?:what|these)\s+(?:are\s+)?(?:the\s+)?" + str(n) + r"\b", t)
    start = m.end() if m else 0
    body = t[start:].strip()

    if n <= 1:
        return ([body] if body else [], "no_split")

    marker_starts: list[int] = []
    cursor = 0
    for i in range(2, n + 1):
        pat = re.compile(rf"\s{i}\s")
        mm = pat.search(body, cursor)
        if not mm:
            return [], f"missing_marker_{i}"
        marker_starts.append(mm.start())
        cursor = mm.start() + 1

    positions = [0] + marker_starts + [len(body)]
    pieces: list[str] = []
    for a, b in zip(positions, positions[1:]):
        chunk = body[a:b].strip()
        chunk = re.sub(r"^\d{1,2}\s+", "", chunk)
        pieces.append(chunk)

    if len(pieces) != n:
        return [], "piece_count_mismatch"

    short = [re.sub(r"\s+", " ", x)[:200].strip() for x in pieces]
    return (short, "ok")


def iter_paths(repo: Path, books: list[int]) -> list[Path]:
    out: list[Path] = []
    for b in books:
        d = repo / f"an{b}" / "suttas"
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            if f.name.startswith("_"):
                continue
            out.append(f)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument("--books", type=int, nargs="+", required=True)
    args = ap.parse_args()
    repo = args.repo.resolve()

    for p in iter_paths(repo, args.books):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(json.dumps({"path": str(p), "error": str(e)}, ensure_ascii=False))
            continue
        if not isinstance(data, dict):
            continue
        sid = str(data.get("sutta_id") or p.stem)
        n = book_from_sutta_id(sid)
        if n is None:
            continue
        if normalize_chain_obj(data.get("chain")):
            # Already have structured chain — skip infer
            continue

        sutta = str(data.get("sutta") or "")
        items, note = split_numbered_items(sutta, n)
        row = {
            "sutta_id": sid,
            "path": str(p.relative_to(repo)),
            "expected_n": n,
            "item_count": len(items),
            "split_note": note,
            "items": items,
            "category": "",
        }
        print(json.dumps(row, ensure_ascii=False))


def normalize_chain_obj(raw: object) -> bool:
    if not isinstance(raw, dict):
        return False
    it = raw.get("items")
    return isinstance(it, list) and len(it) > 0


if __name__ == "__main__":
    main()
