#!/usr/bin/env python3
"""
Add Anguttara Book-of-Ones chains (exactly one item) and merge aud/* timing from aud/audio_map.json.

- Chain: count=1, items=[one word], is_ordered=true; word = refrain noun ("other single X") or keyword scan or first content token.
- Audio: keys in audio_map.json are commentary ids like "cAN 1.18.13" — we match sutta_id.

Re-run after extending audio_map.json for more AN 1 suttas.

Usage (repo root):
  python scripts/backfill_an1_chains_and_audio.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def category_book_one(sutta: str) -> str:
    sl = (sutta or "").lower()
    if "i know not of any other single" in sl or "know of no other single" in sl:
        return "single dominant factor"
    return "single factor"


# Skip when picking the first “content” word from ASR (not the doctrinal head noun).
_CHAIN_STOP = frozenset(
    {
        "a",
        "an",
        "the",
        "i",
        "if",
        "for",
        "so",
        "as",
        "at",
        "be",
        "by",
        "do",
        "go",
        "he",
        "in",
        "is",
        "it",
        "me",
        "my",
        "no",
        "of",
        "on",
        "or",
        "to",
        "up",
        "we",
        "am",
        "are",
        "but",
        "not",
        "now",
        "all",
        "any",
        "can",
        "did",
        "get",
        "has",
        "had",
        "him",
        "his",
        "how",
        "may",
        "new",
        "one",
        "our",
        "out",
        "own",
        "say",
        "she",
        "too",
        "two",
        "who",
        "buddha",
        "monk",
        "monks",
        "said",
        "just",
        "even",
        "then",
        "than",
        "that",
        "this",
        "they",
        "what",
        "when",
        "with",
        "from",
        "into",
        "such",
        "here",
        "there",
        "other",
        "single",
        "thing",
        "things",
        "very",
        "also",
        "some",
        "much",
        "many",
        "more",
        "most",
        "only",
        "like",
        "well",
        "thus",
        "have",
        "been",
        "were",
        "was",
        "will",
        "shall",
        "could",
        "would",
        "should",
        "know",
        "knew",
        "knows",
        "other",
        "even",
        "bit",
        "same",
        "like",
        "just",
        "trifling",
        "evil",
        "lasting",
    }
)

# Prefer these if they appear as whole words (ASR / mixed spelling).
_PRIORITY_WORDS: tuple[tuple[str, str], ...] = (
    ("mettā", "mettā"),
    ("metta", "mettā"),
    ("jhāna", "jhāna"),
    ("jhana", "jhāna"),
    ("negligence", "negligence"),
    ("earnestness", "earnestness"),
    ("mindfulness", "mindfulness"),
    ("friendship", "friendship"),
    ("wisdom", "wisdom"),
    ("dhamma", "dhamma"),
)


def chain_item_book_one(sutta: str) -> str:
    """Single word for Book of Ones chain item (count=1)."""
    s = re.sub(r"\s+", " ", (sutta or "").strip())
    if not s:
        return "dhamma"

    sl = s.lower()

    # Anguttara 1 refrain: “… other single <word> …”
    m = re.search(
        r"(?i)\bother\s+single\s+([^\s,.;:!?'\"]+)",
        s,
    )
    if m:
        w = m.group(1).strip("'\"")
        low = w.lower()
        if low not in _CHAIN_STOP and len(low) >= 2:
            return w

    for needle, canonical in _PRIORITY_WORDS:
        if re.search(rf"(?i)\b{re.escape(needle)}\b", s):
            return canonical

    # Tokens: letters + Pali diacritics + apostrophe inside word
    for raw in re.findall(r"[\w''\-āīūṭḍṇṃṅñ]+", s):
        w = raw.strip("'").lower()
        if len(w) < 2:
            continue
        if w in _CHAIN_STOP:
            continue
        return raw.strip("'")

    return "dhamma"


def commentary_key(sutta_id: str) -> str:
    sid = (sutta_id or "").strip()
    return f"cAN {sid}" if sid else ""


def chain_block(sutta: str) -> dict[str, Any]:
    item = chain_item_book_one(sutta)
    return {
        "items": [item],
        "count": 1,
        "is_ordered": True,
        "category": category_book_one(sutta),
    }


def reorder(obj: dict[str, Any]) -> dict[str, Any]:
    order = [
        "sutta_id",
        "sutta_name_en",
        "sutta_name_pali",
        "sutta",
        "commentary",
        "chain",
        "aud_file",
        "aud_start_s",
        "aud_end_s",
        "valid",
    ]
    out: dict[str, Any] = {}
    for k in order:
        if k in obj:
            out[k] = obj[k]
    for k, v in obj.items():
        if k not in out:
            out[k] = v
    return out


def main() -> None:
    root = _repo_root()
    map_path = root / "aud" / "audio_map.json"
    audio_map: dict[str, Any] = {}
    if map_path.is_file():
        audio_map = json.loads(map_path.read_text(encoding="utf-8"))

    d = root / "an1" / "suttas"
    n_chain = 0
    n_audio = 0
    for path in sorted(d.glob("*.json")):
        if path.name.startswith("_"):
            continue
        obj = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            continue
        sid = str(obj.get("sutta_id") or "").strip()
        sutta = str(obj.get("sutta") or "")
        comm = str(obj.get("commentary") or "")
        obj["chain"] = chain_block(sutta)
        n_chain += 1

        ck = commentary_key(sid)
        entry = audio_map.get(ck) if ck else None
        if isinstance(entry, dict):
            fn = str(entry.get("file") or "").strip()
            try:
                st = float(entry.get("start_s") or 0.0)
                en = float(entry.get("end_s") or 0.0)
            except (TypeError, ValueError):
                st, en = 0.0, 0.0
            if fn and en > st:
                obj["aud_file"] = fn
                obj["aud_start_s"] = round(st, 2)
                obj["aud_end_s"] = round(en, 2)
                n_audio += 1

        has_aud = bool(str(obj.get("aud_file") or "").strip()) and float(obj.get("aud_end_s") or 0) > float(
            obj.get("aud_start_s") or 0.0
        )
        ch = obj.get("chain")
        chain_ok = (
            isinstance(ch, dict)
            and isinstance(ch.get("items"), list)
            and len(ch.get("items")) == 1
            and str((ch.get("items") or [""])[0] or "").strip()
        )
        obj["valid"] = bool(chain_ok and has_aud and sutta.strip() and comm.strip())

        path.write_text(json.dumps(reorder(obj), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"an1: wrote chain for {n_chain} files; merged audio_map for {n_audio} files")


if __name__ == "__main__":
    main()
