"""
Per-book readiness tally for AN4–AN11 (or any --books range): suttas, commentary, audio, chains.

**Prod-ready** (default): non-empty sutta text, non-empty commentary, complete audio
(``aud_file``, ``aud_start_s``, ``aud_end_s`` numeric and end >= start),
and **good chain**: ``chain.items`` exists, length equals book nipāta number,
all item strings non-empty after strip.

Also runs the same inference logic as ``infer_chains_local.py`` into a JSONL artifact
unless --no-infer-jsonl.

Usage:
  python an_book_pipeline_report.py
  python an_book_pipeline_report.py --books 11 10 9 8 7 6 5 4 --out-md an_readiness_an4_11.md
  python an_book_pipeline_report.py --apply-chains   # writes chain only when infer fills all N slots
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

# Re-use inference helpers (same module patterns as infer_chains_local)
from infer_chains_local import (
    book_from_sutta_id,
    iter_paths,
    normalize_chain_obj,
    split_commentary_number_labels,
    split_sutta_numbered,
)


def book_from_an_path(p: Path) -> int | None:
    name = p.parent.parent.name
    if not name.startswith("an"):
        return None
    try:
        return int(name[2:])
    except ValueError:
        return None


@dataclass
class BookStats:
    sutta_files: int = 0
    parse_errors: int = 0
    has_sutta_text: int = 0
    has_commentary: int = 0
    has_audio: int = 0
    has_chain_block: int = 0
    good_chains: int = 0
    prod_ready: int = 0


def audio_ok(data: dict) -> bool:
    af = data.get("aud_file")
    if not isinstance(af, str) or not af.strip():
        return False
    try:
        st = float(data["aud_start_s"])
        en = float(data["aud_end_s"])
    except (KeyError, TypeError, ValueError):
        return False
    return en >= st


def sutta_text_ok(data: dict) -> bool:
    s = data.get("sutta")
    return isinstance(s, str) and bool(s.strip())


def commentary_ok(data: dict) -> bool:
    c = data.get("commentary")
    return isinstance(c, str) and bool(c.strip())


def good_chain(data: dict, expected_book: int) -> bool:
    ch = normalize_chain_obj(data.get("chain"))
    if not ch:
        return False
    items = ch["items"]
    if len(items) != expected_book:
        return False
    return all(isinstance(x, str) and x.strip() for x in items)


def infer_chain_payload(data: dict, expected_book: int) -> tuple[dict | None, str]:
    """Return chain dict to merge or None; second value is source tag."""
    if normalize_chain_obj(data.get("chain")):
        return dict(data["chain"]), "stored"

    sutta = str(data.get("sutta") or "")
    commentary = str(data.get("commentary") or "")

    s_items, s_note = split_sutta_numbered(sutta, expected_book)
    c_items, _c_note = split_commentary_number_labels(commentary, expected_book)

    nonempty_s = sum(1 for x in s_items if x.strip())
    nonempty_c = sum(1 for x in c_items if x.strip())

    items_out: list[str] = []
    source = "failed"

    if s_note == "ok" and nonempty_s == expected_book:
        items_out = s_items
        source = "sutta_asr"
    elif nonempty_c >= nonempty_s and nonempty_c > 0:
        items_out = c_items
        source = "commentary_asr"
    elif nonempty_s > 0:
        items_out = s_items
        source = "sutta_asr_partial"

    if not items_out:
        return None, "failed"

    return (
        {
            "items": items_out,
            "count": expected_book,
            "is_ordered": True,
            "category": "",
        },
        source,
    )


def chain_infer_prod_ok(payload: dict | None, source: str, expected_book: int) -> bool:
    if payload is None or source == "failed":
        return False
    items = payload.get("items") or []
    if len(items) != expected_book:
        return False
    return all(isinstance(x, str) and x.strip() for x in items)


def main() -> None:
    ap = argparse.ArgumentParser(description="AN book pipeline tally (books 4–11 by default)")
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument(
        "--books",
        type=int,
        nargs="+",
        default=list(range(11, 3, -1)),
        help="Book numbers (default: 11 down to 4)",
    )
    ap.add_argument("--out-md", type=Path, default=None, help="Markdown report path")
    ap.add_argument("--out-json", type=Path, default=None, help="JSON summary path")
    ap.add_argument(
        "--infer-jsonl",
        type=Path,
        default=None,
        help="Write per-file inference rows (default: chains_infer_an{min}_{max}.jsonl)",
    )
    ap.add_argument("--no-infer-jsonl", action="store_true", help="Skip writing inference JSONL")
    ap.add_argument(
        "--apply-chains",
        action="store_true",
        help="Merge inferred chain into JSON when inference is prod-grade (full N slots)",
    )
    args = ap.parse_args()
    repo = args.repo.resolve()
    books = sorted(set(args.books))

    stats_by: dict[int, BookStats] = defaultdict(BookStats)
    infer_path = args.infer_jsonl
    if infer_path is None and not args.no_infer_jsonl:
        lo, hi = min(books), max(books)
        infer_path = repo / f"chains_infer_an{lo}_{hi}.jsonl"

    infer_f = None
    if infer_path and not args.no_infer_jsonl:
        infer_path.parent.mkdir(parents=True, exist_ok=True)
        infer_f = infer_path.open("w", encoding="utf-8")

    paths = iter_paths(repo, books)
    for p in paths:
        book = book_from_an_path(p)
        if book is None:
            continue

        st = stats_by[book]
        st.sutta_files += 1

        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            st.parse_errors += 1
            continue

        if not isinstance(data, dict):
            continue

        sid = str(data.get("sutta_id") or p.stem)
        eb = book_from_sutta_id(sid)
        if eb is None:
            eb = book

        if sutta_text_ok(data):
            st.has_sutta_text += 1
        if commentary_ok(data):
            st.has_commentary += 1
        if audio_ok(data):
            st.has_audio += 1
        if normalize_chain_obj(data.get("chain")):
            st.has_chain_block += 1
        if good_chain(data, eb):
            st.good_chains += 1

        if (
            sutta_text_ok(data)
            and commentary_ok(data)
            and audio_ok(data)
            and good_chain(data, eb)
        ):
            st.prod_ready += 1

        payload, src = infer_chain_payload(data, eb)
        if infer_f is not None:
            row = {
                "sutta_id": sid,
                "path": str(p.relative_to(repo)),
                "expected_n": eb,
                "infer_source": src,
                "infer_prod_grade": chain_infer_prod_ok(payload, src, eb),
            }
            if payload:
                row["chain"] = payload
            infer_f.write(json.dumps(row, ensure_ascii=False) + "\n")

        if args.apply_chains and payload and chain_infer_prod_ok(payload, src, eb):
            if not good_chain(data, eb):
                data["chain"] = payload
                p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if infer_f is not None:
        infer_f.close()

    # Console table
    lines = []
    lines.append(
        "| book | suttas | +sutta text | +commentary | +audio | +chain obj | good chains | prod-ready | parse err |"
    )
    lines.append("|-----:|-------:|------------:|------------:|-------:|-----------:|------------:|-----------:|----------:|")
    for b in sorted(stats_by.keys(), reverse=True):
        s = stats_by[b]
        lines.append(
            f"| {b} | {s.sutta_files} | {s.has_sutta_text} | {s.has_commentary} | {s.has_audio} | "
            f"{s.has_chain_block} | {s.good_chains} | {s.prod_ready} | {s.parse_errors} |"
        )
    text = "\n".join(lines)
    print(text)

    total = BookStats()
    for s in stats_by.values():
        total.sutta_files += s.sutta_files
        total.parse_errors += s.parse_errors
        total.has_sutta_text += s.has_sutta_text
        total.has_commentary += s.has_commentary
        total.has_audio += s.has_audio
        total.has_chain_block += s.has_chain_block
        total.good_chains += s.good_chains
        total.prod_ready += s.prod_ready

    print()
    print(
        f"TOTAL (books {min(books)}–{max(books)}): "
        f"suttas={total.sutta_files} commentary={total.has_commentary} audio={total.has_audio} "
        f"good_chains={total.good_chains} prod_ready={total.prod_ready} parse_errors={total.parse_errors}"
    )

    out_md = args.out_md or repo / f"an_readiness_an{min(books)}_{max(books)}.md"
    meta = (
        "Criteria — **prod-ready**: non-empty sutta & commentary; audio has `aud_file`, "
        "`aud_start_s`, `aud_end_s` with end ≥ start; **good chain**: "
        "`len(chain.items)==book` and every item non-empty.\n\n"
        f"Inference artifact: `{infer_path}` (per-file infer rows; prod-grade means infer filled all N slots).\n\n"
    )
    out_md.write_text(meta + "```\n" + text + "\n```\n", encoding="utf-8")
    print(f"\nWrote {out_md}")

    out_js = args.out_json or repo / f"an_readiness_an{min(books)}_{max(books)}.json"
    summary = {
        "books": {
            str(b): {
                "sutta_files": stats_by[b].sutta_files,
                "has_sutta_text": stats_by[b].has_sutta_text,
                "has_commentary": stats_by[b].has_commentary,
                "has_audio": stats_by[b].has_audio,
                "has_chain_block": stats_by[b].has_chain_block,
                "good_chains": stats_by[b].good_chains,
                "prod_ready": stats_by[b].prod_ready,
                "parse_errors": stats_by[b].parse_errors,
            }
            for b in sorted(stats_by.keys())
        },
        "totals": {
            "sutta_files": total.sutta_files,
            "has_sutta_text": total.has_sutta_text,
            "has_commentary": total.has_commentary,
            "has_audio": total.has_audio,
            "has_chain_block": total.has_chain_block,
            "good_chains": total.good_chains,
            "prod_ready": total.prod_ready,
            "parse_errors": total.parse_errors,
        },
        "infer_jsonl": str(infer_path) if infer_path and not args.no_infer_jsonl else None,
    }
    out_js.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {out_js}")


if __name__ == "__main__":
    main()
