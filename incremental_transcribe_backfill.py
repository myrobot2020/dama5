"""
Transcribe all MP3s for one AN book, then periodically backfill aud_* into an{book}/suttas/*.json.

Usage (repo root):
  python incremental_transcribe_backfill.py --book 11
  python incremental_transcribe_backfill.py --book 4 --sleep_after_mp3 60 --backfill_interval 300

GPU: uses aud/transcribe_fasterwhisper.py with --device cuda (CUDA bin is auto-added there on Windows).
Backfill: runs backfill_audio_an_commentary.py --book N --reverse in a background thread every N seconds.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent


def discover_mp3s_for_book(aud_dir: Path, book: int) -> list[Path]:
    rx = re.compile(r"Book\s+(\d+)")
    out: list[Path] = []
    for p in sorted(aud_dir.glob("*.mp3")):
        m = rx.search(p.name)
        if m and int(m.group(1)) == book:
            out.append(p)
    return out


def segments_path_for_mp3(mp3: Path, transcripts_dir: Path) -> Path:
    return transcripts_dir / (mp3.stem + "_segments.json")


def run_backfill(book: int, reverse: bool) -> None:
    cmd = [
        sys.executable,
        str(_REPO / "backfill_audio_an_commentary.py"),
        "--book",
        str(book),
        "--report",
        str(_REPO / f"audio_mapping_report_an{book}.md"),
    ]
    if reverse:
        cmd.append("--reverse")
    subprocess.run(cmd, cwd=str(_REPO), check=False)


def main() -> None:
    ap = argparse.ArgumentParser(description="Incremental transcribe + periodic backfill for one AN book.")
    ap.add_argument("--book", type=int, required=True, help="AN book number (e.g. 11)")
    ap.add_argument("--aud_dir", type=Path, default=Path("aud"))
    ap.add_argument("--transcripts_dir", type=Path, default=Path("aud/transcripts"))
    ap.add_argument("--model", default="small")
    ap.add_argument("--language", default="en")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--compute_type", default="float16")
    ap.add_argument("--sleep_after_mp3", type=float, default=60.0, help="Seconds to pause after each MP3 (GPU cooldown)")
    ap.add_argument(
        "--backfill_interval",
        type=float,
        default=300.0,
        help="Run backfill every this many seconds (0 = only at start/end)",
    )
    ap.add_argument("--no_backfill_thread", action="store_true", help="Disable periodic backfill")
    ap.add_argument(
        "--forward_backfill",
        action="store_true",
        help="Backfill in ascending sutta order (default is --reverse via backfill script)",
    )
    args = ap.parse_args()

    book = int(args.book)
    aud_dir = (_REPO / args.aud_dir).resolve()
    transcripts_dir = (_REPO / args.transcripts_dir).resolve()
    transcribe_py = _REPO / "aud" / "transcribe_fasterwhisper.py"

    if not transcribe_py.is_file():
        raise SystemExit(f"Missing {transcribe_py}")

    mp3s = discover_mp3s_for_book(aud_dir, book)
    if not mp3s:
        raise SystemExit(f"No MP3 under {aud_dir} for book={book} (expected '... Book {book} ...' in filename)")

    reverse_bf = not bool(args.forward_backfill)

    stop = threading.Event()

    def backfill_worker() -> None:
        interval = float(args.backfill_interval)
        if interval <= 0:
            return
        while not stop.wait(timeout=interval):
            print(f"[backfill] book={book} (reverse={reverse_bf})", flush=True)
            run_backfill(book, reverse_bf)

    print(f"book={book} mp3s={len(mp3s)} sleep_after_mp3={args.sleep_after_mp3}s backfill_interval={args.backfill_interval}s", flush=True)

    # Initial backfill (picks up any existing transcripts)
    print("[backfill] initial run", flush=True)
    run_backfill(book, reverse_bf)

    worker: threading.Thread | None = None
    if not args.no_backfill_thread and float(args.backfill_interval) > 0:
        worker = threading.Thread(target=backfill_worker, name="backfill", daemon=True)
        worker.start()

    try:
        for mp3 in mp3s:
            out_json = segments_path_for_mp3(mp3, transcripts_dir)
            if out_json.is_file():
                print(f"[skip transcript] {mp3.name}", flush=True)
            else:
                print(f"=== transcribe {mp3.name} ===", flush=True)
                cmd = [
                    sys.executable,
                    "-u",
                    str(transcribe_py),
                    "--mp3",
                    str(mp3),
                    "--model",
                    args.model,
                    "--language",
                    args.language,
                    "--device",
                    args.device,
                    "--compute_type",
                    args.compute_type,
                ]
                r = subprocess.run(cmd, cwd=str(_REPO))
                if r.returncode != 0:
                    print(f"[warn] transcribe exit {r.returncode} for {mp3.name}", flush=True)
            if args.sleep_after_mp3 > 0:
                time.sleep(float(args.sleep_after_mp3))
    finally:
        stop.set()
        if worker is not None:
            worker.join(timeout=5.0)

    print("[backfill] final run", flush=True)
    run_backfill(book, reverse_bf)
    print("done.", flush=True)


if __name__ == "__main__":
    main()
