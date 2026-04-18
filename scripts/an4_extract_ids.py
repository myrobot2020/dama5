import json
import re
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
 
 
NUM_WORD = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "hundred": 100,
}
 
WORD_RE = re.compile(r"\b(" + "|".join(NUM_WORD.keys()) + r")\b", re.I)
ID_RE = re.compile(r"(?<!\d)4\.\d+(?:\.\d+)*")
SUTTA_END_RE = re.compile(r"(?i)\b(?:that'?s\s+)?the\s+end\s+of\s+the\s+sut(?:ta|a|e|i)\b")
# Fallback cues for where spoken commentary typically begins (when no explicit "end of sutta" phrase
# appears between suttas). These are intentionally conservative/high-signal phrases that show up
# in the existing AN book transcripts.
COMMENTARY_START_RE = re.compile(
    r"(?i)\b("
    r"i\s+just\s+stopped\s+here"
    r"|i'?ll\s+just\s+stop\s+here"
    r"|so\s+here\s+(?:the\s+)?buddha"
    r"|so\s+in\s+this\s+sut(?:ta|a|e|i)"
    r"|this\s+sut(?:ta|a|e|i)\s+is"
    r"|this\s+is\s+one\s+of\s+those\s+sut(?:tas|as|es|is)"
    r"|i\s+will\s+just\s+stop\s+here"
    r")\b"
)
 
 
def _replace_number_words_with_int_tokens(text: str) -> str:
    # Keep it simple: only replace known number words with digit tokens.
    return WORD_RE.sub(lambda m: str(NUM_WORD[m.group(1).lower()]), text)
 
 
def _parse_spoken_3digit(nums: list[int]) -> int | None:
    # Handles common transcript patterns:
    # - "one ninety four" -> [1, 90, 4] -> 194
    # - "one hundred ninety four" -> [1, 100, 90, 4] -> 194
    if len(nums) == 1:
        return nums[0]
    if len(nums) == 3 and nums[0] < 10 and 10 <= nums[1] < 100 and nums[1] % 10 == 0 and nums[2] < 10:
        return nums[0] * 100 + nums[1] + nums[2]
    if (
        len(nums) == 4
        and nums[0] < 10
        and nums[1] == 100
        and 10 <= nums[2] < 100
        and nums[2] % 10 == 0
        and nums[3] < 10
    ):
        return nums[0] * 100 + nums[2] + nums[3]
    return None
 
 
def normalize_spoken_an4_ids(text: str) -> str:
    """
    Converts forms like:
      "four point twenty point one ninety four" -> "4.20.194"
    conservatively, without trying to parse arbitrary English numbers.
    """
    t = _replace_number_words_with_int_tokens(text)

    # Normalize numeric "point" usage everywhere (not just AN4 ids):
    #   "4 point 3 point 25" -> "4.3.25"
    # This helps downstream sutta-id detection.
    t = re.sub(r"(?i)(?<=\d)\s*point\s*(?=\d)", ".", t)
 
    # Tokenize preserving whitespace so we can rebuild exact text.
    tokens = re.split(r"(\\s+)", t)
 
    def is_ws(tok: str) -> bool:
        return tok.isspace()
 
    def is_num(tok: str) -> bool:
        return tok.isdigit()
 
    def is_point(tok: str) -> bool:
        return tok.lower() == "point"
 
    out: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "4":
            j = i + 1
            while j < len(tokens) and is_ws(tokens[j]):
                j += 1
            if j < len(tokens) and is_point(tokens[j]):
                j += 1
                while j < len(tokens) and is_ws(tokens[j]):
                    j += 1
                if j < len(tokens) and is_num(tokens[j]):
                    a = int(tokens[j])
                    j += 1
                    while j < len(tokens) and is_ws(tokens[j]):
                        j += 1
                    if j < len(tokens) and is_point(tokens[j]):
                        j += 1
                        while j < len(tokens) and is_ws(tokens[j]):
                            j += 1
 
                        # Gather number tokens for B until a non-number token.
                        b_nums: list[int] = []
                        k = j
                        while k < len(tokens):
                            if is_ws(tokens[k]):
                                k += 1
                                continue
                            if is_num(tokens[k]):
                                b_nums.append(int(tokens[k]))
                                k += 1
                                continue
                            break
 
                        b: int | None = None
                        if b_nums:
                            if len(b_nums) == 1:
                                b = b_nums[0]
                            else:
                                # Try common 3- or 4-token hundreds patterns.
                                b = _parse_spoken_3digit(b_nums[:4])
 
                        if b is not None:
                            out.append(f"4.{a}.{b}")
                            i = k
                            continue
 
        out.append(tok)
        i += 1
 
    s = "".join(out)
    # Cleanup spacing around dots if any were introduced elsewhere.
    s = re.sub(r"(\\d)\\s*\\.\\s*(\\d)", r"\\1.\\2", s)
    return s
 
 
def extract_ordered_unique_ids(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in ID_RE.finditer(text):
        sid = m.group(0)
        if sid in seen:
            continue
        seen.add(sid)
        out.append(sid)
    return out
 
 
def file_name_for_id(sutta_id: str) -> str:
    base = re.sub(r"[^0-9.]+", "_", sutta_id).strip("_") or "unknown"
    return f"{base}.json"
 
 
@dataclass(frozen=True)
class Outputs:
    sutta_ids_txt: Path
    suttas_index_json: Path
    suttas_written: int
    commentary_missing: int
    bounds_offsets_csv: Path


def _preview_stats(text: str) -> tuple[int, str, str]:
    words = [w for w in re.split(r"\s+", text.strip()) if w]
    if not words:
        return 0, "", ""
    first = " ".join(words[:3])
    last = " ".join(words[-3:])
    return len(words), first, last


def update_bounds_csv(repo_root: Path) -> Path:
    """
    Update repo_root/sutta_bounds_an_folders.csv by replacing any existing an4 rows
    and appending fresh rows derived from an4/suttas/*.json.
    """
    csv_path = repo_root / "sutta_bounds_an_folders.csv"
    if not csv_path.exists():
        raise FileNotFoundError(str(csv_path))

    header = [
        "sutta_id",
        "source_path",
        "sutta_word_count",
        "sutta_first3",
        "sutta_last3",
        "commentary_word_count",
        "commentary_first3",
        "commentary_last3",
    ]

    # Read existing rows, drop any an4 entries.
    rows: list[dict[str, str]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            sp = (r.get("source_path") or "").replace("/", "\\")
            if sp.lower().startswith("an4\\"):
                continue
            rows.append(r)

    # Build fresh an4 rows.
    an4_dir = repo_root / "an4" / "suttas"
    for p in sorted(an4_dir.glob("*.json")):
        if p.name == "_index.json":
            continue
        obj = json.loads(p.read_text(encoding="utf-8"))
        sid = obj.get("sutta_id", "")
        sutta = obj.get("sutta", "") or ""
        comm = obj.get("commentary", "") or ""

        s_n, s_first, s_last = _preview_stats(sutta)
        c_n, c_first, c_last = _preview_stats(comm)

        rows.append(
            {
                "sutta_id": sid,
                "source_path": f"an4\\suttas\\{p.name}",
                "sutta_word_count": str(s_n),
                "sutta_first3": s_first,
                "sutta_last3": s_last,
                "commentary_word_count": str(c_n),
                "commentary_first3": c_first,
                "commentary_last3": c_last,
            }
        )

    # Write back in canonical column order.
    try:
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            for r in rows:
                writer.writerow({k: (r.get(k) or "") for k in header})
        return csv_path
    except PermissionError:
        # Common on Windows if the CSV is open in Excel. Write a new file instead.
        alt = repo_root / "sutta_bounds_an_folders.updated.csv"
        with alt.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            for r in rows:
                writer.writerow({k: (r.get(k) or "") for k in header})
        return alt


def write_bounds_offsets_csv(
    *,
    repo_root: Path,
    source_txt_path: Path,
    normalized_text: str,
    merged_blocks_with_spans: list[tuple[str, int, int]],
    out_name: str = "sutta_bounds_with_offsets.csv",
) -> Path:
    """
    Write a CSV that records deterministic boundaries for sutta/commentary
    for each sutta_id, as character offsets into the *normalized_text*.

    This is intended for future books so the split can be reproduced exactly.
    """
    out_path = repo_root / out_name
    header = [
        "sutta_id",
        "source_txt_path",
        "normalized_block_start",
        "normalized_block_end",
        "sutta_start",
        "sutta_end",
        "commentary_start",
        "commentary_end",
        "used_rule",  # end_marker | cue_marker | none
    ]

    def split_with_offsets(block: str) -> tuple[int, int, int, int, str]:
        # returns (sutta_start, sutta_end, comm_start, comm_end, used_rule) relative to block start
        blk = block.strip()
        if not blk:
            return 0, 0, 0, 0, "none"

        m_end = SUTTA_END_RE.search(blk)
        if m_end:
            cut = m_end.end()
            # sutta: [0, cut), comm: [cut, len)
            return 0, cut, cut, len(blk), "end_marker"

        MIN_PREFIX = 200
        m_comm = COMMENTARY_START_RE.search(blk)
        if m_comm and m_comm.start() >= MIN_PREFIX:
            cut = m_comm.start()
            return 0, cut, cut, len(blk), "cue_marker"

        return 0, len(blk), len(blk), len(blk), "none"

    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()

        wrote: set[str] = set()
        for sid, start, end in merged_blocks_with_spans:
            if sid in wrote:
                continue
            wrote.add(sid)
            block = normalized_text[start:end]
            # Use the same trimming as when writing JSONs so offsets correspond to the text
            block_stripped = block.strip()
            # Adjust start/end for the strip so offsets point to the same substring
            # inside normalized_text.
            if block_stripped:
                leading = len(block) - len(block.lstrip())
                trailing = len(block.rstrip())
                abs_block_start = start + leading
                abs_block_end = start + trailing
            else:
                abs_block_start = start
                abs_block_end = start

            rel_s0, rel_s1, rel_c0, rel_c1, used_rule = split_with_offsets(block_stripped)

            writer.writerow(
                {
                    "sutta_id": sid,
                    "source_txt_path": str(source_txt_path),
                    "normalized_block_start": str(abs_block_start),
                    "normalized_block_end": str(abs_block_end),
                    "sutta_start": str(abs_block_start + rel_s0),
                    "sutta_end": str(abs_block_start + rel_s1),
                    "commentary_start": str(abs_block_start + rel_c0),
                    "commentary_end": str(abs_block_start + rel_c1),
                    "used_rule": used_rule,
                }
            )

    return out_path
 
 
def split_sutta_commentary(block: str) -> tuple[str, str]:
    """
    Split a per-sutta text slice into (sutta, commentary).

    Priority:
    1) If we see an explicit "end of the sutta" marker, everything after becomes commentary.
    2) Otherwise, fall back to a set of common commentary-start cues and split there.
    3) If neither is present, return (block, "").
    """
    blk = block.strip()
    if not blk:
        return "", ""

    m_end = SUTTA_END_RE.search(blk)
    if m_end:
        cut = m_end.end()
        return blk[:cut].strip(), blk[cut:].strip()

    # Heuristic split: avoid splitting too early on intros like "so now we come...".
    MIN_PREFIX = 200
    m_comm = COMMENTARY_START_RE.search(blk)
    if m_comm and m_comm.start() >= MIN_PREFIX:
        cut = m_comm.start()
        return blk[:cut].strip(), blk[cut:].strip()

    return blk, ""


def write_outputs(repo_root: Path, ids: Iterable[str], normalized_text: str) -> Outputs:
    ids = list(ids)
    an4_dir = repo_root / "an4"
    out_dir = an4_dir / "suttas"
    out_dir.mkdir(parents=True, exist_ok=True)
 
    sutta_ids_txt = an4_dir / "sutta_ids.txt"
    sutta_ids_txt.write_text("\n".join(ids) + ("\n" if ids else ""), encoding="utf-8")
 
    # Clean previously generated per-sutta files (keep directory and _index.json)
    for p in out_dir.glob("*.json"):
        if p.name == "_index.json":
            continue
        p.unlink()

    # Slice into per-sutta blocks using positions in normalized text
    matches = list(ID_RE.finditer(normalized_text))
    blocks: list[tuple[str, str]] = []
    blocks_with_spans: list[tuple[str, int, int]] = []
    for i, m in enumerate(matches):
        sid = m.group(0)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(normalized_text)
        blocks.append((sid, normalized_text[start:end].strip()))
        blocks_with_spans.append((sid, start, end))

    # De-dupe consecutive identical IDs by merging blocks (speaker sometimes repeats)
    merged: list[tuple[str, str]] = []
    merged_with_spans: list[tuple[str, int, int]] = []
    for sid, blk in blocks:
        if merged and merged[-1][0] == sid:
            merged[-1] = (sid, (merged[-1][1] + "\n" + blk).strip())
        else:
            merged.append((sid, blk))
    for sid, start, end in blocks_with_spans:
        if merged_with_spans and merged_with_spans[-1][0] == sid:
            # extend end span for consecutive duplicate ids
            merged_with_spans[-1] = (sid, merged_with_spans[-1][1], end)
        else:
            merged_with_spans.append((sid, start, end))

    written = 0
    missing_commentary = 0
    index = []
    wrote_ids: set[str] = set()
    for sid, blk in merged:
        # If the same sutta id appears again later (non-consecutively), don't double-count or
        # produce duplicate index entries; keep the first slice.
        if sid in wrote_ids:
            continue
        wrote_ids.add(sid)
        sutta_txt, comm_txt = split_sutta_commentary(blk)

        out_path = out_dir / file_name_for_id(sid)
        obj = {"sutta_id": sid, "sutta": sutta_txt, "commentary": comm_txt}
        out_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written += 1
        if not comm_txt.strip():
            missing_commentary += 1
        index.append({"path": f"an4/suttas/{out_path.name}"})

    suttas_index_json = out_dir / "_index.json"
    suttas_index_json.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Write deterministic boundary CSV (offsets into normalized text) for future reuse.
    src_txt = Path(r"c:\\Users\\ADMIN\\Desktop\\dama3\\raw2\\AN_Book_04.txt")
    bounds_offsets_csv = write_bounds_offsets_csv(
        repo_root=repo_root,
        source_txt_path=src_txt,
        normalized_text=normalized_text,
        merged_blocks_with_spans=merged_with_spans,
    )

    return Outputs(
        sutta_ids_txt=sutta_ids_txt,
        suttas_index_json=suttas_index_json,
        suttas_written=written,
        commentary_missing=missing_commentary,
        bounds_offsets_csv=bounds_offsets_csv,
    )
 
 
def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
 
    # Default matches your current AN4 source location.
    src_path = Path(r"c:\\Users\\ADMIN\\Desktop\\dama3\\raw2\\AN_Book_04.txt")
    raw = src_path.read_text(encoding="utf-8", errors="replace")
 
    normalized = normalize_spoken_an4_ids(raw)
    ids = extract_ordered_unique_ids(normalized)
    outs = write_outputs(repo_root=repo_root, ids=ids, normalized_text=normalized)
    csv_out = update_bounds_csv(repo_root=repo_root)
 
    print(f"Found {len(ids)} unique AN4 sutta ids.")
    if ids:
        print(f"First: {ids[0]}")
        print(f"Last:  {ids[-1]}")
    print(f"Wrote: {outs.sutta_ids_txt}")
    print(f"Wrote: {outs.suttas_index_json}")
    print(f"Wrote {outs.suttas_written} per-sutta JSON files.")
    print(f"Commentary missing/empty: {outs.commentary_missing} of {outs.suttas_written}")
    print(f"Updated: {csv_out}")
    print(f"Wrote bounds offsets: {outs.bounds_offsets_csv}")
 
 
if __name__ == "__main__":
    main()
