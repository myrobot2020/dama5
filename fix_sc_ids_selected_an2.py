import json
from pathlib import Path
from typing import Any, Dict, List


PLAIN_QUERY = "lang=en&layout=plain&reference=none&notes=asterisk&highlight=false&script=latin"


TARGET_SUTTA_IDS = {
    "2.3.9",
    "2.4.1",
    "2.4.2",
    "2.11.2",
    "2.11.8",
    "2.11.9",
}


def build_sc_url(uid: str) -> str:
    uid = uid.strip().lower()
    return f"https://suttacentral.net/{uid}/en/sujato?{PLAIN_QUERY}"


def collapsed_uid_from_sutta_id(sutta_id: str) -> str:
    # User rule: remove middle number, keep last component: 2.x.n -> an2.n
    parts = [p for p in (sutta_id or "").split(".") if p.strip()]
    if len(parts) < 3:
        raise ValueError(f"Unexpected sutta_id format: {sutta_id!r}")
    last = parts[-1]
    if not last.isdigit():
        raise ValueError(f"Unexpected sutta_id last token: {sutta_id!r}")
    return f"an2.{int(last)}"


def main() -> None:
    path = Path("an2.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise TypeError("Expected top-level list in an2.json")

    updated: List[str] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        sid = str(entry.get("sutta_id") or "").strip()
        if sid not in TARGET_SUTTA_IDS:
            continue
        uid = collapsed_uid_from_sutta_id(sid)
        entry["sc_id"] = uid
        entry["sc_url"] = build_sc_url(uid)
        # Force refresh using the SC extractsutta API backfill script.
        entry["sc_sutta"] = ""
        updated.append(f"{sid} -> {uid}")

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    rep = Path("fix_sc_ids_selected_an2.report.txt")
    rep.write_text("\n".join(["updated=" + str(len(updated))] + updated) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

