import json
import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/epistex-delivery"


class DeliveryPluginTest(unittest.TestCase):
    def test_manifest_pins_paseo_0_14_0_and_entry_exists(self):
        manifest = json.loads((PLUGIN / "paseo-plugin.json").read_text())
        self.assertEqual(manifest["id"], "epistex-delivery")
        self.assertEqual(manifest["requirements"], {"paseo": "0.14.0"})
        self.assertTrue((PLUGIN / "index.server.ts").is_file())
        self.assertIn('PASEO_VERSION = "0.14.0"', (PLUGIN / "server/plugin.ts").read_text())

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
