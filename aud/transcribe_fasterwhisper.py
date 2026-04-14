import argparse
import json
import os
from pathlib import Path

import imageio_ffmpeg
from faster_whisper import WhisperModel


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mp3", required=True, help="MP3 path (relative to repo root or absolute)")
    ap.add_argument("--out", default="", help="Output JSON path (default: aud/transcripts/<mp3-stem>_segments.json)")
    ap.add_argument("--model", default="tiny", help="faster-whisper model name (tiny/base/small/medium/...)")
    ap.add_argument("--language", default="en")
    args = ap.parse_args()

    mp3 = Path(args.mp3)
    if not mp3.is_file():
        raise SystemExit(f"MP3 not found: {mp3}")
    out_dir = Path("aud") / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = Path(args.out).resolve() if args.out.strip() else (out_dir / (mp3.stem + "_segments.json"))

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    os.environ["PATH"] = str(Path(ff).parent) + os.pathsep + os.environ.get("PATH", "")

    print("Loading model…")
    model = WhisperModel(str(args.model), device="cpu", compute_type="int8")
    print("Transcribing…")
    segments, info = model.transcribe(str(mp3), language=str(args.language), beam_size=5, vad_filter=True)

    rows = [{"start": float(s.start), "end": float(s.end), "text": (s.text or "").strip()} for s in segments]
    data = {
        "source": "faster-whisper",
        "model": str(args.model),
        "device": "cpu",
        "compute_type": "int8",
        "language": getattr(info, "language", None),
        "duration": getattr(info, "duration", None),
        "segments": rows,
    }
    out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_json}")
    print(f"segments {len(rows)} duration_s {data['duration']}")


if __name__ == "__main__":
    main()

