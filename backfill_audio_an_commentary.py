from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


TRANSCRIPTS_DIR = Path("aud/transcripts")

# Keep clips tight-ish; you can widen later.
MAX_CLIP_S_DEFAULT = 170.0
MIN_CLIP_S_DEFAULT = 20.0

STOPWORDS = {
    "a",
    "about",
    "after",
    "again",
    "all",
    "also",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "before",
    "but",
    "by",
    "can",
    "come",
    "could",
    "did",
    "do",
    "does",
    "done",
    "end",
    "even",
    "etc",
    "for",
    "from",
    "get",
    "go",
    "going",
    "got",
    "had",
    "has",
    "have",
    "he",
    "her",
    "here",
    "him",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "just",
    "know",
    "like",
    "may",
    "means",
    "mind",
    "monk",
    "monks",
    "more",
    "most",
    "next",
    "not",
    "now",
    "of",
    "on",
    "one",
    "or",
    "other",
    "our",
    "people",
    "person",
    "said",
    "say",
    "saying",
    "see",
    "so",
    "some",
    "sometimes",
    "such",
    "suta",
    "sutta",
    "that",
    "the",
    "their",
    "then",
    "there",
    "these",
    "they",
    "thing",
    "things",
    "this",
    "those",
    "to",
    "two",
    "uh",
    "we",
    "what",
    "when",
    "which",
    "who",
    "will",
    "with",
    "would",
    "you",
    "your",
}


def toks(text: str) -> List[str]:
    ws = re.findall(r"[a-z]{2,}", (text or "").lower())
    return [w for w in ws if w not in STOPWORDS]


def build_idf(seg_texts: List[str]) -> Dict[str, float]:
    df: Dict[str, int] = {}
    n = max(1, len(seg_texts))
    for t in seg_texts:
        s = set(toks(t))
        for w in s:
            df[w] = df.get(w, 0) + 1
    idf: Dict[str, float] = {}
    for w, c in df.items():
        idf[w] = math.log((n + 1) / (c + 1)) + 1.0
    return idf


def pick_anchor(commentary: str, idf: Dict[str, float], *, min_words: int = 10, max_words: int = 18) -> List[str]:
    words = toks(commentary)
    if len(words) <= min_words:
        return words
    best: List[str] = []
    best_score = -1.0
    for L in range(max_words, min_words - 1, -1):
        for i in range(0, len(words) - L + 1):
            window = words[i : i + L]
            score = sum(idf.get(w, 1.0) for w in window) / max(1, L)
            if score > best_score:
                best_score = score
                best = window
        if best:
            break
    return best


def overlap_score(anchor: List[str], seg_tokens: List[str]) -> float:
    if not anchor:
        return 0.0
    a = set(anchor)
    b = set(seg_tokens)
    return len(a & b) / max(1, len(a))


@dataclass
class Match:
    idx: int
    score: float


def best_segment_match(anchor: List[str], seg_tokens: List[List[str]]) -> Match:
    best = Match(idx=0, score=0.0)
    for i, st in enumerate(seg_tokens):
        sc = overlap_score(anchor, st)
        if sc > best.score:
            best = Match(idx=i, score=sc)
    return best


def expand_window(
    segs: List[Dict[str, Any]],
    center_idx: int,
    *,
    max_clip_s: float,
    min_clip_s: float,
) -> Tuple[int, int]:
    n = len(segs)
    start = max(0, center_idx - 1)
    end = min(n - 1, center_idx + 8)

    def dur(a: int, b: int) -> float:
        return float(segs[b]["end"]) - float(segs[a]["start"])

    while dur(start, end) < min_clip_s and (start > 0 or end < n - 1):
        if start > 0:
            start -= 1
        if dur(start, end) >= min_clip_s:
            break
        if end < n - 1:
            end += 1

    while True:
        d = dur(start, end)
        if d >= max_clip_s:
            break
        grew = False
        if end < n - 1 and d < max_clip_s:
            end += 1
            grew = True
        d = dur(start, end)
        if d >= max_clip_s:
            break
        if start > 0 and d < max_clip_s:
            start -= 1
            grew = True
        if not grew:
            break
    return start, end


@dataclass
class TranscriptBundle:
    mp3: str
    segments_path: Path
    segs: List[Dict[str, Any]]
    seg_texts: List[str]
    seg_tokens: List[List[str]]
    idf: Dict[str, float]
    id_to_idx: Dict[str, int]
    boundaries: List[Tuple[int, str]]
    # Inclusive PTS-style triple range parsed from the MP3/transcript filename (e.g. 3212–3324 → 3.2.12–3.3.24).
    filename_range: Optional[Tuple[Tuple[int, int, int], Tuple[int, int, int]]] = None


def mp3_name_from_segments_path(p: Path) -> str:
    return p.name.replace("_segments.json", ".mp3")


# e.g. "… Book 3A 3212 - 3324 by …" / "… Book 3E 3660 by …" / "… Book 3J 3983 - 31099 by …"
_MP3_FILE_RANGE_RX = re.compile(r"Book\s+(\d+)\s*[A-Za-z]?\s+(.+?)\s+by\b", re.IGNORECASE)


def parse_compressed_token_to_triple(book: int, token: str) -> Optional[Tuple[int, int, int]]:
    """
    Decode filename tokens like 3212 → (3,2,12), 31099 → (3,10,99), 3660 → (3,6,60).

    Filenames use a fixed digit grouping after the book digit: 3 + (chapter digits) + (sutta digits).
    Common lengths: 3→1+2, 4→2+2, 5→2+3 (matches Bhante AN MP3 naming).
    """
    d = re.sub(r"[^0-9]", "", token or "")
    bp = str(book)
    if not d.startswith(bp):
        return None
    rest = d[len(bp) :]
    if not rest:
        return None
    L = len(rest)
    split_lens: List[Tuple[int, int]]
    if L == 2:
        split_lens = [(1, 1)]
    elif L == 3:
        split_lens = [(1, 2)]
    elif L == 4:
        split_lens = [(2, 2)]
    elif L == 5:
        split_lens = [(2, 3)]
    elif L == 6:
        split_lens = [(2, 4), (3, 3)]
    else:
        split_lens = [(i, L - i) for i in range(1, L)]

    for la, lb in split_lens:
        if la + lb != L:
            continue
        a, b = rest[:la], rest[la:]
        if len(a) > 1 and a.startswith("0"):
            continue
        if len(b) > 1 and b.startswith("0"):
            continue
        try:
            ch, su = int(a), int(b)
        except ValueError:
            continue
        if 1 <= ch <= 50 and 1 <= su <= 400:
            return (book, ch, su)
    return None


def parse_filename_audio_range(filename: str, book: int) -> Optional[Tuple[Tuple[int, int, int], Tuple[int, int, int]]]:
    m = _MP3_FILE_RANGE_RX.search(filename)
    if not m or int(m.group(1)) != book:
        return None
    chunk = (m.group(2) or "").strip()
    if not chunk:
        return None
    if " - " in chunk:
        a, b = chunk.split(" - ", 1)
        t0 = parse_compressed_token_to_triple(book, a.strip())
        t1 = parse_compressed_token_to_triple(book, b.strip())
    else:
        t0 = t1 = parse_compressed_token_to_triple(book, chunk)
    if not t0 or not t1:
        return None
    if t0 > t1:
        t0, t1 = t1, t0
    return (t0, t1)


def sutta_id_to_order_triple(sid: str, book: int) -> Optional[Tuple[int, int, int]]:
    """
    Map sutta_id to a comparable triple. Two-part ids (e.g. 3.4) → (3, 4, 1); three-part → full.
    """
    sid = _norm_sid(sid)
    if not sid:
        return None
    parts: List[int] = []
    for p in sid.split("."):
        if not p:
            continue
        if p.isdigit():
            parts.append(int(p))
        else:
            digits = "".join(ch for ch in p if ch.isdigit())
            if digits:
                parts.append(int(digits))
    if len(parts) < 2 or parts[0] != book:
        return None
    if len(parts) == 2:
        return (parts[0], parts[1], 1)
    return (parts[0], parts[1], parts[2])


def bundle_priority_for_sutta(b: TranscriptBundle, sid: str, book: int) -> int:
    """Higher = try this transcript first (filename range matches sutta)."""
    t = sutta_id_to_order_triple(sid, book)
    if t is None or b.filename_range is None:
        return 1
    lo, hi = b.filename_range
    if lo <= t <= hi:
        return 2
    return 0


def sort_bundles_for_sutta(bundles: List[TranscriptBundle], sid: str, book: int) -> List[TranscriptBundle]:
    return [
        b
        for _, b in sorted(
            enumerate(bundles),
            key=lambda ib: (-bundle_priority_for_sutta(ib[1], sid, book), ib[0]),
        )
    ]


def _norm_sid(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    s = re.sub(r"^AN\s+", "", s, flags=re.I).strip()
    return s


def build_boundary_index_for_book(seg_texts: List[str], book: int) -> Tuple[Dict[str, int], List[Tuple[int, str]]]:
    """
    Extract boundary markers like '3.2.12' or '11.6' from transcript text.
    We accept either 2- or 3-part dotted IDs, then filter to this book prefix.
    """
    id_pat = re.compile(r"\b(?P<sid>\d+\.\d+(?:\.\d+)?)\b")
    prefix = f"{book}."
    id_to_idx: Dict[str, int] = {}
    boundaries: List[Tuple[int, str]] = []
    for i, t in enumerate(seg_texts):
        m = id_pat.search(t)
        if not m:
            continue
        sid = m.group("sid")
        if not sid.startswith(prefix):
            continue
        if sid not in id_to_idx:
            id_to_idx[sid] = i
            boundaries.append((i, sid))
    boundaries.sort(key=lambda x: x[0])
    return id_to_idx, boundaries


def load_bundle(segments_path: Path, book: int) -> TranscriptBundle:
    seg_obj = json.loads(segments_path.read_text(encoding="utf-8"))
    segs = seg_obj.get("segments")
    if not isinstance(segs, list) or not segs:
        raise TypeError(f"Transcript segments missing/empty: {segments_path}")
    seg_texts = [str(s.get("text") or "") for s in segs]
    seg_tokens = [toks(t) for t in seg_texts]
    idf = build_idf(seg_texts)
    id_to_idx, boundaries = build_boundary_index_for_book(seg_texts, book)
    rng = parse_filename_audio_range(segments_path.name, book)
    return TranscriptBundle(
        mp3=mp3_name_from_segments_path(segments_path),
        segments_path=segments_path,
        segs=segs,
        seg_texts=seg_texts,
        seg_tokens=seg_tokens,
        idf=idf,
        id_to_idx=id_to_idx,
        boundaries=boundaries,
        filename_range=rng,
    )


def discover_segment_paths_for_book(transcripts_dir: Path, book: int) -> List[Path]:
    """
    Match only real AN book N transcripts.

    Avoid globs like *Book*4* (matches '244') or *Book 1* (matches 'Book 11').
    Parse the first integer after 'Book' in the filename and compare to `book`.
    """
    if not transcripts_dir.is_dir():
        return []
    rx = re.compile(r"Book\s+(\d+)")
    out: List[Path] = []
    for p in sorted(transcripts_dir.glob("*_segments.json")):
        if not p.is_file():
            continue
        m = rx.search(p.name)
        if not m:
            continue
        if int(m.group(1)) == book:
            out.append(p)
    return out


def attempt_map_commentary(
    sid: str,
    commentary: str,
    b: TranscriptBundle,
    *,
    max_clip_s: float,
    min_clip_s: float,
    min_overlap: float,
    sutta: str = "",
) -> Optional[Tuple[float, str, float, float, str, List[str]]]:
    """
    Returns (score, mp3, start_s, end_s, status, anchor_tokens) or None.
    """
    sid = _norm_sid(sid)
    if not sid or not (commentary or "").strip():
        return None

    # Prefer exact boundary markers when present.
    if sid in b.id_to_idx:
        start_idx = b.id_to_idx[sid]
        end_boundary_idx: Optional[int] = None
        for bi, _bsid in b.boundaries:
            if bi > start_idx:
                end_boundary_idx = bi
                break
        start_s = float(b.segs[start_idx]["start"])
        if end_boundary_idx is not None:
            end_s = float(b.segs[max(start_idx, end_boundary_idx - 1)]["end"])
        else:
            end_s = float(b.segs[-1]["end"])
        if end_s - start_s > max_clip_s:
            end_s = start_s + max_clip_s
        anchor = pick_anchor(commentary, b.idf)
        return (1.0, b.mp3, start_s, end_s, "OK", anchor)

    # Fuzzy match: try anchors from commentary, sutta text, and combined (commentary often
    # discusses etymology while the transcript follows the sutta wording).
    sutta_excerpt = (sutta or "")[:4500]
    anchor_candidates: List[List[str]] = []
    ac = pick_anchor(commentary, b.idf)
    if ac:
        anchor_candidates.append(ac)
    if sutta_excerpt.strip():
        as_ = pick_anchor(sutta_excerpt, b.idf)
        if as_ and as_ != ac:
            anchor_candidates.append(as_)
        comb = (commentary or "").strip() + " " + sutta_excerpt
        ac2 = pick_anchor(comb, b.idf)
        if ac2 and not any(ac2 == x for x in anchor_candidates):
            anchor_candidates.append(ac2)

    best_m = Match(idx=0, score=0.0)
    best_anchor: List[str] = []
    for anchor in anchor_candidates:
        if not anchor:
            continue
        m = best_segment_match(anchor, b.seg_tokens)
        if m.score > best_m.score:
            best_m = m
            best_anchor = anchor
    if not best_anchor:
        return None
    if best_m.score < min_overlap:
        return None
    start_idx, end_idx = expand_window(b.segs, best_m.idx, max_clip_s=max_clip_s, min_clip_s=min_clip_s)
    start_s = float(b.segs[start_idx]["start"])
    end_s = float(b.segs[end_idx]["end"])
    status = "WEAK" if best_m.score < 0.55 else "OK"
    return (best_m.score, b.mp3, start_s, end_s, status, best_anchor)


def _sutta_stem_sort_key(stem: str) -> Tuple[int, ...]:
    """Sort sutta filenames like 4.18.180, 11.6, 4.17 — numeric tuple, missing parts = 0."""
    s = (stem or "").strip()
    s = re.sub(r"^AN\s+", "", s, flags=re.I).strip()
    parts = [p for p in s.split(".") if p]
    key: List[int] = []
    for p in parts:
        if p.isdigit():
            key.append(int(p))
        else:
            nums = re.findall(r"\d+", p)
            key.append(int(nums[0]) if nums else 0)
    return tuple(key) if key else (0,)


def iter_sutta_files(book: int, *, reverse: bool = False) -> List[Path]:
    d = Path(f"an{book}") / "suttas"
    if not d.is_dir():
        return []
    files = [p for p in d.glob("*.json") if p.is_file() and p.name != "_index.json"]
    files.sort(key=lambda p: _sutta_stem_sort_key(p.stem), reverse=reverse)
    return files


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill aud_* fields for AN books (commentary-only), per-sutta JSON files.")
    ap.add_argument("--book", type=int, required=True, help="AN book number (e.g. 3..11)")
    ap.add_argument("--transcripts_dir", default=str(TRANSCRIPTS_DIR))
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing aud_* fields")
    ap.add_argument("--max_clip_s", type=float, default=MAX_CLIP_S_DEFAULT)
    ap.add_argument("--min_clip_s", type=float, default=MIN_CLIP_S_DEFAULT)
    ap.add_argument("--report", default="", help="Optional markdown report path")
    ap.add_argument(
        "--reverse",
        action="store_true",
        help="Process suttas in reverse order (higher sutta ids first; better for incremental long-commentary runs)",
    )
    ap.add_argument(
        "--min_overlap",
        type=float,
        default=0.33,
        help="Minimum token-overlap score between commentary/sutta anchors and a transcript segment (default: 0.33)",
    )
    args = ap.parse_args()

    book = int(args.book)
    transcripts_dir = Path(args.transcripts_dir)
    seg_paths = discover_segment_paths_for_book(transcripts_dir, book)
    if not seg_paths:
        raise SystemExit(
            f"No segment JSON under {transcripts_dir} for book={book} "
            f"(expected *Book {book}*_segments.json or *Book  {book}*_segments.json)"
        )

    bundles = [load_bundle(p, book) for p in seg_paths]
    sutta_files = iter_sutta_files(book, reverse=bool(args.reverse))
    if not sutta_files:
        raise SystemExit(f"No per-sutta JSON files found under an{book}/suttas (expected *.json excluding _index.json)")

    rows: List[str] = []
    mapped = 0
    skipped = 0
    weak = 0
    missing = 0

    for p in sutta_files:
        obj = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            continue
        sid = str(obj.get("sutta_id") or "").strip()
        comm = str(obj.get("commentary") or "")
        sutta_text = str(obj.get("sutta") or "")
        if not sid or not comm.strip():
            skipped += 1
            continue

        if not args.overwrite and str(obj.get("aud_file") or "").strip() and float(obj.get("aud_end_s") or 0.0) > float(
            obj.get("aud_start_s") or 0.0
        ):
            skipped += 1
            continue

        best: Optional[Tuple[float, str, float, float, str, List[str]]] = None
        ordered = sort_bundles_for_sutta(bundles, sid, book)
        for b in ordered:
            r = attempt_map_commentary(
                sid,
                comm,
                b,
                max_clip_s=float(args.max_clip_s),
                min_clip_s=float(args.min_clip_s),
                min_overlap=float(args.min_overlap),
                sutta=sutta_text,
            )
            if r is None:
                continue
            if best is None or r[0] > best[0]:
                best = r

        if best is None:
            missing += 1
            rows.append(f"| {sid} | NO_MATCH ({len(bundles)} src) | 0.00 | {p.name} | |")
            continue

        score, mp3, start_s, end_s, status, anchor = best
        obj["aud_file"] = mp3
        obj["aud_start_s"] = round(start_s, 2)
        obj["aud_end_s"] = round(end_s, 2)
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

        mapped += 1
        if status == "WEAK":
            weak += 1
        rows.append(f"| {sid} | {status} | {score:.2f} | {mp3[:42]}… | {' '.join(anchor[:14])} |")

    if args.report.strip():
        report = Path(args.report)
        src_list = ", ".join(b.segments_path.name for b in bundles)
        header = [
            f"## AN{book} audio mapping report (commentary-only)",
            "",
            f"- segment sources ({len(bundles)}): **{src_list}**",
            f"- mapped: **{mapped}**",
            f"- skipped: **{skipped}**",
            f"- weak matches: **{weak}**",
            f"- misses: **{missing}**",
            "",
            "| sutta_id | status | score | mp3 | anchor |",
            "|---|---:|---:|---|---|",
        ]
        report.write_text("\n".join(header + rows) + "\n", encoding="utf-8")

    print(f"book={book} bundles={len(bundles)} suttas={len(sutta_files)} mapped={mapped} skipped={skipped} weak={weak} missing={missing}")


if __name__ == "__main__":
    main()

