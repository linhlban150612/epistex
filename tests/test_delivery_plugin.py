import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/epistex-delivery"


class DeliveryPluginTest(unittest.TestCase):
    # The manifest/guard pin is enforced by setup-seats.sh --check (covered in test_setup_seats).
    def test_node_test_suite_passes(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        result = subprocess.run([node, "--test", "--test-reporter=tap", "server/**/*.test.ts"], cwd=PLUGIN,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("# fail 0", result.stdout)


if __name__ == "__main__":
    unittest.main()
