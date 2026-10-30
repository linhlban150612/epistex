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


class Primer:
    """Add the role to each session's first prompt in this ACP proxy process.

    A session restored with session/load or session/resume already holds the role in its
    history, e.g. after Paseo releases an idle runtime and resumes it in a new proxy, so its
    first prompt here gets only the cwd pin, if any.
    """

    def __init__(self, role: str):
        self.role = role
        self.sessions: dict[str, bool] = {}  # session -> role already in this proxy's prompts

    def restore(self, session: str) -> None:
        self.sessions.setdefault(session, False)

    def prime(self, session: str, prompt: list, cwd: str | None = None) -> list:
        primed = self.sessions.get(session)
        if primed:
            return prompt
        parts = []
        if cwd:
            parts.append(f"Session working directory: {cwd}. Run every shell command in that directory.")
        if primed is None:
            parts.append("Role instructions for this session:\n" + load_prompt(self.role))
        self.sessions[session] = True
        return [{"type": "text", "text": "\n\n".join(parts)}, *prompt] if parts else prompt


if __name__ == "__main__":
    sys.stdout.write(load_prompt(sys.argv[1]))
