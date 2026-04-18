"""
Run incremental_transcribe_backfill.py for several books in order (e.g. 9 down to 4).

Use when a prior book (e.g. 10) has finished — do not run in parallel with another GPU job.

Usage:
  python incremental_transcribe_books_sequence.py --books 9 8 7 6 5 4
  python incremental_transcribe_books_sequence.py --books 9 8 7 6 5 4 --sleep_after_mp3 60 --backfill_interval 300
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser(description="Sequential incremental transcribe+backfill for multiple AN books.")
    ap.add_argument("--books", type=int, nargs="+", required=True, help="Book numbers in order (e.g. 9 8 7 6 5 4)")
    ap.add_argument("--sleep_after_mp3", type=float, default=60.0)
    ap.add_argument("--backfill_interval", type=float, default=300.0)
    ap.add_argument("--no_backfill_thread", action="store_true")
    ap.add_argument("--forward_backfill", action="store_true")
    args = ap.parse_args()

    runner = _REPO / "incremental_transcribe_backfill.py"
    if not runner.is_file():
        raise SystemExit(f"Missing {runner}")

    for book in args.books:
        print(f"\n========== BOOK {book} ==========\n", flush=True)
        cmd = [
            sys.executable,
            str(runner),
            "--book",
            str(book),
            "--sleep_after_mp3",
            str(args.sleep_after_mp3),
            "--backfill_interval",
            str(args.backfill_interval),
        ]
        if args.no_backfill_thread:
            cmd.append("--no_backfill_thread")
        if args.forward_backfill:
            cmd.append("--forward_backfill")
        r = subprocess.run(cmd, cwd=str(_REPO))
        if r.returncode != 0:
            raise SystemExit(f"Book {book} failed with exit code {r.returncode}")
    print("\nAll requested books finished.\n", flush=True)


if __name__ == "__main__":
    main()
