import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


TRANSCRIPTS_DIR = Path("aud/transcripts")

# Hand-checked: sutta text only in that MP3 (e.g. 2.1.5 ends before MN12 digression in 006).
MANUAL_SUTTA_WINDOWS: Dict[str, Tuple[str, float, float]] = {
    "2.1.5": (
        "006_Anguttara Nikaya Book  2A 212 - 239 by Bhante Hye Dhammavuddho Mahathera.mp3",
        256.16,
        356.98,
    ),
}

# Keep clips tight-ish; you can widen later.
MAX_CLIP_S = 170.0
MIN_CLIP_S = 20.0

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


def best_segment_match(anchor: List[str], seg_texts: List[str], seg_tokens: List[List[str]]) -> Match:
    best = Match(idx=0, score=0.0)
    for i, st in enumerate(seg_tokens):
        sc = overlap_score(anchor, st)
        if sc > best.score:
            best = Match(idx=i, score=sc)
    return best


def strip_sutta_id(sid: str, text: str) -> str:
    return re.sub(r"^\s*" + re.escape(sid) + r"\s+", "", (text or ""), flags=re.I).strip()


def best_anchor_match(
    entry: Dict[str, Any],
    idf: Dict[str, float],
    seg_texts: List[str],
    seg_tokens: List[List[str]],
) -> Tuple[List[str], Match]:
    """Prefer sutta text (and leading phrase) over commentary — commentary often digresses to other suttas."""
    sid = str(entry.get("sutta_id") or "")
    candidates: List[List[str]] = []
    sutta = strip_sutta_id(sid, str(entry.get("sutta") or ""))
    if sutta:
        w = toks(sutta)
        if w:
            candidates.append(w[:42])
        pa = pick_anchor(sutta, idf)
        if pa:
            candidates.append(pa)
    comm = str(entry.get("commentary") or "")
    if comm.strip():
        candidates.append(pick_anchor(comm, idf))
    sc = str(entry.get("sc_sutta") or "")
    if sc.strip():
        candidates.append(pick_anchor(sc, idf))

    best_m = Match(idx=0, score=0.0)
    best_anchor: List[str] = []
    for anchor in candidates:
        if not anchor:
            continue
        m = best_segment_match(anchor, seg_texts, seg_tokens)
        if m.score > best_m.score or (m.score == best_m.score and len(anchor) > len(best_anchor)):
            best_m = m
            best_anchor = anchor
    if not best_anchor:
        best_anchor = []
    return best_anchor, best_m


def expand_window(
    segs: List[Dict[str, Any]],
    center_idx: int,
    *,
    max_clip_s: float = MAX_CLIP_S,
    min_clip_s: float = MIN_CLIP_S,
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


def build_boundary_index(seg_texts: List[str]) -> Tuple[Dict[str, int], List[Tuple[int, str]]]:
    id_pat = re.compile(r"\b2\.\d+\.\d+\b")
    id_to_idx: Dict[str, int] = {}
    boundaries: List[Tuple[int, str]] = []
    for i, t in enumerate(seg_texts):
        m = id_pat.search(t)
        if not m:
            continue
        sid = m.group(0)
        if sid not in id_to_idx:
            id_to_idx[sid] = i
            boundaries.append((i, sid))
    boundaries.sort(key=lambda x: x[0])
    return id_to_idx, boundaries


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


def mp3_name_from_segments_path(p: Path) -> str:
    return p.name.replace("_segments.json", ".mp3")


def discover_an2_segment_paths(transcripts_dir: Path) -> List[Path]:
    """All Book 2 Anguttara whisper segment files (006 2A, 007 2B, 008 2C, …) when present."""
    if not transcripts_dir.is_dir():
        return []
    cands = sorted(transcripts_dir.glob("*Anguttara*Nikaya*Book*2*_segments.json"))
    return [p for p in cands if p.is_file()]


def load_bundle(segments_path: Path) -> TranscriptBundle:
    seg_obj = json.loads(segments_path.read_text(encoding="utf-8"))
    segs = seg_obj.get("segments")
    if not isinstance(segs, list) or not segs:
        raise TypeError(f"Transcript segments missing/empty: {segments_path}")
    seg_texts = [str(s.get("text") or "") for s in segs]
    seg_tokens = [toks(t) for t in seg_texts]
    idf = build_idf(seg_texts)
    id_to_idx, boundaries = build_boundary_index(seg_texts)
    return TranscriptBundle(
        mp3=mp3_name_from_segments_path(segments_path),
        segments_path=segments_path,
        segs=segs,
        seg_texts=seg_texts,
        seg_tokens=seg_tokens,
        idf=idf,
        id_to_idx=id_to_idx,
        boundaries=boundaries,
    )


def attempt_map_entry(
    entry: Dict[str, Any],
    sid: str,
    b: TranscriptBundle,
) -> Optional[Tuple[float, str, float, float, str, List[str], str]]:
    """
    Try to map one entry using one transcript. Returns:
    (score, mp3, start_s, end_s, status, anchor_preview, source_label) or None if this file cannot map.
    """
    comm = str(entry.get("commentary") or "")
    sc_raw = str(entry.get("sc_sutta") or "")

    anchor, fuzzy_m = best_anchor_match(entry, b.idf, b.seg_texts, b.seg_tokens)
    if not anchor:
        anchor = pick_anchor(comm, b.idf) if comm.strip() else toks(sc_raw)[:30]

    source_label = b.segments_path.name.replace("_segments.json", "")

    if sid in b.id_to_idx:
        start_idx = b.id_to_idx[sid]
        end_boundary_idx: Optional[int] = None
        for bi, bsid in b.boundaries:
            if bi > start_idx:
                end_boundary_idx = bi
                break
        start_s = float(b.segs[start_idx]["start"])
        if end_boundary_idx is not None:
            end_s = float(b.segs[max(start_idx, end_boundary_idx - 1)]["end"])
        else:
            end_s = float(b.segs[-1]["end"])
        if end_s - start_s > MAX_CLIP_S:
            end_s = start_s + MAX_CLIP_S
        return (1.0, b.mp3, start_s, end_s, "OK", anchor, source_label)

    m = fuzzy_m
    if not anchor:
        return None
    if m.score < 0.40:
        return None
    start_idx, end_idx = expand_window(b.segs, m.idx)
    start_s = float(b.segs[start_idx]["start"])
    end_s = float(b.segs[end_idx]["end"])
    status = "WEAK" if m.score < 0.55 else "OK"
    return (m.score, b.mp3, start_s, end_s, status, anchor, source_label)


def main() -> None:
    an2_path = Path("an2.json")
    an2 = json.loads(an2_path.read_text(encoding="utf-8"))
    if not isinstance(an2, list):
        raise TypeError("Expected top-level list in an2.json")

    seg_paths = discover_an2_segment_paths(TRANSCRIPTS_DIR)
    if not seg_paths:
        raise FileNotFoundError(
            f"No AN2 segment JSON under {TRANSCRIPTS_DIR} (expected names like "
            f"*Anguttara*Nikaya*Book*2*_segments.json). Add 006/007/008 transcripts there."
        )
    bundles = [load_bundle(p) for p in seg_paths]

    rows: List[str] = []
    mapped = 0
    skipped = 0
    weak = 0
    missing = 0

    for entry in an2:
        if not isinstance(entry, dict):
            continue
        sid = str(entry.get("sutta_id") or "")
        comm = str(entry.get("commentary") or "")
        sutta_raw = str(entry.get("sutta") or "")
        sc_raw = str(entry.get("sc_sutta") or "")
        if not comm.strip() and not sutta_raw.strip() and not sc_raw.strip():
            skipped += 1
            continue

        af = str(entry.get("aud_file") or "").strip()
        a0 = float(entry.get("aud_start_s") or 0.0)
        a1 = float(entry.get("aud_end_s") or 0.0)
        if af and a1 > a0:
            skipped += 1
            continue

        if sid in MANUAL_SUTTA_WINDOWS:
            mp3_m, w0, w1 = MANUAL_SUTTA_WINDOWS[sid]
            entry["aud_file"] = mp3_m
            entry["aud_start_s"] = round(w0, 2)
            entry["aud_end_s"] = round(w1, 2)
            mapped += 1
            rows.append(f"| {sid} | MANUAL | 1.00 | {mp3_m[:40]}… | verified sutta window |")
            continue

        best: Optional[Tuple[float, str, float, float, str, List[str], str]] = None
        best_fail_score = -1.0
        for b in bundles:
            r = attempt_map_entry(entry, sid, b)
            if r is None:
                # track weakest fuzzy for diagnostics
                anchor, fuzzy_m = best_anchor_match(entry, b.idf, b.seg_texts, b.seg_tokens)
                if anchor and fuzzy_m.score > best_fail_score:
                    best_fail_score = fuzzy_m.score
                continue
            score, _mp3, _s0, _s1, _st, _a, _src = r
            if best is None or score > best[0]:
                best = r

        if best is None:
            missing += 1
            anchor_preview = ""
            for b in bundles:
                a, _ = best_anchor_match(entry, b.idf, b.seg_texts, b.seg_tokens)
                if a:
                    anchor_preview = " ".join(a[:14])
                    break
            rows.append(
                f"| {sid} | NO_MATCH ({len(bundles)} src) | {best_fail_score:.2f} | {anchor_preview} |"
            )
            continue

        score, mp3, start_s, end_s, status, anchor, src_lbl = best
        entry["aud_file"] = mp3
        entry["aud_start_s"] = round(start_s, 2)
        entry["aud_end_s"] = round(end_s, 2)
        mapped += 1
        if status == "WEAK":
            weak += 1
        rows.append(f"| {sid} | {status} | {score:.2f} | {src_lbl} | {' '.join(anchor[:14])} |")

    an2_path.write_text(json.dumps(an2, ensure_ascii=False, indent=2), encoding="utf-8")

    reorder = Path("reorder_an2.py")
    if reorder.exists():
        import runpy

        runpy.run_path(str(reorder), run_name="__main__")

    report = Path("audio_mapping_report_an2.md")
    src_list = ", ".join(b.segments_path.name for b in bundles)
    header = [
        "## AN2 audio mapping report",
        "",
        f"- segment sources ({len(bundles)}): **{src_list}**",
        f"- mapped: **{mapped}**",
        f"- skipped (no text fields or already mapped): **{skipped}**",
        f"- weak matches: **{weak}**",
        f"- misses: **{missing}**",
        "",
        "| sutta_id | status | score | source / anchor |",
        "|---|---:|---:|---|",
    ]
    report.write_text("\n".join(header + rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
