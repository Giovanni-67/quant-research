from dataclasses import replace
from decimal import Decimal as D, Inexact, ROUND_DOWN, localcontext
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from quant_research.data import Dataset
from quant_research.engine import run
from quant_research.models import Config
from quant_research.reporting import canonical, save_bundle
from quant_research.storage import publish
from quant_research.strategies import BreakoutRetest, BuyAndHold, CashOnly, bollinger

FIXTURE = Path(__file__).parent / "fixtures/synthetic.csv"


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.dataset = Dataset.from_path(FIXTURE, "SYNTHETIC", "synthetic")
        self.result = run(self.dataset.bars, BreakoutRetest())

    def test_original_path_changed_after_read_does_not_change_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "input.csv"
            source.write_bytes(self.dataset.raw)
            frozen = Dataset.from_path(source, "TEST", "synthetic")
            source.write_text("not the data computed")
            bundle = save_bundle(root / "runs", frozen, {"breakout_retest": self.result})
            self.assertEqual((bundle / "input.csv").read_bytes(), self.dataset.raw)

    def test_results_from_other_bars_rejected(self):
        r = run(self.dataset.bars[:-1], BreakoutRetest())
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "not computed"):
                save_bundle(Path(d), self.dataset, {"breakout_retest": r})

    def test_baseline_parameters_and_identity_change_run_id(self):
        with tempfile.TemporaryDirectory() as d:
            a = {"breakout_retest": self.result, "baseline": run(self.dataset.bars, CashOnly())}
            b = {"breakout_retest": self.result, "baseline": run(self.dataset.bars, BuyAndHold(), Config(max_position_weight=D(1)))}
            first = save_bundle(Path(d), self.dataset, a)
            second = save_bundle(Path(d), self.dataset, b)
            self.assertNotEqual(first, second)
            saved = json.loads((second / "results.json").read_text())
            self.assertEqual(len(saved["baseline"]["result"]["fills"]), 1)

    def test_identical_spec_with_different_results_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            save_bundle(Path(d), self.dataset, {"breakout_retest": self.result})
            changed = replace(self.result, equity=self.result.equity[:-1])
            with self.assertRaisesRegex(ValueError, "differs"):
                save_bundle(Path(d), self.dataset, {"breakout_retest": changed})

    def test_removed_checksum_entry_cannot_hide_corruption(self):
        with tempfile.TemporaryDirectory() as d:
            bundle = save_bundle(Path(d), self.dataset, {"breakout_retest": self.result})
            (bundle / "checksums.json").write_text("{}")
            with self.assertRaises(ValueError):
                save_bundle(Path(d), self.dataset, {"breakout_retest": self.result})

    def test_mid_write_failure_leaves_no_published_bundle(self):
        original = Path.write_bytes
        def fail(path, payload):
            if path.name == "b.json": raise OSError("simulated interrupted write")
            return original(path, payload)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with patch.object(Path, "write_bytes", fail):
                with self.assertRaises(OSError): publish(root, "abcd", {"a.json": b"a", "b.json": b"b"})
            self.assertFalse((root / "abcd").exists())
            self.assertEqual(list(root.iterdir()), [])

    def test_decimal_traps_and_rounding_do_not_leak_into_engine(self):
        with localcontext() as ctx:
            ctx.rounding = ROUND_DOWN
            ctx.traps[Inexact] = True
            observed = run(self.dataset.bars, BreakoutRetest())
        self.assertEqual(canonical(observed), canonical(self.result))

    def test_standalone_indicators_have_fixed_decimal_context(self):
        values = (D(1), D(2), D(4))
        expected = bollinger(values, 3)
        with localcontext() as ctx:
            ctx.prec = 5
            ctx.rounding = ROUND_DOWN
            ctx.traps[Inexact] = True
            self.assertEqual(bollinger(values, 3), expected)

    def test_source_change_prevents_saving(self):
        with tempfile.TemporaryDirectory() as d:
            changed = replace(self.result, source_sha256="different")
            with self.assertRaisesRegex(ValueError, "source differs"):
                save_bundle(Path(d), self.dataset, {"breakout_retest": changed})


if __name__ == "__main__": unittest.main()
