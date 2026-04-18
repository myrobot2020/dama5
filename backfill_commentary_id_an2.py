import json
from pathlib import Path


def _normalize_suttaid(sutta_id: str) -> str:
    s = (sutta_id or "").strip()
    if not s:
        return ""
    if s.upper().startswith("AN "):
        return "AN " + s[3:].strip()
    if s.upper().startswith("AN"):
        # tolerate "AN2.1.2" or "AN2.1.2" style
        rest = s[2:].lstrip(" .")
        return "AN " + rest.strip()
    return "AN " + s


def main() -> None:
    path = Path("an2.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise TypeError("Expected top-level list in an2.json")

    changed = 0
    for obj in data:
        if not isinstance(obj, dict):
            continue
        if (obj.get("commentary_id") or "").strip():
            continue
        sid = _normalize_suttaid(str(obj.get("sutta_id") or obj.get("suttaid") or ""))
        if not sid:
            continue
        obj["commentary_id"] = "c" + sid
        changed += 1

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Backfilled commentary_id on {changed} records in {path}")


if __name__ == "__main__":
    main()

