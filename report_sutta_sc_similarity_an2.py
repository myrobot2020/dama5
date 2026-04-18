import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z]{2,}", (text or "").lower())


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
    return re.sub(r"^\s*\d+(?:\.\d+)+\s*", "", (sutta or "").strip())


def _jaccard(a: List[str], b: List[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def main() -> None:
    data = json.loads(Path("an2.json").read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise TypeError("Expected list in an2.json")

    rows: List[Tuple[float, str, str, str]] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        sid = str(entry.get("sutta_id") or "")
        sutta = _strip_internal_prefix(str(entry.get("sutta") or ""))
        sc = str(entry.get("sc_sutta") or "")
        sim = _jaccard(_dedupe_keep_order(_tokens(sutta)), _dedupe_keep_order(_tokens(sc)))
        sc_id = str(entry.get("sc_id") or "")
        rows.append((sim, sid, sc_id, str(entry.get("sc_url") or "")))

    rows.sort(key=lambda r: r[0])
    avg = sum(r[0] for r in rows) / max(1, len(rows))

    out = Path("sutta_sc_similarity_an2.md")
    lines = []
    lines.append("## AN2 sutta↔sc_sutta similarity")
    lines.append("")
    lines.append(f"- entries: **{len(rows)}**")
    lines.append(f"- avg_jaccard: **{avg:.3f}**")
    lines.append("")
    lines.append("| sutta_id | sc_id | jaccard | sc_url |")
    lines.append("|---|---|---:|---|")
    for sim, sid, sc_id, sc_url in rows:
        lines.append(f"| {sid} | {sc_id} | {sim:.3f} | {sc_url} |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

