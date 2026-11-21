import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
NO_GIT_CONFIG = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "PYTHONDONTWRITEBYTECODE": "1"}

CLEAN_PY = '#!/usr/bin/env python3\nUSAGE = """usage: tool # not a comment"""\nprint("# text", USAGE)  # type: ignore\n'
CLEAN_SH = "#!/usr/bin/env bash\n# shellcheck disable=SC2034\ncount=${#items[@]}\necho \"a # b\" 'c # d' $#\ncat <<'EOF'\n# heredoc text\nEOF\n"
CLEAN_TS = 'const url = "http://host/path"; // @ts-expect-error\nconst pattern = /\\/\\/[^/]*/;\nconst text = `a // b ${url /* eslint-disable */} /* c */`;\n'


class LintCommentsTest(unittest.TestCase):
    def kit(self, folder, files):
        kit = pathlib.Path(folder) / "kit"
        (kit / "setup").mkdir(parents=True)
        shutil.copy2(ROOT / "setup/lint-comments", kit / "setup/lint-comments")
        for name, text in files.items():
            (kit / name).parent.mkdir(parents=True, exist_ok=True)
            (kit / name).write_text(text)
        subprocess.run(["git", "-C", str(kit), "init", "-q"], check=True, env=NO_GIT_CONFIG)
        subprocess.run(["git", "-C", str(kit), "add", "-A"], check=True, env=NO_GIT_CONFIG)
        return kit

    def lint(self, kit, *args):
        return subprocess.run([str(kit / "setup/lint-comments"), *args], text=True, capture_output=True, cwd="/", env=NO_GIT_CONFIG, timeout=60)

    def test_code_without_comments_passes_and_directives_are_allowed(self):
        with tempfile.TemporaryDirectory() as folder:
            kit = self.kit(folder, {"setup/tool": CLEAN_PY, "setup/run.sh": CLEAN_SH, "plugin/a.ts": CLEAN_TS, "README.md": "# Title\n"})
            result = self.lint(kit)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.lint(kit, "--list").stdout, "total: 0 comment lines in 0 files\n")
            self.assertEqual(self.lint(kit, "--unknown").returncode, 2)

    def test_each_language_reports_its_comment_lines(self):
        files = {
            "setup/tool": '#!/usr/bin/env python3\n"""Doc.\n\nMore.\n"""\nx = 1  # why\n\n\ndef f():\n    """Doc."""\n',
            "setup/run.sh": "#!/usr/bin/env bash\n# note\necho ok # trailing\n",
            "setup/filter.jq": '# note\n.a | "# text"\n',
            "plugin/a.ts": "// line\n/**\n * block\n */\nconst a = 1; /* inline */\n",
        }
        with tempfile.TemporaryDirectory() as folder:
            kit = self.kit(folder, files)
            listed = self.lint(kit, "--list").stdout.splitlines()
            lines = {":".join(entry.split(":", 2)[:2]) for entry in listed[:-1]}
            self.assertEqual(lines, {
                "setup/tool:2", "setup/tool:3", "setup/tool:4", "setup/tool:5", "setup/tool:6", "setup/tool:10",
                "setup/run.sh:2", "setup/run.sh:3", "setup/filter.jq:1",
                "plugin/a.ts:1", "plugin/a.ts:2", "plugin/a.ts:3", "plugin/a.ts:4", "plugin/a.ts:5",
            })
            self.assertEqual(listed[-1], "total: 14 comment lines in 4 files")
            result = self.lint(kit)
            self.assertEqual(result.returncode, 1)
            self.assertIn("setup/run.sh: 2 comment lines, limit 0. Delete the new comments.", result.stdout)

    def test_ratchet_only_goes_down(self):
        with tempfile.TemporaryDirectory() as folder:
            kit = self.kit(folder, {"setup/run.sh": "#!/usr/bin/env bash\n# one\n# two\ntrue\n"})
            baseline = kit / "setup/comment-baseline.json"
            self.assertEqual(self.lint(kit, "--update").returncode, 1)
            self.assertFalse(baseline.exists())
            baseline.write_text(json.dumps({"setup/run.sh": 2}))
            self.assertEqual(self.lint(kit).returncode, 0)

            (kit / "setup/run.sh").write_text("#!/usr/bin/env bash\n# one\n# two\n# three\ntrue\n")
            more = self.lint(kit)
            self.assertEqual(more.returncode, 1)
            self.assertIn("setup/run.sh: 3 comment lines, limit 2. Delete the new comments.", more.stdout)
            self.assertIn("setup/run.sh:4:# three", more.stdout)
            self.assertEqual(self.lint(kit, "--update").returncode, 1)
            self.assertEqual(json.loads(baseline.read_text()), {"setup/run.sh": 2})

            (kit / "setup/run.sh").write_text("#!/usr/bin/env bash\n# one\ntrue\n")
            fewer = self.lint(kit)
            self.assertEqual(fewer.returncode, 1)
            self.assertIn("setup/run.sh: 1 comment lines, limit 2. Run setup/lint-comments --update.", fewer.stdout)
            self.assertEqual(self.lint(kit, "--update").returncode, 0)
            self.assertEqual(json.loads(baseline.read_text()), {"setup/run.sh": 1})

            (kit / "setup/new.sh").write_text("#!/usr/bin/env bash\n# new\n")
            subprocess.run(["git", "-C", str(kit), "add", "-A"], check=True, env=NO_GIT_CONFIG)
            new_file = self.lint(kit)
            self.assertEqual(new_file.returncode, 1)
            self.assertIn("setup/new.sh: 1 comment lines, limit 0. Delete the new comments.", new_file.stdout)

    def test_code_that_is_not_a_comment_passes(self):
        files = {
            "setup/tool": '#!/usr/bin/env python3\nimport sys\n"-".join(sys.argv)\n"%s" % sys.argv\n',
        }
        with tempfile.TemporaryDirectory() as folder:
            kit = self.kit(folder, files)
            self.assertEqual(self.lint(kit, "--list").stdout, "total: 0 comment lines in 0 files\n")

    def test_comments_after_quotes_here_strings_and_directives_are_reported(self):
        files = {
            "setup/a.yml": "desc: don't stop\n# one\nname: x # two\n",
            "setup/run.sh": "#!/usr/bin/env bash\ncat <<<EOF\n# three\n",
            "setup/tool.py": "x = 1  # noqa free text\ny = 2  # noqa: E501\n",
            "plugin/a.ts": "// @ts-ignore free text\n// eslint-disable-next-line no-console\n",
        }
        with tempfile.TemporaryDirectory() as folder:
            kit = self.kit(folder, files)
            listed = self.lint(kit, "--list").stdout.splitlines()
            lines = {":".join(entry.split(":", 2)[:2]) for entry in listed[:-1]}
            self.assertEqual(lines, {"setup/a.yml:2", "setup/a.yml:3", "setup/run.sh:3", "setup/tool.py:1", "plugin/a.ts:1"})

    def test_untracked_files_are_read_and_a_broken_file_is_named(self):
        with tempfile.TemporaryDirectory() as folder:
            kit = self.kit(folder, {"setup/run.sh": "#!/usr/bin/env bash\ntrue\n"})
            (kit / "setup/new.sh").write_text("#!/usr/bin/env bash\n# new\n")
            (kit / ".gitignore").write_text("ignored.sh\n")
            (kit / "ignored.sh").write_text("# ignored\n")
            untracked = self.lint(kit)
            self.assertEqual(untracked.returncode, 1)
            self.assertIn("setup/new.sh: 1 comment lines, limit 0.", untracked.stdout)
            self.assertNotIn("ignored.sh", untracked.stdout)

            (kit / "setup/new.sh").unlink()
            (kit / "setup/broken.py").write_text("def f(:\n")
            broken = self.lint(kit)
            self.assertEqual(broken.returncode, 1)
            self.assertIn("setup/broken.py: cannot read as python", broken.stderr)
            self.assertNotIn("Traceback", broken.stderr)


if __name__ == "__main__":
    unittest.main()
