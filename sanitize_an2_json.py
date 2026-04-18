import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple


_SUTTA_ID_RE = re.compile(r"(\d+(?:\.\d+)*)")


def _canon_commentary_id_from_sutta_id(sutta_id: str) -> str:
    s = str(sutta_id or "").strip()
    m = _SUTTA_ID_RE.search(s)
    return f"cAN {m.group(1)}" if m else ""


def _truncate_spillover(text: str) -> Tuple[str, bool]:
    """
    Remove embedded 'next sutta' spillover that sometimes appears inside a single commentary/sutta field.

    We cut at the earliest marker that looks like a new record starting inside the text.
    """
    s = str(text or "")
    if not s.strip():
        return s, False

    # Markers seen in this dataset.
    markers = [
        r"\n\s*sutta_id\s*:\s*\d",  # e.g. "\n    sutta_id:2.3.10"
        r"\n\s*sutta\s*:\s*",      # e.g. "\n    sutta: The buddha said ..."
        r"\n\s*sutta\s*;\s*",      # e.g. "\n    sutta; point two point seven ..."
    ]
    cut_idx = None
    for pat in markers:
        m = re.search(pat, s, flags=re.I)
        if m:
            i = m.start()
            if cut_idx is None or i < cut_idx:
                cut_idx = i

    if cut_idx is None:
        return s, False

    out = s[:cut_idx].rstrip()
    return out, out != s


def main() -> None:
    path = Path("an2.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("an2.json must be a top-level list")

    changed: List[Dict[str, Any]] = []
    out: List[Dict[str, Any]] = []
    for obj in data:
        if not isinstance(obj, dict):
            out.append(obj)
            continue

        sid = str(obj.get("sutta_id") or obj.get("suttaid") or "").strip()
        before_comm_id = str(obj.get("commentary_id") or "").strip()
        canon_comm_id = _canon_commentary_id_from_sutta_id(sid)
        if canon_comm_id:
            obj["commentary_id"] = canon_comm_id

        comm = obj.get("commentary")
        sut = obj.get("sutta")
        comm2, comm_changed = _truncate_spillover(str(comm or ""))
        sut2, sut_changed = _truncate_spillover(str(sut or ""))
        if comm_changed:
            obj["commentary"] = comm2
        if sut_changed:
            obj["sutta"] = sut2

        if comm_changed or sut_changed or (canon_comm_id and before_comm_id != canon_comm_id):
            changed.append(
                {
                    "sutta_id": sid,
                    "commentary_id_before": before_comm_id,
                    "commentary_id_after": obj.get("commentary_id"),
                    "commentary_len_before": len(str(comm or "")),
                    "commentary_len_after": len(str(obj.get("commentary") or "")),
                    "sutta_len_before": len(str(sut or "")),
                    "sutta_len_after": len(str(obj.get("sutta") or "")),
                }
            )

        out.append(obj)

    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    Path("sanitize_an2_json.report.json").write_text(
        json.dumps({"changed": changed, "changed_count": len(changed)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

