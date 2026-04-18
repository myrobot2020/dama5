import json
import os
import re
from pathlib import Path


PREFIX_RE = re.compile(r"^\s*\d+(?:\.\d+)*\s+")


def transform_sutta_value(value: str) -> str:
    return PREFIX_RE.sub("", value, count=1)


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    target_dir = repo_root / "an3" / "suttas"

    if not target_dir.exists():
        raise SystemExit(f"Target directory not found: {target_dir}")

    changed_files: list[Path] = []
    for path in sorted(target_dir.glob("*.json")):
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception as e:
            raise SystemExit(f"Failed to read/parse {path}: {e}") from e

        if not isinstance(data, dict):
            continue

        sutta = data.get("sutta")
        if not isinstance(sutta, str):
            continue

        new_sutta = transform_sutta_value(sutta)
        if new_sutta != sutta:
            data["sutta"] = new_sutta
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            changed_files.append(path)

    print(f"Updated {len(changed_files)} file(s) in {os.path.relpath(target_dir, repo_root)}")
    for p in changed_files:
        print(f"- {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

