import json
import re
from pathlib import Path
from typing import Any, Dict, List


def _safe_name(sutta_id: str) -> str:
    s = (sutta_id or "").strip()
    if not s:
        return "unknown"
    s = s.replace("/", "_").replace("\\", "_")
    s = re.sub(r"[^0-9A-Za-z._-]+", "_", s)
    return s


def main() -> None:
    src = Path("an2.json")
    if not src.exists():
        raise FileNotFoundError("Expected an2.json in repo root")

    data = json.loads(src.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise TypeError("Expected an2.json top-level list")

    out_dir = Path("an2") / "suttas"
    out_dir.mkdir(parents=True, exist_ok=True)

    written: List[Path] = []
    used_names = set()
    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            continue
        sid = str(entry.get("sutta_id") or "").strip()
        base = _safe_name(sid) if sid else f"row_{i:04d}"
        name = base
        n = 2
        while name.lower() in used_names:
            name = f"{base}__{n}"
            n += 1
        used_names.add(name.lower())

        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(entry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(path)

    index_path = out_dir / "_index.json"
    index: List[Dict[str, Any]] = []
    for p in sorted(written, key=lambda x: x.name.lower()):
        # store relative path for portability
        index.append({"path": str(p.as_posix())})
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {len(written)} sutta files to {out_dir}")


if __name__ == "__main__":
    main()

