import os
import pathlib
import re
import shlex
import subprocess

TEMP_ROOTS = ("/tmp", "/var/tmp")
PREFIXES = {"sudo", "command", "exec", "env", "nice", "time", "nohup"}
OPAQUE = re.compile(r"[$`]")


def segments(command: str):
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    try:
        words = list(lexer)
    except ValueError:
        return None
    out, current = [], []
    for word in words:
        if word in ("{", "}") or set(word) <= set(";&|()"):
            out.append(current)
            current = []
        else:
            current.append(word)
    out.append(current)
    return [segment for segment in out if segment]


def program(words):
    index = 0
    while index < len(words) and (re.fullmatch(r"\w+=.*", words[index]) or words[index] in PREFIXES):
        index += 1
    return words[index:]


def inside(path: pathlib.Path, root: pathlib.Path) -> bool:
    return path == root or root in path.parents


def resolve(text: str, directory):
    if OPAQUE.search(text):
        return None
    if text == "~" or text.startswith("~/"):
        text = str(pathlib.Path.home()) + text[1:]
    elif text.startswith("~"):
        return None
    if not os.path.isabs(text):
        if directory is None:
            return None
        text = os.path.join(directory, text)
    return pathlib.Path(os.path.normpath(text))


def rm_reason(words, directory, workspace):
    flags = "".join(word[1:] for word in words[1:] if re.fullmatch(r"-[A-Za-z]+", word))
    longs = {word for word in words[1:] if word.startswith("--")}
    if not (set(flags) & set("rR") or "--recursive" in longs) or not ("f" in flags or "--force" in longs):
        return None
    for operand in (word for word in words[1:] if not word.startswith("-")):
        path = resolve(operand, directory)
        if path is None:
            return f"rm -rf on a path the guard cannot read: {operand}"
        if inside(workspace, path):
            return f"rm -rf on the workspace or a folder above it: {operand}"
        if inside(path, workspace):
            continue
        if any(inside(path, pathlib.Path(root)) and str(path) != root for root in TEMP_ROOTS):
            continue
        return f"rm -rf outside the workspace: {operand}"
    return None


def git_reason(words):
    args = words[1:]
    index = 0
    while index < len(args) and args[index].startswith("-"):
        index += 2 if args[index] in ("-C", "-c") else 1
    if index >= len(args):
        return None
    subcommand, rest = args[index], args[index + 1:]
    if subcommand == "reset" and "--hard" in rest:
        return "git reset --hard"
    if subcommand == "push":
        short = "".join(word[1:] for word in rest if re.fullmatch(r"-[A-Za-z]+", word))
        if "f" in short or any(word.startswith(("--force", "--mirror")) for word in rest) or any(word.startswith("+") for word in rest):
            return "git push --force"
    return None


def denied(command: str, cwd: str, workspace: pathlib.Path):
    parts = segments(command)
    if parts is None:
        if re.search(r"\brm\s+(?:-\w+\s+)*-\w*[rR]", command) and re.search(r"\brm\b.*\s-\w*f", command):
            return "rm -rf in a command the guard cannot split"
        parts = [command.split()]
    directory = cwd
    for words in parts:
        words = program(words)
        if not words:
            continue
        name = os.path.basename(words[0])
        if name in ("cd", "pushd"):
            target = resolve(words[1], directory) if len(words) > 1 else None
            directory = str(target) if target else None
        elif name == "rm":
            reason = rm_reason(words, directory, workspace)
            if reason:
                return reason
        elif name == "git":
            reason = git_reason(words)
            if reason:
                return reason
        elif name in ("bash", "sh", "zsh") and "-c" in words and words.index("-c") + 1 < len(words):
            reason = denied(words[words.index("-c") + 1], directory or cwd, workspace)
            if reason:
                return reason
    return None


def workspace_of(cwd: str, project_variable: str) -> pathlib.Path:
    project = os.environ.get(project_variable)
    if project:
        return pathlib.Path(os.path.normpath(project))
    try:
        top = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"], text=True, capture_output=True, timeout=5)
        if top.returncode == 0 and top.stdout.strip():
            return pathlib.Path(top.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return pathlib.Path(os.path.normpath(cwd))


def peer_reason(call: dict, tool: str, project_variable: str):
    command = call.get("tool_input", {}).get("command") if isinstance(call.get("tool_input"), dict) else None
    if call.get("tool_name") != tool or not isinstance(command, str):
        return None
    cwd = call.get("cwd") if isinstance(call.get("cwd"), str) and call.get("cwd") else os.getcwd()
    return denied(command, cwd, workspace_of(cwd, project_variable))


PEER_ADVICE = "Use a narrower command inside your worktree, or report the need to the Lead in the handoff (BLOCKED)."
