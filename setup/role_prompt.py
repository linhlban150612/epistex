"""Load the kit's common contract and role instructions, independent of session CWD."""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_prompt(role: str) -> str:
    role = role.lower()
    if role not in ("supervisor", "lead", "peer"):
        raise SystemExit(f"invalid role: {role}")
    try:
        common = (ROOT / "agents/contract/COMMON.md").read_text(encoding="utf-8")
        specific = (ROOT / "agents" / f"{role.upper()}.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise SystemExit(f"cannot load {role} prompt: {error}") from None
    prompt = common.rstrip() + "\n\n" + specific
    if len(prompt.encode("utf-8")) > 16384:
        raise SystemExit(f"combined {role} prompt exceeds 16 KiB")
    return prompt


if __name__ == "__main__":
    sys.stdout.write(load_prompt(sys.argv[1]))
