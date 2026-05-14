import json
import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


class FrontendHelpersTestCase(unittest.TestCase):
    def run_node(self, script):
        repo_root = Path(__file__).resolve().parents[1]
        node = shutil.which("node") or shutil.which("node.exe")
        self.assertIsNotNone(node, "node or node.exe is required for frontend helper tests")
        result = subprocess.run(
            [node, "-e", script],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def test_find_known_stock_name_uses_existing_trade_for_symbol(self):
        script = textwrap.dedent(
            """
            const { findKnownStockName } = require("./app-helpers.js");
            const trades = [
              { symbol: "0050", name: "元大台灣50" },
              { symbol: "2330", name: "台積電" },
              { symbol: "0050", name: "較舊名稱" },
            ];
            console.log(JSON.stringify({
              exact: findKnownStockName(trades, "2330"),
              trimmed: findKnownStockName(trades, " 0050 "),
              missing: findKnownStockName(trades, "006208"),
              blankName: findKnownStockName([{ symbol: "1101", name: "" }], "1101"),
            }));
            """
        )

        payload = json.loads(self.run_node(script))

        self.assertEqual(payload["exact"], "台積電")
        self.assertEqual(payload["trimmed"], "元大台灣50")
        self.assertEqual(payload["missing"], "")
        self.assertEqual(payload["blankName"], "")

    def test_should_auto_fill_stock_name_replaces_stale_existing_value(self):
        script = textwrap.dedent(
            """
            const { shouldAutoFillStockName } = require("./app-helpers.js");
            console.log(JSON.stringify({
              empty: shouldAutoFillStockName("", "凱基台灣 TOP 50"),
              stale: shouldAutoFillStockName("富邦科技", "凱基台灣 TOP 50"),
              same: shouldAutoFillStockName("凱基台灣 TOP 50", "凱基台灣 TOP 50"),
              missingKnownName: shouldAutoFillStockName("富邦科技", ""),
            }));
            """
        )

        payload = json.loads(self.run_node(script))

        self.assertTrue(payload["empty"])
        self.assertTrue(payload["stale"])
        self.assertFalse(payload["same"])
        self.assertFalse(payload["missingKnownName"])


if __name__ == "__main__":
    unittest.main()
