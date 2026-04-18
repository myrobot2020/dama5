import argparse
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

# Sutta/commentary split rules (same as Books 5/6)
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
    t = _replace_number_words_with_int_tokens(text)
    # numeric "point" -> ".": 7 point 3 point 26 -> 7.3.26
    t = re.sub(r"(?i)(?<=\d)\s*point\s*(?=\d)", ".", t)

    tokens = re.split(r"(\s+)", t)

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
    if not sutta_text:
        return sutta_text
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
    out_prefix: str


def update_sutta_tag_csv(*, repo_root: Path, out_prefix: str, rows_to_add: list[dict[str, str]], csv_name: str) -> Path:
    csv_path = repo_root / csv_name
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

    existing: list[dict[str, str]] = []
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                sp = (r.get("source_path") or "").replace("/", "\\").lower()
                if sp.startswith(f"{out_prefix}\\".lower()):
                    continue
                existing.append(r)

    existing.extend(rows_to_add)

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        for r in existing:
            writer.writerow({k: (r.get(k) or "") for k in header})

    return csv_path


def default_source_path(repo_root: Path, volume: int) -> Path:
    return repo_root / "raw2" / f"AN_Book_{volume:02d}.txt"


def extract_book(*, repo_root: Path, source_txt_path: Path, volume: int, out_prefix: str, csv_name: str) -> Outputs:
    raw = source_txt_path.read_text(encoding="utf-8", errors="replace")
    normalized = normalize_spoken_ids(raw, volume=volume)

    id_re = re.compile(rf"(?<!\d){volume}\.\d+(?:\.\d+)*")
    matches = list(id_re.finditer(normalized))

    blocks_with_spans: list[tuple[str, int, int]] = []
    for i, m in enumerate(matches):
        sid = m.group(0)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(normalized)
        blocks_with_spans.append((sid, start, end))

    # Merge consecutive duplicates (extend span)
    merged_spans: list[tuple[str, int, int]] = []
    for sid, start, end in blocks_with_spans:
        if merged_spans and merged_spans[-1][0] == sid:
            merged_spans[-1] = (sid, merged_spans[-1][1], end)
        else:
            merged_spans.append((sid, start, end))

    out_dir = repo_root / out_prefix / "suttas"
    out_dir.mkdir(parents=True, exist_ok=True)
    for p in out_dir.glob("*.json"):
        if p.name == "_index.json":
            continue
        p.unlink()

    wrote: set[str] = set()
    index: list[dict[str, str]] = []
    csv_rows: list[dict[str, str]] = []
    missing_commentary = 0
    written = 0

    for sid, start, end in merged_spans:
        if sid in wrote:
            continue
        wrote.add(sid)

        block = normalized[start:end].strip()
        sutta_txt, comm_txt, _rule = split_sutta_commentary(block)
        sutta_txt = strip_leading_sutta_id(sutta_txt, sid)
        if not comm_txt.strip():
            missing_commentary += 1

        out_path = out_dir / file_name_for_id(sid)
        out_obj = {"sutta_id": sid, "sutta": sutta_txt, "commentary": comm_txt}
        out_path.write_text(json.dumps(out_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written += 1
        index.append({"path": f"{out_prefix}/suttas/{out_path.name}"})

        s_n, s_first, s_last = _preview_stats(sutta_txt)
        c_n, c_first, c_last = _preview_stats(comm_txt)
        csv_rows.append(
            {
                "sutta_id": sid,
                "source_path": f"{out_prefix}\\suttas\\{out_path.name}",
                "sutta_word_count": str(s_n),
                "sutta_first3": s_first,
                "sutta_last3": s_last,
                "commentary_word_count": str(c_n),
                "commentary_first3": c_first,
                "commentary_last3": c_last,
            }
        )

    (out_dir / "_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    update_sutta_tag_csv(repo_root=repo_root, out_prefix=out_prefix, rows_to_add=csv_rows, csv_name=csv_name)

    return Outputs(suttas_written=written, commentary_missing=missing_commentary, out_prefix=out_prefix)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--volume", type=int, required=True)
    ap.add_argument("--source", type=str, default="")
    ap.add_argument("--out-prefix", type=str, default="")
    ap.add_argument("--csv", type=str, default="sutta_tag.csv")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    volume = args.volume
    source_txt_path = Path(args.source) if args.source else default_source_path(repo_root, volume)
    out_prefix = args.out_prefix or f"an{volume}"

    outs = extract_book(
        repo_root=repo_root,
        source_txt_path=source_txt_path,
        volume=volume,
        out_prefix=out_prefix,
        csv_name=args.csv,
    )
    print(f"volume={volume} wrote={outs.suttas_written} missing_commentary={outs.commentary_missing} out_prefix={outs.out_prefix}")


if __name__ == "__main__":
    main()

