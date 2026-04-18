from pathlib import Path


def escape_newlines_in_json_strings(raw: str) -> str:
    out: list[str] = []
    in_string = False
    escape = False

    i = 0
    while i < len(raw):
        ch = raw[i]

        if in_string:
            if escape:
                out.append(ch)
                escape = False
            else:
                if ch == "\\":
                    out.append(ch)
                    escape = True
                elif ch == "\r":
                    # Normalize CRLF/CR inside strings as \n
                    out.append("\\n")
                    # If this is a CRLF pair, consume the LF too.
                    if i + 1 < len(raw) and raw[i + 1] == "\n":
                        i += 1
                elif ch == "\n":
                    out.append("\\n")
                elif ch == '"':
                    out.append(ch)
                    in_string = False
                else:
                    out.append(ch)
        else:
            out.append(ch)
            if ch == '"':
                in_string = True
                escape = False

        i += 1

    return "".join(out)


def main() -> None:
    path = Path("an2.json")
    raw = path.read_text(encoding="utf-8")
    fixed = escape_newlines_in_json_strings(raw)
    path.write_text(fixed, encoding="utf-8")


if __name__ == "__main__":
    main()

