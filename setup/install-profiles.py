#!/usr/bin/env python3
"""Install 35 independent Paseo role providers and launch profiles."""

import json
import os
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROLES = ("supervisor", "lead", "peer", "reviewer", "watcher")
AGENTS = ("claude", "codex", "devin", "pi", "amp", "glm", "droid")
BASE = {"claude": "claude", "codex": "codex", "devin": "acp", "pi": "pi",
        "amp": "acp", "glm": "acp", "droid": "acp"}


def desired():
    providers = {}
    profiles = []
    old = json.loads((ROOT / "examples" / "paseo-providers.json").read_text())
    for role in ROLES:
        for agent in AGENTS:
            key = f"epx-{role}-{agent}"
            if agent == "codex":
                provider = dict(old.get(f"codex-{role}", {}))
                provider.update(extends="codex", command=[str(ROOT / "setup" / "codex-room"), role])
                provider["env"] = {**provider.get("env", {}), "EPISTEX_DESK": str(ROOT / "setup" / "desk.py")}
            else:
                provider = {
                    "extends": BASE[agent],
                    "command": [str(ROOT / "setup" / "role-agent"), role, agent],
                    "env": {"EPISTEX_DESK": str(ROOT / "setup" / "desk.py")},
                }
            provider.update(label=f"{role.title()} · {agent.title()} (Epistex)",
                            description=f"Standalone {role} role on {agent}; instructions from Epistex",
                            enabled=True,
                            paseoTools={"enabled": role in ("supervisor", "lead")})
            if agent == "droid":
                provider["env"].update(DROID_DISABLE_AUTO_UPDATE="true", FACTORY_DROID_AUTO_UPDATE_ENABLED="false")
                provider["params"] = {"supportsMcpServers": False}
            providers[key] = provider
            profiles.append({"id": key, "name": provider["label"], "provider": key,
                             "notes": f"Epistex {role} instructions; ACP agents use a first-turn instruction, not a system prompt."})
    return providers, profiles


def main():
    if sys.argv[1:] not in ([], ["--check"]):
        raise SystemExit("usage: install-profiles.py [--check]")
    check = sys.argv[1:] == ["--check"]
    path = pathlib.Path(os.environ.get("PASEO_CONFIG", pathlib.Path.home() / ".paseo/config.json"))
    config = json.loads(path.read_text())
    if config.get("plugins", {}).get("seatworks-v2") is not None:
        raise SystemExit("Seatworks is installed; refusing standalone setup")
    providers, profiles = desired()
    for role in ROLES:
        if not (ROOT / "agents" / f"{role.upper()}.md").is_file():
            raise SystemExit(f"missing role instructions for {role}")
    for name in ("codex-room", "codex-room-sync", "role-agent"):
        if not os.access(ROOT / "setup" / name, os.X_OK):
            raise SystemExit(f"not executable: setup/{name}")
    installed = config.setdefault("agents", {}).setdefault("providers", {})
    current = config.setdefault("daemon", {}).setdefault("agentProfiles", [])
    if not isinstance(current, list):
        raise SystemExit("daemon.agentProfiles must be a list")
    if len({item["id"] for item in current}) != len(current):
        raise SystemExit("duplicate profile IDs in Paseo config")
    existing = {item["id"]: item for item in current}
    if check:
        if any(installed.get(key) != value or existing.get(key) != profile
               for (key, value), profile in zip(providers.items(), profiles)):
            raise SystemExit("Epistex providers or profiles missing or changed")
        print("35 Epistex providers and profiles match; Seatworks is uninstalled")
        return
    installed.update(providers)
    config["daemon"]["agentProfiles"] = [item for item in current if item["id"] not in providers] + profiles
    backup = path.with_name(path.name + ".epistex-backup")
    if not backup.exists():
        shutil.copy2(path, backup)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        os.fchmod(fd, path.stat().st_mode & 0o777)
        with os.fdopen(fd, "w") as stream:
            json.dump(config, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print("Installed 35 Epistex providers and profiles; backup:", backup)


if __name__ == "__main__":
    main()
