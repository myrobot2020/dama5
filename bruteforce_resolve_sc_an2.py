import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PLAIN_QUERY = "lang=en&layout=plain&reference=none&notes=asterisk&highlight=false&script=latin"

TARGET_SUTTA_IDS = {
    "2.3.9",
    "2.4.1",
    "2.4.2",
    "2.11.2",
    "2.11.8",
    "2.11.9",
}

UID_MAX = 112  # AN2 has 112 suttas
CACHE_PATH = Path("sc_cache_an2_sujato.json")


def build_sc_url(uid: str) -> str:
    uid = uid.strip().lower()
    return f"https://suttacentral.net/{uid}/en/sujato?{PLAIN_QUERY}"


def strip_internal_prefix(sutta: str) -> str:
    return re.sub(r"^\\s*\\d+(?:\\.\\d+)+\\s*", "", (sutta or "").strip())


def tokens(text: str) -> List[str]:
    return re.findall(r"[a-z]{2,}", (text or "").lower())


def jaccard(a: List[str], b: List[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def load_cache() -> Dict[str, str]:
    if CACHE_PATH.exists():
        try:
            obj = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                return {str(k): str(v) for k, v in obj.items()}
        except Exception:
            pass
    return {}


def save_cache(cache: Dict[str, str]) -> None:
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_an2_cache() -> Dict[str, str]:
    from backfill_sc_sutta_an2 import fetch_sc_translation

    cache = load_cache()
    updated = 0
    for n in range(1, UID_MAX + 1):
        uid = f"an2.{n}"
        if uid in cache and cache[uid].strip():
            continue
        txt = ""
        last_err: Optional[Exception] = None
        for attempt in range(3):
            try:
                txt = fetch_sc_translation(uid, "sujato", timeout_s=12)
                last_err = None
                break
            except Exception as e:
                last_err = e
                time.sleep(0.7 + attempt * 0.8)
        if last_err is not None and not txt:
            # Keep placeholder so we can retry on the next run.
            cache.setdefault(uid, "")
        else:
            cache[uid] = txt or ""
            updated += 1

        # Persist incrementally so we can resume after network flakiness.
        if updated and (updated % 8 == 0):
            save_cache(cache)

        time.sleep(0.18)
    if updated:
        save_cache(cache)
    return cache


def best_uid_for_text(text: str, cache: Dict[str, str]) -> Tuple[str, float]:
    t = tokens(strip_internal_prefix(text))
    best_uid = "an2.1"
    best_sim = -1.0
    for uid, sc_txt in cache.items():
        sim = jaccard(t, tokens(sc_txt))
        if sim > best_sim:
            best_sim = sim
            best_uid = uid
    return best_uid, float(best_sim)


def main() -> None:
    path = Path("an2.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise TypeError("Expected top-level list in an2.json")

    cache = ensure_an2_cache()

    updated: List[str] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        sid = str(entry.get("sutta_id") or "").strip()
        if sid not in TARGET_SUTTA_IDS:
            continue

        sutta = str(entry.get("sutta") or "")
        old = str(entry.get("sc_id") or "").strip()

        uid, sim = best_uid_for_text(sutta, cache)
        sc_txt = cache.get(uid, "")

        entry["sc_id"] = uid
        entry["sc_url"] = build_sc_url(uid)
        entry["sc_sutta"] = sc_txt
        updated.append(f"{sid}: {old} -> {uid} (sim={sim:.3f})")

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    rep = Path("bruteforce_resolve_sc_an2.report.txt")
    rep.write_text("\n".join([f"updated={len(updated)}", *updated, ""]), encoding="utf-8")


if __name__ == "__main__":
    main()

