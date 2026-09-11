from datetime import date, timedelta
from decimal import Decimal as D, localcontext
from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from quant_research.data import Dataset, read_csv
from quant_research.engine import run
from quant_research.models import Bar, Config, Decision, PortfolioView
from quant_research.reporting import canonical, metrics, save_bundle
from quant_research.strategies import BreakoutConfig, BreakoutRetest, BuyAndHold, CashOnly, bollinger


def bars(prices):
    return tuple(Bar(date(2025, 1, 1) + timedelta(days=i), D(str(p)), D(str(p)), D(str(p)), D(str(p)), D("1000")) for i, p in enumerate(prices))


class Script:
    def __init__(self, actions): self.actions = actions
    def decide(self, history, portfolio):
        action = self.actions.get(len(history) - 1)
        return Decision(action, "test") if action else None


class AccountingTests(unittest.TestCase):
    def test_hand_calculated_round_trip(self):
        cfg = Config(max_position_weight=D(".25"), fee_bps=D("100"), slippage_bps=D("100"))
        r = run(bars([100, 100, 100]), Script({0: "BUY", 1: "SELL"}), cfg)
        buy, sell = r.fills
        self.assertEqual((buy.quantity, buy.price, buy.fee, buy.cash_after), (D(2), D(101), D("2.02"), D("795.98")))
        self.assertEqual((sell.price, sell.fee, sell.cash_after), (D(99), D("1.98"), D(992)))
        self.assertEqual(r.equity[-1].equity, D(992))

    def test_no_overnight_profit_before_fill(self):
        r = run(bars([100, 200, 200]), Script({0: "BUY"}), Config(max_position_weight=D(1), fee_bps=D(0), slippage_bps=D(0)))
        self.assertEqual(r.fills[0].price, D(200))
        self.assertEqual(r.equity[-1].equity, D(1000))

    def test_final_signal_stays_pending(self):
        r = run(bars([100]), Script({0: "BUY"}))
        self.assertEqual(len(r.fills), 0)
        self.assertIsNotNone(r.pending)

    def test_cash_and_long_only_invariants_across_costs(self):
        for price in ("0.10", "10", "199", "10000"):
            for fee in ("0", "5", "100"):
                cfg = Config(fee_bps=D(fee), slippage_bps=D(50))
                r = run(bars([price] * 6), Script({0: "SELL", 1: "BUY", 2: "BUY", 3: "SELL", 4: "SELL"}), cfg)
                for point in r.equity:
                    self.assertGreaterEqual(point.cash, 0)
                    self.assertGreaterEqual(point.quantity, 0)
                    self.assertEqual(point.equity, point.cash + point.quantity * point.close)
                for f in r.fills:
                    self.assertGreater(f.date, f.signal_date)
                    if f.action == "BUY": self.assertLessEqual(f.notional + f.fee, D(200))

    def test_initial_equity_in_drawdown(self):
        r = run(bars([100, 100]), BuyAndHold(), Config(fee_bps=D(100), slippage_bps=D(0)))
        self.assertEqual(metrics(r)["max_drawdown"], D("-.001"))

    def test_zero_volume_fails_data_admission(self):
        b = bars([100, 100])
        empty = Bar(b[1].date, D(100), D(100), D(100), D(100), D(0))
        with self.assertRaisesRegex(ValueError, "zero-volume"):
            run((b[0], empty), BuyAndHold())

    def test_repeatable_despite_external_decimal_precision(self):
        reference = canonical(run(bars([100, 105, 99]), BuyAndHold()))
        with localcontext() as c:
            c.prec = 8
            self.assertEqual(reference, canonical(run(bars([100, 105, 99]), BuyAndHold())))

    def test_no_terminal_liquidation(self):
        r = run(bars([100, 100, 110]), BuyAndHold())
        self.assertEqual(len(r.fills), 1)
        self.assertGreater(r.equity[-1].quantity, 0)


class DataTests(unittest.TestCase):
    def test_invalid_bars(self):
        for bad in ("NaN", "Infinity", "-1", "0"):
            with self.assertRaises(ValueError):
                Bar(date(2025, 1, 1), D(bad), D(10), D(1), D(5), D(10))

    def test_duplicate_and_reversed_sessions(self):
        b = bars([100, 101])
        for invalid in ((b[0], b[0]), tuple(reversed(b)), ()):
            with self.assertRaises(ValueError): run(invalid, CashOnly())

    def test_csv_missing_and_inconsistent_fields(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.csv"
            for row in ("2025-01-01,10,9,8,10,100", "2025-01-01,10,,8,10,100", "2025-01-01,10,11,8,10,100,extra"):
                p.write_text("date,open,high,low,close,volume\n" + row)
                with self.assertRaises(ValueError): read_csv(p)


class StrategyTests(unittest.TestCase):
    def test_bollinger_known_population_variance(self):
        self.assertEqual(bollinger((D(1), D(3)), 2), (D(0), D(2), D(4)))
        self.assertIsNone(bollinger((D(1),), 2))

    def test_frozen_resistance_and_next_open_fill(self):
        b = bars([100, 100, 102, 100, 103, 104, 105])
        cfg = BreakoutConfig(lookback=2, max_holding_bars=2)
        r = run(b, BreakoutRetest(cfg), Config(fee_bps=D(0), slippage_bps=D(0)))
        self.assertEqual(r.signals[0].date, b[3].date)
        self.assertEqual(r.signals[0].decision.level, D(100))
        self.assertEqual(r.fills[0].date, b[4].date)
        self.assertEqual(r.fills[0].price, D(103))
        self.assertEqual(r.fills[1].date, b[6].date)

    def test_expired_retest_does_not_enter(self):
        r = run(bars([100, 100, 102, 105, 100, 100]), BreakoutRetest(BreakoutConfig(lookback=2, retest_bars=1)))
        self.assertFalse(r.fills)

    def test_stop_is_close_based_and_gap_can_exceed_threshold(self):
        # Retest on bar 3, enter on bar 4 at 103, stop decision at 95,
        # actual exit on the next open at 80, not at the threshold 97.85.
        b = bars([100, 100, 102, 100, 103, 95, 80])
        r = run(b, BreakoutRetest(BreakoutConfig(lookback=2)), Config(fee_bps=D(0), slippage_bps=D(0)))
        self.assertEqual(r.fills[1].price, D(80))
        self.assertEqual(r.fills[1].signal_date, b[5].date)
        self.assertIn("close-based stop", r.fills[1].reason)

    def test_breakout_bar_cannot_confirm_its_own_retest(self):
        b = bars([100, 100])
        breakout = Bar(date(2025, 1, 3), D(100), D(104), D(100), D(103), D(1000))
        r = run(b + (breakout,), BreakoutRetest(BreakoutConfig(lookback=2)))
        self.assertFalse(r.signals)

    def test_close_below_retest_tolerance_invalidates_setup(self):
        r = run(bars([100, 100, 102, 98, 100, 101]), BreakoutRetest(BreakoutConfig(lookback=2)))
        self.assertFalse(r.fills)

    def test_future_changes_cannot_change_past(self):
        prefix = bars([100, 100, 102, 100, 103, 104])
        cfg = BreakoutConfig(lookback=2)
        short = run(prefix, BreakoutRetest(cfg))
        extended = run(prefix + bars([1] * 6 + [10000, 2])[6:], BreakoutRetest(cfg))
        self.assertEqual(short.equity, extended.equity[:len(prefix)])
        self.assertEqual(short.signals, tuple(s for s in extended.signals if s.date <= prefix[-1].date))
        self.assertEqual(short.fills, tuple(f for f in extended.fills if f.date <= prefix[-1].date))


class BundleTests(unittest.TestCase):
    def test_reproduction_and_tamper_detection(self):
        fixture = Path(__file__).parent / "fixtures/synthetic.csv"
        b = read_csv(fixture)
        cfg = BreakoutConfig()
        results = {"breakout_retest": run(b, BreakoutRetest(cfg)), "cash": run(b, CashOnly())}
        with tempfile.TemporaryDirectory() as d:
            args = (Path(d), Dataset.from_path(fixture, "SYNTHETIC", "synthetic"), results)
            first = save_bundle(*args)
            self.assertEqual(first, save_bundle(*args))
            self.assertEqual(json.loads((first / "manifest.json").read_text())["validation_status"], "engineering_only")
            (first / "fills.csv").write_text("changed")
            with self.assertRaises(ValueError): save_bundle(*args)


if __name__ == "__main__":
    unittest.main()
