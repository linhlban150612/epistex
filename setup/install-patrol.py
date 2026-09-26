#!/usr/bin/env python3
"""Install the user timer that runs one Epistex desk patrol every 30 seconds."""

import pathlib
import shutil
import subprocess
import sys

kit = pathlib.Path(__file__).resolve().parent
paseo = shutil.which("paseo")
if not paseo:
    raise SystemExit("paseo CLI is required on PATH")
paseo = pathlib.Path(paseo).resolve(strict=True)
node = shutil.which("node")
if not node:
    raise SystemExit("Node.js is required on PATH")
node_dir = pathlib.Path(node).resolve(strict=True).parent
units = pathlib.Path.home() / ".config/systemd/user"
units.mkdir(parents=True, exist_ok=True)
service = units / "epistex-patrol.service"
timer = units / "epistex-patrol.timer"
expected = {
    service: f"""[Unit]
Description=Epistex standalone desk patrol

[Service]
Type=oneshot
Environment=PASEO_BIN={paseo}
Environment=PATH={node_dir}:/usr/local/bin:/usr/bin:/bin
ExecStart={sys.executable} {kit / 'desk.py'} patrol
TimeoutStartSec=120
""",
    timer: """[Unit]
Description=Run Epistex patrol every 30 seconds

[Timer]
OnBootSec=30s
OnUnitInactiveSec=30s
Unit=epistex-patrol.service

[Install]
WantedBy=timers.target
""",
}
for path, content in expected.items():
    if path.exists() and path.read_text() != content:
        previous = path.read_text()
        old_bin = next((line for line in previous.splitlines() if line.startswith("Environment=PASEO_BIN=")), None)
        normalized = previous.replace(old_bin, f"Environment=PASEO_BIN={paseo}") if old_bin else previous
        if path == service and "Environment=PATH=" not in normalized:
            normalized = normalized.replace("ExecStart=", f"Environment=PATH={node_dir}:/usr/local/bin:/usr/bin:/bin\nExecStart=", 1)
        if path != service or not old_bin or normalized != content:
            raise SystemExit(f"refusing to overwrite an existing unit: {path}")
    path.write_text(content)
subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
subprocess.run(["systemctl", "--user", "enable", "--now", timer.name], check=True)
print("Epistex patrol timer enabled:", timer)
