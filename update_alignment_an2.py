import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple


_STOPWORDS = {
    "a",
    "about",
    "all",
    "also",
    "am",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "being",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "doing",
    "don",
    "done",
    "down",
    "each",
    "etc",
    "for",
    "from",
    "get",
    "go",
    "had",
    "has",
    "have",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "him",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "just",
    "let",
    "like",
    "may",
    "me",
    "more",
    "most",
    "my",
    "no",
    "not",
    "of",
    "on",
    "one",
    "only",
    "or",
    "our",
    "out",
    "said",
    "say",
    "says",
    "she",
    "should",
    "so",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "will",
    "with",
    "would",
    "you",
    "your",
}


def _normalize_for_scoring(text: str) -> str:
    """
    Cleanup to reduce transcript/noise effects before tokenization.
    This is *not* canonical editing; it's only used for alignment scoring.
    """
    s = (text or "").lower()
    s = _strip_internal_prefix(s)
    # Remove common filler / artifacts seen in transcripts.
    s = re.sub(r"\betc(?:\s+etc)?\b", " ", s)
    s = re.sub(r"\buh+\b|\bum+\b|\ber+\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _tokens(text: str) -> List[str]:
    s = _normalize_for_scoring(text)
    toks = re.findall(r"[a-z]{2,}", s)
    return [t for t in toks if t not in _STOPWORDS]


def _dedupe_keep_order(xs: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in xs:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _strip_internal_prefix(sutta: str) -> str:
    # Remove leading internal numbering like "2.1.6" / "2.11.9"
    return re.sub(r"^\s*\d+(?:\.\d+)+\s*", "", (sutta or "").strip())


def _jaccard(a: List[str], b: List[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _score_from_sim(sim: float) -> int:
    # Tuned for paraphrase tolerance
    if sim >= 0.65:
        return 5
    if sim >= 0.50:
        return 4
    if sim >= 0.35:
        return 3
    if sim >= 0.20:
        return 2
    if sim >= 0.10:
        return 1
    return 0


def _bool_to_score(ok: bool) -> int:
    return 5 if ok else 0


def _chain_keywords(chain: Dict[str, Any]) -> str:
    items = chain.get("items") if isinstance(chain, dict) else None
    items = items if isinstance(items, list) else []
    # join as keywords (avoid punctuation/numbering differences dominating)
    return "\n".join(str(x or "").strip() for x in items if str(x or "").strip())


@dataclass
class AlignmentResult:
    scores: Dict[str, int]
    total: int
    max_total: int = 30
    needs_review: bool = True
    notes: str = ""


def compute_alignment(entry: Dict[str, Any]) -> AlignmentResult:
    sc_id = str(entry.get("sc_id") or "").strip()
    sc_url = str(entry.get("sc_url") or "").strip()
    aud_file = str(entry.get("aud_file") or "").strip()
    aud_start = float(entry.get("aud_start_s") or 0.0)
    aud_end = float(entry.get("aud_end_s") or 0.0)

    sutta = str(entry.get("sutta") or "")
    sutta_clean = _strip_internal_prefix(sutta)
    comm = str(entry.get("commentary") or "")
    sc_sutta = str(entry.get("sc_sutta") or "")

    # 1) source_ids_url
    source_ok = bool(sc_id) and bool(sc_url) and (sc_id.lower() in sc_url.lower())
    source_ids_url = _bool_to_score(source_ok)

    # 2) text_to_source (sutta vs sc_sutta)
    sim_ts = _jaccard(_dedupe_keep_order(_tokens(sutta_clean)), _dedupe_keep_order(_tokens(sc_sutta)))
    text_to_source = _score_from_sim(sim_ts)

    # 3) audio_segment (only structural check here; content match requires transcript)
    audio_ok = bool(aud_file) and (aud_end > aud_start) and (aud_start >= 0.0)
    audio_segment = _bool_to_score(audio_ok)

    # 4) commentary alignment (commentary vs (sutta+sc_sutta))
    chain = entry.get("chain") if isinstance(entry.get("chain"), dict) else {}
    chain_kw = _chain_keywords(chain)
    # Strengthen "on-topic" signal by scoring commentary primarily against chain keywords.
    # This avoids penalizing commentary that paraphrases the sutta but still tracks the intended theme.
    sim_comm_chain = _jaccard(
        _dedupe_keep_order(_tokens(comm)),
        _dedupe_keep_order(_tokens(chain_kw)),
    )
    kw_text = f"{chain_kw}\n\n{sutta_clean}\n\n{sc_sutta}"
    sim_comm_kw = _jaccard(_dedupe_keep_order(_tokens(comm)), _dedupe_keep_order(_tokens(kw_text)))
    sim_comm = max(sim_comm_chain, sim_comm_kw)
    commentary = _score_from_sim(sim_comm)

    # 5) chain alignment
    items = chain.get("items") if isinstance(chain, dict) else None
    items = items if isinstance(items, list) else []
    count_ok = isinstance(chain.get("count"), int) and chain.get("count") == len(items)
    # each item should be supported by token overlap somewhere
    support_tokens = set(_tokens(f"{sutta_clean}\n\n{comm}\n\n{sc_sutta}"))
    supported = 0
    for it in items[:10]:
        it_s = str(it or "").strip()
        if not it_s.strip():
            continue
        ws = _tokens(it_s)
        if not ws:
            continue
        overlap = sum(1 for w in ws if w in support_tokens) / max(1, len(ws))
        if overlap >= 0.70:
            supported += 1
    chain_score = 0
    if items:
        frac = supported / max(1, len(items))
        if count_ok and frac >= 1.0:
            chain_score = 5
        elif count_ok and frac >= 0.5:
            chain_score = 4
        elif frac > 0:
            chain_score = 3
        else:
            chain_score = 1 if count_ok else 0
    else:
        chain_score = 0

    # 6) boundaries
    boundaries_ok = bool(sutta_clean.strip()) and (comm == "" or comm.strip() != "")
    # penalize dangling obvious truncations
    bad_tail = sutta.strip().endswith((" thus:", " thus", " and then", " and then,", " and then."))
    boundaries = 5 if boundaries_ok and not bad_tail else (3 if boundaries_ok else 0)

    scores = {
        "source_ids_url": source_ids_url,
        "text_to_source": text_to_source,
        "audio_segment": audio_segment,
        "commentary": commentary,
        "chain": chain_score,
        "boundaries": boundaries,
    }
    total = sum(scores.values())

    # Review heuristic:
    # - always review if source ids are missing/invalid, or text-to-source very low
    # - or if commentary looks unrelated (when non-empty)
    # - or if total is low (ignoring commentary volatility)
    # If chain exists, require some chain overlap; otherwise fall back to kw overlap.
    has_chain_kw = bool(chain_kw.strip())
    comm_unrelated = bool(comm.strip()) and (
        (has_chain_kw and sim_comm_chain < 0.10 and commentary <= 1)
        or ((not has_chain_kw) and sim_comm < 0.10 and commentary <= 1)
    )
    total_no_comm = total - commentary
    needs_review = (
        (source_ids_url < 5)
        # Jaccard is conservative; treat 0–1 as strong mismatch, 2 as "ok but verify".
        or (text_to_source < 2)
        or comm_unrelated
        or (total_no_comm < 18)
    )

    notes = (
        f"Auto-scored v5: sim_text_to_source={sim_ts:.3f}, "
        f"sim_commentary_chain={sim_comm_chain:.3f}, sim_commentary_kw={sim_comm_kw:.3f}, "
        f"chain_supported={supported}/{len(items)}"
    )

    return AlignmentResult(scores=scores, total=total, needs_review=needs_review, notes=notes)


def main() -> None:
    path = Path("an2.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise TypeError("Expected top-level list")

    rows: List[Tuple[str, int, Dict[str, int], bool]] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        ar = compute_alignment(entry)
        entry["alignment"] = {
            "rubric_version": "align_v5",
            "scores_0_to_5": ar.scores,
            "total": ar.total,
            "max_total": ar.max_total,
            "needs_review": ar.needs_review,
            "notes": ar.notes,
        }
        rows.append((str(entry.get("sutta_id") or ""), ar.total, ar.scores, ar.needs_review))

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Keep ordering consistent if helper exists
    reorder = Path("reorder_an2.py")
    if reorder.exists():
        import runpy

        runpy.run_path(str(reorder), run_name="__main__")

    # Report
    rows_sorted = sorted(rows, key=lambda r: r[1])
    avg = sum(r[1] for r in rows) / max(1, len(rows))
    needs = sum(1 for r in rows if r[3])

    rep = Path("alignment_report_an2.md")
    lines = []
    lines.append("## AN2 alignment report")
    lines.append("")
    lines.append(f"- entries: **{len(rows)}**")
    lines.append(f"- avg_total: **{avg:.1f}/30**")
    lines.append(f"- needs_review: **{needs}/{len(rows)}**")
    lines.append("")
    lines.append("### Lowest totals")
    lines.append("")
    lines.append("| sutta_id | total | source | text | audio | comm | chain | bounds | needs_review |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|:---:|")
    for sid, total, sc, nr in rows_sorted[:10]:
        lines.append(
            f"| {sid} | {total} | {sc['source_ids_url']} | {sc['text_to_source']} | {sc['audio_segment']} | "
            f"{sc['commentary']} | {sc['chain']} | {sc['boundaries']} | {'Y' if nr else 'N'} |"
        )
    lines.append("")
    lines.append("### Full list (sorted by total)")
    lines.append("")
    lines.append("| sutta_id | total | needs_review |")
    lines.append("|---|---:|:---:|")
    for sid, total, _sc, nr in rows_sorted:
        lines.append(f"| {sid} | {total} | {'Y' if nr else 'N'} |")
    rep.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

