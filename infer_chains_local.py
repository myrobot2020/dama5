"""
Fully offline chain inference for AN per-sutta JSON (no APIs, no network).

Strategies (in order):
  1) Use existing ``chain`` in the file if valid.
  2) Sutta ASR: after ``what N`` / ``these N``, split on spaced markers `` 2 `` … `` N ``.
  3) Commentary ASR: split on verbal ``number 1`` … ``number N`` (teacher enumeration).

Writes JSONL for review; optional ``--apply`` merges ``chain`` into JSON files.

Usage:
  python infer_chains_local.py --books 11 --output chains_local_an11.jsonl
  python infer_chains_local.py --books 4 5 6 7 8 9 10 11 --output chains_local_an4_11.jsonl
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


def normalize_chain_obj(raw: object) -> dict | None:
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


def split_sutta_numbered(sutta: str, n: int) -> tuple[list[str], str]:
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
            return [], f"missing_sutta_marker_{i}"
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
    short = [re.sub(r"\s+", " ", x)[:220].strip() for x in pieces]
    return (short, "ok")


def split_commentary_number_labels(commentary: str, n: int) -> tuple[list[str], str]:
    """Segments after ``number K`` until the next ``number`` label."""
    if not commentary or not commentary.strip():
        return [], "empty_commentary"

    t = commentary.strip()
    rx = re.compile(r"\bnumber\s+(\d{1,2})\b", re.I)
    matches = list(rx.finditer(t))
    if not matches:
        return [], "no_number_labels"

    by_num: dict[int, str] = {}
    for i, m in enumerate(matches):
        num = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(t)
        chunk = t[start:end].strip()
        chunk = re.sub(r"^[\s:.,;-]+", "", chunk)
        prev = by_num.get(num)
        if prev is not None:
            chunk = prev + " " + chunk
        by_num[num] = chunk

    items: list[str] = []
    missing: list[int] = []
    for k in range(1, n + 1):
        if k in by_num:
            items.append(re.sub(r"\s+", " ", by_num[k])[:220].strip())
        else:
            items.append("")
            missing.append(k)

    note = "ok" if not missing else f"gaps_{missing}"
    return items, note


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
    ap = argparse.ArgumentParser(description="Offline chain inference for an*/suttas/*.json")
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument("--books", type=int, nargs="+", required=True)
    ap.add_argument(
        "--output",
        type=Path,
        help="JSONL path (default: chains_local_book_<first>-<last>.jsonl in repo root)",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Write inferred chain into each sutta JSON (only when source is not stored)",
    )
    args = ap.parse_args()
    repo = args.repo.resolve()
    books = sorted(set(args.books))
    out_path = args.output
    if out_path is None:
        lo, hi = min(books), max(books)
        out_path = repo / f"chains_local_an{lo}_{hi}.jsonl" if lo != hi else repo / f"chains_local_an{lo}.jsonl"

    rows_written = 0
    with out_path.open("w", encoding="utf-8") as out_f:
        for p in iter_paths(repo, books):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                out_f.write(
                    json.dumps({"path": str(p), "error": str(e)}, ensure_ascii=False) + "\n"
                )
                continue
            if not isinstance(data, dict):
                continue

            sid = str(data.get("sutta_id") or p.stem)
            n = book_from_sutta_id(sid)
            if n is None:
                continue

            stored = normalize_chain_obj(data.get("chain"))
            if stored:
                row = {
                    "sutta_id": sid,
                    "path": str(p.relative_to(repo)),
                    "expected_n": n,
                    "source": "stored",
                    "split_note": "ok",
                    "nonempty_count": len([x for x in stored["items"] if x.strip()]),
                    "chain": stored,
                }
                out_f.write(json.dumps(row, ensure_ascii=False) + "\n")
                rows_written += 1
                continue

            sutta = str(data.get("sutta") or "")
            commentary = str(data.get("commentary") or "")

            s_items, s_note = split_sutta_numbered(sutta, n)
            c_items, c_note = split_commentary_number_labels(commentary, n)

            nonempty_s = len([x for x in s_items if x.strip()])
            nonempty_c = len([x for x in c_items if x.strip()])

            source = None
            split_note = ""
            items_out: list[str] = []
            category = ""

            if s_note == "ok" and nonempty_s == n:
                source = "sutta_asr"
                split_note = s_note
                items_out = s_items
            elif nonempty_c >= nonempty_s and nonempty_c > 0:
                source = "commentary_asr"
                split_note = c_note
                items_out = c_items
            elif nonempty_s > 0:
                source = "sutta_asr_partial"
                split_note = s_note
                items_out = s_items
            else:
                source = "failed"
                split_note = f"sutta:{s_note};commentary:{c_note}"
                items_out = s_items if s_items else c_items

            chain_obj = {
                "items": items_out,
                "count": n,
                "is_ordered": True,
                "category": category,
            }

            row = {
                "sutta_id": sid,
                "path": str(p.relative_to(repo)),
                "expected_n": n,
                "source": source,
                "split_note": split_note,
                "nonempty_count": len([x for x in items_out if x.strip()]),
                "chain": chain_obj,
            }
            out_f.write(json.dumps(row, ensure_ascii=False) + "\n")
            rows_written += 1

            if args.apply and source != "failed" and source != "stored":
                filled = len([x for x in items_out if x.strip()])
                if filled == n:
                    data["chain"] = {
                        "items": items_out,
                        "count": n,
                        "is_ordered": False,
                        "category": category,
                    }
                    p.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )

    print(f"Wrote {rows_written} records to {out_path}")


if __name__ == "__main__":
    main()
