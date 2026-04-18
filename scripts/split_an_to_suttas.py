import json
import re
from pathlib import Path


def _extract_braced_object(text: str, start_idx: int) -> str | None:
    """Given text and index at '{', returns the full balanced {...} substring."""
    if start_idx < 0 or start_idx >= len(text) or text[start_idx] != "{":
        return None
    i = start_idx
    depth = 0
    in_str = False
    esc = False
    while i < len(text):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start_idx : i + 1]
        i += 1
    return None


def extract_blocks(text: str, id_key: str) -> list[tuple[str, str]]:
    """
    Extracts the nearest surrounding {...} block for each occurrence of `"id_key": "..."`.
    This is tolerant of invalid JSON elsewhere in the file.
    """
    out: list[tuple[str, str]] = []

    # Require the key to begin a JSON-ish key position (start of text, after '{', '[', ',' or whitespace),
    # so we don't accidentally match `suttaid` text that appears inside malformed strings.
    key_re = re.compile(
        rf"(?:^|[\s\{{\[,])\"{re.escape(id_key)}\"\s*:\s*\"([^\"]+)\"",
        flags=re.M,
    )

    matches = list(key_re.finditer(text))

    # `an1.json` contains broken quoting/newlines inside strings, which makes brace matching unreliable
    # if we try to respect string boundaries. For `suttaid`, use a positional slice between successive
    # ids instead (works well for an array of objects).
    if id_key.lower() == "suttaid" and matches:
        for i, m in enumerate(matches):
            sid = m.group(1)
            start = text.rfind("{", 0, m.start())
            if start == -1:
                continue
            end = len(text)
            if i + 1 < len(matches):
                next_start = text.rfind("{", 0, matches[i + 1].start())
                if next_start != -1:
                    end = next_start

            block = text[start:end].strip()
            # Trim trailing separators from the array (commas/newlines)
            block = re.sub(r",\s*\Z", "", block)
            # Ensure it ends at a closing brace for this object
            last_brace = block.rfind("}")
            if last_brace != -1:
                block = block[: last_brace + 1]
            out.append((sid, block))
    else:
        for m in matches:
            sid = m.group(1)

            start = text.rfind("{", 0, m.start())
            if start == -1:
                continue

            i = start
            depth = 0
            in_str = False
            esc = False
            while i < len(text):
                ch = text[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                else:
                    if ch == '"':
                        in_str = True
                    elif ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            i += 1
                            break
                i += 1

            block = text[start:i]
            out.append((sid, block))

    # Fallback for a known malformed pattern in `an1.json` where the sutta id appears as
    # `": "AN 1.6.8"` (missing a proper key) and the real `"suttaid"` key is corrupted.
    if id_key.lower() == "suttaid":
        fallback_re = re.compile(
            r'(?:^|[\s\{\[,])"\s*:\s*"AN\s*([0-9.]+)"',
            flags=re.M,
        )
        for m in fallback_re.finditer(text):
            sid = f"AN {m.group(1)}"
            start = text.rfind("{", 0, m.start())
            if start == -1:
                continue

            i = start
            depth = 0
            in_str = False
            esc = False
            while i < len(text):
                ch = text[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                else:
                    if ch == '"':
                        in_str = True
                    elif ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            i += 1
                            break
                i += 1

            block = text[start:i]
            out.append((sid, block))

    seen: set[str] = set()
    uniq: list[tuple[str, str]] = []
    for sid, block in out:
        if sid in seen:
            continue
        seen.add(sid)
        uniq.append((sid, block))

    return uniq


def normalize_id(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^AN\s*", "", s, flags=re.I).strip()
    return s


def file_name_for_id(sutta_id: str) -> str:
    # Keep dot-separated numeric id. Replace anything else with underscores.
    base = re.sub(r"[^0-9.]+", "_", sutta_id).strip("_") or "unknown"
    return f"{base}.json"


def _extract_string_values(block: str, key: str) -> list[str]:
    """
    Tolerant extraction of values for `"key": "..."` even when the JSON is malformed.
    Captures until the next line that looks like a JSON key at the same or lower indentation.
    """
    values: list[str] = []
    # Find occurrences of "key": "
    for m in re.finditer(rf"\"{re.escape(key)}\"\s*:\s*\"", block):
        start = m.end()
        # Stop at:
        # - next JSON-ish key line
        # - OR an object boundary like `}, {` / `}]` (common when the source file is malformed)
        stop_m = re.search(
            r"\n\s*(?:\"[^\"]+\"\s*:|\}\s*,\s*\{|\}\s*\]|\}\s*,\s*\Z|\]\s*,\s*\Z)",
            block[start:],
        )
        end = start + (stop_m.start() if stop_m else len(block) - start)
        raw = block[start:end]
        # Trim trailing commas/quotes/newlines commonly left behind
        raw = raw.rstrip().rstrip(",").rstrip()
        # If it ends with an unbalanced quote because of malformed source, just strip one
        if raw.endswith('"'):
            raw = raw[:-1]
        # Strip common malformed tails
        raw = re.sub(r'"\s*\}\s*,?\s*\Z', "", raw).rstrip()
        raw = re.sub(r"\}\s*,\s*\Z", "", raw).rstrip()
        values.append(raw.strip())
    return values


def _try_parse_json_object(block: str) -> dict | None:
    try:
        obj = json.loads(block)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _extract_chain(block: str) -> dict | None:
    # Fast path: valid JSON
    obj = _try_parse_json_object(block)
    if obj and isinstance(obj.get("chain"), dict):
        return obj["chain"]

    # Fallback: brace-match chain object
    m = re.search(r"\"chain\"\s*:\s*\{", block)
    if not m:
        return None
    start_idx = block.find("{", m.end() - 1)
    chain_txt = _extract_braced_object(block, start_idx)
    if not chain_txt:
        return None
    try:
        parsed = json.loads(chain_txt)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _extract_sutta_and_commentary(block: str) -> tuple[str | None, str | None]:
    # Prefer real JSON if it parses
    obj = _try_parse_json_object(block)
    if obj:
        s = obj.get("sutta")
        c = obj.get("commentary") or obj.get("commentry")
        sutta = s if isinstance(s, str) else None
        comm = c if isinstance(c, str) else None
        return sutta, comm

    # Tolerant extraction: there may be multiple "sutta" keys in `an1.json`
    suttas = _extract_string_values(block, "sutta")
    commentary = _extract_string_values(block, "commentary") or _extract_string_values(block, "commentry")

    sutta_text = "\n".join([s for s in suttas if s]).strip() or None
    comm_text = "\n".join([c for c in commentary if c]).strip() or None
    return sutta_text, comm_text


def write_suttas_folder(
    repo_root: Path,
    source_file: str,
    id_key: str,
    out_prefix: str,
) -> int:
    src_path = repo_root / source_file
    text = src_path.read_text(encoding="utf-8", errors="replace")

    blocks = extract_blocks(text, id_key)

    out_dir = repo_root / out_prefix / "suttas"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Clean previously generated files (keep directory)
    for p in out_dir.glob("*.json"):
        p.unlink()

    index: list[dict[str, str]] = []
    for sid_raw, block in blocks:
        sid = normalize_id(sid_raw)
        sutta, comm = _extract_sutta_and_commentary(block)
        chain = _extract_chain(block)

        obj: dict = {"sutta_id": sid}
        if sutta is not None:
            obj["sutta"] = sutta
        if comm is not None:
            obj["commentary"] = comm
        if chain is not None:
            obj["chain"] = chain

        out_path = out_dir / file_name_for_id(sid)
        out_path.write_text(
            json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        index.append({"path": f"{out_prefix}/suttas/{out_path.name}"})

    (out_dir / "_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    return len(blocks)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    n1 = write_suttas_folder(
        repo_root=repo_root,
        source_file="an1.json",
        id_key="suttaid",
        out_prefix="an1",
    )
    print(f"an1: wrote {n1} suttas")

    n3 = write_suttas_folder(
        repo_root=repo_root,
        source_file="an3.json",
        id_key="sutta_id",
        out_prefix="an3",
    )
    print(f"an3: wrote {n3} suttas")


if __name__ == "__main__":
    main()

