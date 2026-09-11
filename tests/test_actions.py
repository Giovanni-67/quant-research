from dataclasses import replace
from datetime import date
from decimal import Decimal as D, Inexact, localcontext
from pathlib import Path
import json
import tempfile
import unittest

from test_core import bars, Script
from quant_research.actions import Dividend, Split, parse_actions
from quant_research.data import Dataset
from quant_research.engine import run
from quant_research.models import Config
from quant_research.reporting import save_bundle
from quant_research.strategies import BuyAndHold, BreakoutRetest, BreakoutConfig, CashOnly

CFG = Config(max_position_weight=D(1), fee_bps=D(0), slippage_bps=D(0))


class SplitScript(Script):
    def on_split(self, ratio): pass


class CorporateActionTests(unittest.TestCase):
    def test_dividend_preserves_equity_and_only_later_becomes_cash(self):
        b = bars([100, 100, 99, 99, 99])
        a = Dividend(b[2].date, b[3].date, D(1), "fixture")
        r = run(b, BuyAndHold(), CFG, actions=(a,))
        self.assertEqual([p.equity for p in r.equity], [D(1000)] * 5)
        self.assertEqual([p.cash for p in r.equity], [D(1000), D(0), D(0), D(0), D(10)])
        self.assertEqual([p.receivable for p in r.equity], [D(0), D(0), D(10), D(10), D(0)])

    def test_seller_on_ex_date_keeps_entitlement(self):
        b = bars([100, 100, 99, 99, 99])
        r = run(b, Script({0:"BUY", 1:"SELL"}), CFG,
                actions=(Dividend(b[2].date, b[3].date, D(1), "fixture"),))
        self.assertEqual((r.equity[2].cash, r.equity[2].receivable), (D(990), D(10)))
        self.assertEqual(r.equity[-1].cash, D(1000))

    def test_buyer_on_ex_date_has_no_entitlement(self):
        b = bars([100, 100, 99, 99, 99])
        r = run(b, Script({1:"BUY"}), CFG,
                actions=(Dividend(b[2].date, b[3].date, D(1), "fixture"),))
        self.assertFalse(r.action_ledger)
        self.assertEqual(r.equity[-1].receivable, D(0))

    def test_unpaid_dividend_is_marked_but_not_spendable(self):
        b = bars([100, 100, 99])
        r = run(b, BuyAndHold(), CFG, actions=(Dividend(b[2].date, date(2025,2,1), D(1), "fixture"),))
        self.assertEqual((r.equity[-1].cash, r.equity[-1].receivable, r.equity[-1].equity), (D(0),D(10),D(1000)))

    def test_split_conserves_equity_and_adjusts_sell_quantity(self):
        b = bars([100, 100, 50, 50])
        r = run(b, SplitScript({0:"BUY",2:"SELL"}), CFG, actions=(Split(b[2].date,D(2),"fixture"),))
        self.assertEqual([p.equity for p in r.equity], [D(1000)]*4)
        self.assertEqual(r.fills[-1].quantity, D(20))

    def test_split_rebases_frozen_retest_level(self):
        b = bars([100,100,102,50,51,52])
        r = run(b, BreakoutRetest(BreakoutConfig(lookback=2)), CFG, actions=(Split(b[3].date,D(2),"fixture"),))
        self.assertEqual(r.signals[0].date,b[3].date)
        self.assertEqual(r.signals[0].decision.level,D(50))
        self.assertEqual(r.fills[0].price,D(51))

    def test_split_rebases_entry_without_false_stop(self):
        b = bars([100,100,102,100,100,50,50])
        r = run(b, BreakoutRetest(BreakoutConfig(lookback=2)), CFG, actions=(Split(b[5].date,D(2),"fixture"),))
        self.assertEqual(len(r.fills),1)
        self.assertEqual(r.equity[-1].equity,D(1000))
        self.assertFalse(any(s.decision.action == "SELL" for s in r.signals))

    def test_future_split_cannot_change_earlier_signals_or_equity(self):
        b = bars([100,100,102,100,100,50])
        short = run(b[:-1], BreakoutRetest(BreakoutConfig(lookback=2)), CFG)
        long = run(b, BreakoutRetest(BreakoutConfig(lookback=2)), CFG, actions=(Split(b[-1].date,D(2),"fixture"),))
        self.assertEqual(short.equity,long.equity[:-1])
        self.assertEqual(short.signals,tuple(s for s in long.signals if s.date < b[-1].date))

    def test_reverse_split_fractional_holdings_fail(self):
        b = bars([100,100,400])
        with self.assertRaisesRegex(ValueError,"fractional"):
            run(b, BuyAndHold(), CFG, actions=(Split(b[-1].date,D('.25'),"fixture"),))

    def test_unknown_strategy_cannot_silently_mishandle_split(self):
        b=bars([100,50])
        with self.assertRaisesRegex(ValueError,"on_split"):
            run(b, Script({}), actions=(Split(b[-1].date,D(2),"fixture"),))

    def test_actions_validate_dates_order_large_distributions(self):
        b=bars([100,100,100])
        a=Dividend(b[1].date,b[2].date,D(1),"fixture")
        for events in ((a,a),(replace(a,ex_date=date(2024,1,1)),),(replace(a,amount=D(25)),)):
            with self.assertRaises(ValueError): run(b,BuyAndHold(),actions=events)
        with self.assertRaises(ValueError): Dividend(b[2].date,b[1].date,D(1),"fixture")

    def test_adjusted_prices_and_malformed_json_contract_rejected(self):
        obj={"schema_version":1,"symbol":"TEST","price_basis":"adjusted","events":[]}
        with self.assertRaisesRegex(ValueError,"as_traded"): parse_actions(json.dumps(obj).encode(),"TEST")

    def test_action_identity_prevents_wrong_ledger_bundle(self):
        fixture=Path(__file__).parent/'fixtures/synthetic.csv'
        data=Dataset.from_path(fixture,"TEST","synthetic")
        a=Dividend(data.bars[2].date,data.bars[3].date,D(1),"fixture")
        result=run(data.bars,BreakoutRetest(),actions=(a,))
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"corporate actions"):
                save_bundle(Path(d),data,{"breakout_retest":result})

    def test_external_decimal_traps_do_not_affect_actions(self):
        b=bars([100,100,99,99])
        a=Dividend(b[2].date,b[2].date,D('1.000001'),"fixture")
        expected=run(b,BuyAndHold(),CFG,actions=(a,))
        with localcontext() as ctx:
            ctx.prec=4
            ctx.traps[Inexact]=True
            self.assertEqual(run(b,BuyAndHold(),CFG,actions=(a,)),expected)


if __name__ == '__main__': unittest.main()
