from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


def _ollama_base_url() -> str:
    return (
        os.environ.get("DAMA_OLLAMA_BASE_URL", "").strip()
        or os.environ.get("OLLAMA_BASE_URL", "").strip()
        or "http://localhost:11434"
    ).rstrip("/")


def _ollama_model() -> str:
    return os.environ.get("DAMA_OLLAMA_MODEL", "").strip() or os.environ.get("OLLAMA_MODEL", "").strip() or "mistral:instruct"


def _build_prompt(commentary: str) -> str:
    # Keep it deterministic and conservative: fix grammar/punctuation only; do not add new claims.
    return (
        "You are cleaning an ASR transcript of a Buddhist talk.\n"
        "Task: rewrite the text into clean, readable English with proper punctuation and capitalization.\n"
        "Constraints:\n"
        "- Do NOT add new factual claims.\n"
        "- Do NOT remove content except filler like 'uh', 'um', repeated fragments, and obvious ASR glitches.\n"
        "- Keep meaning the same.\n"
        "- Keep it as ONE paragraph (no bullet lists).\n"
        "- Output ONLY the cleaned text.\n\n"
        "TEXT:\n"
        f"{commentary.strip()}\n"
    )


def clean_text_via_ollama(
    http: requests.Session,
    *,
    base_url: str,
    model: str,
    text: str,
    num_predict: int = 512,
    temperature: float = 0.1,
    timeout_s: int = 120,
) -> str:
    url = f"{base_url}/api/generate"
    payload = {
        "model": model,
        "prompt": _build_prompt(text),
        "stream": False,
        "options": {"temperature": temperature, "num_predict": num_predict},
    }
    r = http.post(url, json=payload, timeout=timeout_s)
    r.raise_for_status()
    data = r.json()
    out = str(data.get("response") or "").strip()
    if not out:
        raise RuntimeError("Ollama returned empty response")
    return out


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_backup(path: Path) -> Path:
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup = path.with_suffix(path.suffix + f".bak-{ts}")
    shutil.copy2(path, backup)
    return backup


def _should_skip(text: str) -> bool:
    t = (text or "").strip()
    return (not t) or len(t) < 30


def main() -> None:
    ap = argparse.ArgumentParser(description="Clean AN2 commentary using local Ollama.")
    ap.add_argument("--in", dest="inp", default="an2.json", help="Input JSON (default: an2.json)")
    ap.add_argument("--out", dest="out", default="", help="Output JSON (default: overwrite input after backup)")
    ap.add_argument("--limit", type=int, default=0, help="Only process first N entries with commentary (0 = all)")
    ap.add_argument("--sleep-ms", type=int, default=0, help="Sleep between calls (ms)")
    ap.add_argument("--num-predict", type=int, default=512)
    ap.add_argument("--model", type=str, default="", help="Override model (default from env or mistral:instruct)")
    ap.add_argument("--dry-run", action="store_true", help="Do not write output")
    args = ap.parse_args()

    src = Path(args.inp)
    if not src.is_file():
        raise FileNotFoundError(f"Input not found: {src}")

    out_path = Path(args.out) if args.out else src

    data = _load_json(src)
    if not isinstance(data, list):
        raise TypeError("Expected top-level list")

    base_url = _ollama_base_url()
    model = (args.model or _ollama_model()).strip()

    http = requests.Session()

    changed = 0
    attempted = 0
    failures: List[Tuple[str, str]] = []
    processed = 0

    for entry in data:
        if not isinstance(entry, dict):
            continue
        comm = str(entry.get("commentary") or "")
        if _should_skip(comm):
            continue
        if args.limit and processed >= args.limit:
            break

        attempted += 1
        sid = str(entry.get("sutta_id") or "")
        try:
            cleaned = clean_text_via_ollama(
                http,
                base_url=base_url,
                model=model,
                text=comm,
                num_predict=args.num_predict,
            )
            if cleaned and cleaned != comm:
                entry["commentary"] = cleaned
                changed += 1
            processed += 1
        except Exception as e:
            failures.append((sid, f"{type(e).__name__}: {e}"))

        if args.sleep_ms:
            time.sleep(args.sleep_ms / 1000.0)

    if failures:
        print("Failures:")
        for sid, err in failures[:20]:
            print(f"- {sid}: {err}")
        if len(failures) > 20:
            print(f"... and {len(failures) - 20} more")

    print(f"ollama_base_url={base_url}")
    print(f"model={model}")
    print(f"attempted={attempted} changed={changed} failures={len(failures)}")

    if args.dry_run:
        print("dry-run: not writing output")
        return

    if out_path == src:
        backup = _atomic_backup(src)
        print(f"backup={backup.name}")

    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote={out_path}")


if __name__ == "__main__":
    main()

