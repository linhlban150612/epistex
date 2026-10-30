import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class LeadSkillsTest(unittest.TestCase):
    def test_lead_prompt_references_only_existing_skills_and_keeps_headroom(self):
        lead = (ROOT / "agents/LEAD.md").read_text()
        protocol = (ROOT / "examples/WORKSPACE_PROTOCOL.md").read_text()
        entry_points = lead + "\n" + protocol
        paths = set(re.findall(r"`(\.agents/skills/[\w-]+/SKILL\.md)`", entry_points))
        on_disk = {p.relative_to(ROOT).as_posix() for p in ROOT.glob(".agents/skills/*/SKILL.md")}
        self.assertEqual(paths, on_disk, "every kit skill is reachable from the Lead prompt or protocol template")
        for path in paths:
            self.assertTrue((ROOT / path).is_file(), path)
            name = path.split("/")[2]
            text = (ROOT / path).read_text()
            self.assertRegex(text, rf"(?m)^name: {name}$", path)
            self.assertIn(f"`{name}` skill", entry_points, path)
        prompt = subprocess.run([sys.executable, str(ROOT / "setup/role_prompt.py"), "lead"],
                                text=True, capture_output=True, check=True).stdout
        self.assertLessEqual(len(prompt.encode()), 16384 - 1024, "Lead prompt must keep 1 KiB of headroom")


if __name__ == "__main__":
    unittest.main()
