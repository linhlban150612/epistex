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
        self.assertLessEqual(len(prompt.encode()), 16384 - 512, "Lead prompt must keep 512 B of headroom")

    def test_startup_template_routes_requests_without_promoting_assumptions(self):
        template = (ROOT / "examples/LEAD_INITIAL_PROMPT.md").read_text()
        for field in ("Outcome", "Verified constraints", "Open assumptions", "Decided & who may reopen"):
            self.assertIn(f"\n{field}\n", template)
        self.assertIn("Your Supervisor agent ID is <this agent's agentId>. Ask the Supervisor questions "
                      "with send_agent_prompt(<agentId>, ...).", template)
        self.assertIn(".agents/skills/handling-reopen/SKILL.md", template)
        protocol = (ROOT / "examples/WORKSPACE_PROTOCOL.md").read_text()
        self.assertIn("(LEAD_INITIAL_PROMPT.md)", protocol)

    def test_core_rules_stay_in_lead_prompt(self):
        lead = (ROOT / "agents/LEAD.md").read_text()
        for rule in ("no explicit\nHuman confirmation → no reset", "no replacement writer before",
                     "Rework cap: 2 rework rounds", "Verified facts", "never acceptance"):
            self.assertIn(rule, lead, rule)


if __name__ == "__main__":
    unittest.main()
