import csv
import json
import re
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

# Sutta/commentary split rules (same as AN4)
SUTTA_END_RE = re.compile(r"(?i)\b(?:that'?s\s+)?the\s+end\s+of\s+the\s+sut(?:ta|a|e|i)\b")
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
    return WORD_RE.sub(lambda m: str(NUM_WORD[m.group(1).lower()]), text)


def _parse_spoken_3digit(nums: list[int]) -> int | None:
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


def normalize_spoken_ids(text: str, volume: int) -> str:
    """
    Normalizes:
    - number words -> digit tokens
    - numeric "point" -> ".": 5 point 3 point 26 -> 5.3.26
    - spoken ids: "five point three point one ninety four" -> 5.3.194 (conservative)
    """
    t = _replace_number_words_with_int_tokens(text)
    t = re.sub(r"(?i)(?<=\d)\s*point\s*(?=\d)", ".", t)

    tokens = re.split(r"(\s+)", t)  # keep whitespace

    def is_ws(tok: str) -> bool:
        return tok.isspace()

    def is_num(tok: str) -> bool:
        return tok.isdigit()

    def is_point(tok: str) -> bool:
        return tok.lower() == "point"

    out: list[str] = []
    i = 0
    vtok = str(volume)
    while i < len(tokens):
        tok = tokens[i]
        if tok == vtok:
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
                                b = _parse_spoken_3digit(b_nums[:4])
                        if b is not None:
                            out.append(f"{volume}.{a}.{b}")
                            i = k
                            continue

        out.append(tok)
        i += 1

    s = "".join(out)
    s = re.sub(r"(\d)\s*\.\s*(\d)", r"\1.\2", s)
    return s


def split_sutta_commentary(block: str) -> tuple[str, str, str]:
    """
    Returns (sutta, commentary, used_rule).
    used_rule: end_marker | cue_marker | none
    """
    blk = block.strip()
    if not blk:
        return "", "", "none"

    m_end = SUTTA_END_RE.search(blk)
    if m_end:
        cut = m_end.end()
        return blk[:cut].strip(), blk[cut:].strip(), "end_marker"

    MIN_PREFIX = 200
    m_comm = COMMENTARY_START_RE.search(blk)
    if m_comm and m_comm.start() >= MIN_PREFIX:
        cut = m_comm.start()
        return blk[:cut].strip(), blk[cut:].strip(), "cue_marker"

    return blk, "", "none"


def strip_leading_sutta_id(sutta_text: str, sutta_id: str) -> str:
    """
    Remove a leading sutta id token like '5.1.2' from the beginning of sutta text.
    Leaves other occurrences untouched.
    """
    if not sutta_text:
        return sutta_text
    # common patterns: "5.1.2 ...", "5.1.2. ...", "5.1.2 - ...", "5.1.2: ..."
    pat = re.compile(rf"^\s*{re.escape(sutta_id)}(?:\s*[\.\-:])?\s+", re.I)
    return pat.sub("", sutta_text, count=1).lstrip()


def file_name_for_id(sutta_id: str) -> str:
    base = re.sub(r"[^0-9.]+", "_", sutta_id).strip("_") or "unknown"
    return f"{base}.json"


def _preview_stats(text: str) -> tuple[int, str, str]:
    words = [w for w in re.split(r"\s+", text.strip()) if w]
    if not words:
        return 0, "", ""
    return len(words), " ".join(words[:3]), " ".join(words[-3:])


@dataclass(frozen=True)
class Outputs:
    suttas_written: int
    commentary_missing: int
    csv_path: Path


def write_unified_bounds_csv(
    *,
    repo_root: Path,
    out_csv: Path,
    # Existing rows may not have all columns; we preserve what we can.
    drop_prefixes: tuple[str, ...],
    new_rows: list[dict[str, str]],
) -> Path:
    header = [
        # identity + json path
        "sutta_id",
        "source_path",
        # preview stats
        "sutta_word_count",
        "sutta_first3",
        "sutta_last3",
        "commentary_word_count",
        "commentary_first3",
        "commentary_last3",
        # deterministic boundaries in normalized source text
        "source_txt_path",
        "normalized_block_start",
        "normalized_block_end",
        "sutta_start",
        "sutta_end",
        "commentary_start",
        "commentary_end",
        "used_rule",
    ]

    rows: list[dict[str, str]] = []
    if out_csv.exists():
        with out_csv.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                sp = (r.get("source_path") or "").replace("/", "\\").lower()
                if any(sp.startswith(p) for p in drop_prefixes):
                    continue
                rows.append(r)
    else:
        # seed from the old summary csv if present
        seed = repo_root / "sutta_bounds_an_folders.csv"
        if seed.exists():
            with seed.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    sp = (r.get("source_path") or "").replace("/", "\\").lower()
                    if any(sp.startswith(p) for p in drop_prefixes):
                        continue
                    rows.append(r)

    rows.extend(new_rows)

    # Write. If the file is locked (Excel), fail loudly rather than creating extra CSVs,
    # since the workflow wants only this single CSV.
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: (r.get(k) or "") for k in header})
    return out_csv


def extract_book(
    *,
    repo_root: Path,
    source_txt_path: Path,
    volume: int,
    out_prefix: str,
    out_csv_name: str = "sutta_tag.csv",
) -> Outputs:
    raw = source_txt_path.read_text(encoding="utf-8", errors="replace")
    normalized = normalize_spoken_ids(raw, volume=volume)

    id_re = re.compile(rf"(?<!\d){volume}\.\d+(?:\.\d+)*")
    matches = list(id_re.finditer(normalized))

    # Slice blocks with spans
    blocks_with_spans: list[tuple[str, int, int]] = []
    for i, m in enumerate(matches):
        sid = m.group(0)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(normalized)
        blocks_with_spans.append((sid, start, end))

    # Merge consecutive duplicate ids (extend span)
    merged_spans: list[tuple[str, int, int]] = []
    for sid, start, end in blocks_with_spans:
        if merged_spans and merged_spans[-1][0] == sid:
            merged_spans[-1] = (sid, merged_spans[-1][1], end)
        else:
            merged_spans.append((sid, start, end))

    # De-dupe non-consecutive repeats by keeping the first occurrence
    wrote: set[str] = set()
    out_dir = repo_root / out_prefix / "suttas"
    out_dir.mkdir(parents=True, exist_ok=True)
    for p in out_dir.glob("*.json"):
        if p.name == "_index.json":
            continue
        p.unlink()

    index: list[dict[str, str]] = []
    new_csv_rows: list[dict[str, str]] = []
    missing_commentary = 0
    written = 0

    for sid, start, end in merged_spans:
        if sid in wrote:
            continue
        wrote.add(sid)

        block = normalized[start:end]
        # compute stripped span in normalized text
        if block.strip():
            leading = len(block) - len(block.lstrip())
            trailing_len = len(block.rstrip())
            abs_block_start = start + leading
            abs_block_end = start + trailing_len
            block_stripped = block.strip()
        else:
            abs_block_start = start
            abs_block_end = start
            block_stripped = ""

        sutta_txt, comm_txt, used_rule = split_sutta_commentary(block_stripped)
        sutta_txt = strip_leading_sutta_id(sutta_txt, sid)
        if not comm_txt.strip():
            missing_commentary += 1

        out_path = out_dir / file_name_for_id(sid)
        out_obj = {"sutta_id": sid, "sutta": sutta_txt, "commentary": comm_txt}
        out_path.write_text(json.dumps(out_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written += 1
        index.append({"path": f"{out_prefix}/suttas/{out_path.name}"})

        # Offsets for sutta/commentary relative to stripped block
        s0 = abs_block_start
        # Find cut point again for offsets (based on used_rule)
        if used_rule == "end_marker":
            m_end = SUTTA_END_RE.search(block_stripped)
            cut = m_end.end() if m_end else len(sutta_txt)
        elif used_rule == "cue_marker":
            m_comm = COMMENTARY_START_RE.search(block_stripped)
            cut = m_comm.start() if m_comm else len(sutta_txt)
        else:
            cut = len(block_stripped)

        sutta_start = s0
        sutta_end = s0 + cut
        comm_start = s0 + cut
        comm_end = s0 + len(block_stripped)

        s_n, s_first, s_last = _preview_stats(sutta_txt)
        c_n, c_first, c_last = _preview_stats(comm_txt)

        new_csv_rows.append(
            {
                "sutta_id": sid,
                "source_path": f"{out_prefix}\\suttas\\{out_path.name}",
                "sutta_word_count": str(s_n),
                "sutta_first3": s_first,
                "sutta_last3": s_last,
                "commentary_word_count": str(c_n),
                "commentary_first3": c_first,
                "commentary_last3": c_last,
                "source_txt_path": str(source_txt_path),
                "normalized_block_start": str(abs_block_start),
                "normalized_block_end": str(abs_block_end),
                "sutta_start": str(sutta_start),
                "sutta_end": str(sutta_end),
                "commentary_start": str(comm_start),
                "commentary_end": str(comm_end),
                "used_rule": used_rule,
            }
        )

    (out_dir / "_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    out_csv = repo_root / out_csv_name
    out_csv = write_unified_bounds_csv(
        repo_root=repo_root,
        out_csv=out_csv,
        drop_prefixes=(f"{out_prefix}\\".lower(),),
        new_rows=new_csv_rows,
    )

    return Outputs(suttas_written=written, commentary_missing=missing_commentary, csv_path=out_csv)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src = repo_root / "raw2" / "AN_Book_05.txt"
    outs = extract_book(repo_root=repo_root, source_txt_path=src, volume=5, out_prefix="an5")
    print(f"Wrote {outs.suttas_written} per-sutta JSON files to an5/suttas.")
    print(f"Commentary missing/empty: {outs.commentary_missing} of {outs.suttas_written}")
    print(f"Updated: {outs.csv_path}")


if __name__ == "__main__":
    main()

