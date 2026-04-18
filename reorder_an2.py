import json
from collections import OrderedDict
from pathlib import Path


ORDER = [
    "sutta_id",
    "sc_id",
    "sc_url",
    "aud_file",
    "aud_start_s",
    "aud_end_s",
    "chain",
    "alignment",
]
TAIL = ["sc_sutta", "sutta", "commentary"]


def reorder_entry(entry: dict) -> OrderedDict:
    """Return an OrderedDict with a consistent, readability-focused key order."""
    out = OrderedDict()
    # First, our preferred order
    for k in ORDER:
        if k in entry:
            out[k] = entry[k]
    # Then, any remaining keys in original order
    for k, v in entry.items():
        if k not in out and k not in TAIL:
            out[k] = v
    # Finally, force long text fields last, in this order
    for k in TAIL:
        if k in entry:
            out[k] = entry[k]
    return out


def main() -> None:
    path = Path("an2.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise TypeError("Expected top-level list in an2.json")

    new_data = [reorder_entry(obj if isinstance(obj, dict) else obj) for obj in data]
    path.write_text(
        json.dumps(new_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

