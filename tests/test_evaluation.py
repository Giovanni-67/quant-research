from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from test_core import bars, Script
from quant_research.data import Dataset
from quant_research.engine import run
from quant_research.evaluation import evaluate
from quant_research.models import Config
from quant_research.strategies import BuyAndHold, TechnicalConfig, TechnicalSwing


def dataset():
    b=bars(([100]*20+[90,95,100,105,102,98])*3)
    raw='date,open,high,low,close,volume\n'+''.join(f'{x.date},{x.open},{x.high},{x.low},{x.close},{x.volume}\n' for x in b)
    return Dataset(raw.encode(),'TEST','synthetic')


class EvaluationTests(unittest.TestCase):
    def test_no_decisions_or_orders_carry_across_boundary(self):
        b=bars([100,100,100,100,100])
        result=run(b,Script({0:'BUY',3:'BUY'}),decision_start=b[3].date)
        self.assertEqual(len(result.signals),1)
        self.assertEqual(result.fills[0].date,b[4].date)
        self.assertEqual(result.equity[0].equity,D(1000))

    def test_baseline_starts_on_first_evaluation_close(self):
        b=bars([100,100,100,100,100])
        r=run(b,BuyAndHold(),decision_start=b[3].date)
        self.assertEqual(r.fills[0].signal_date,b[3].date)
        self.assertEqual(r.fills[0].date,b[4].date)

    def test_trend_uses_prior_prices_but_first_fills_next_open(self):
        b=bars([100,100,99,98,102,104])
        cfg=TechnicalConfig(family='trend',lookback=3,fast_window=2)
        r=run(b,TechnicalSwing(cfg),decision_start=b[4].date)
        self.assertEqual(r.signals[0].date,b[4].date)
        self.assertEqual(r.fills[0].date,b[5].date)

    def test_bollinger_reentry_and_holding_exit(self):
        b=bars([100,100,100,90,100,100,100,100])
        cfg=TechnicalConfig(family='bollinger',lookback=3,fast_window=1,width=D(1),max_holding_bars=1)
        r=run(b,TechnicalSwing(cfg))
        self.assertEqual(r.signals[0].date,b[4].date)
        self.assertEqual([f.action for f in r.fills],['BUY','SELL'])
        self.assertEqual(r.fills[1].date,b[6].date)

    def test_both_new_families_are_causal(self):
        b=dataset().bars
        for family in ('trend','bollinger'):
            config=TechnicalConfig(family=family)
            prefix=run(b[:40],TechnicalSwing(config))
            changed=b[:40]+tuple(replace(x,open=D(10000),high=D(10000),low=D(10000),close=D(10000)) for x in b[40:])
            full=run(changed,TechnicalSwing(config))
            self.assertEqual(prefix.equity,full.equity[:40])
            self.assertEqual(prefix.signals,tuple(s for s in full.signals if s.date<=b[39].date))

    def test_registry_written_before_failed_simulation(self):
        data=dataset()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch('quant_research.evaluation.run',side_effect=ValueError('forced failure')):
                with self.assertRaisesRegex(ValueError,'forced failure'):
                    evaluate(root,data,data.bars[35].date)
            plans=list((root/'plans').glob('*/plan.json'))
            self.assertEqual(len(plans),1)
            self.assertEqual(len(json.loads(plans[0].read_text())['candidates']),5)
            self.assertFalse((root/'comparisons').exists())

    def test_comparison_reproduces_and_never_selects_a_winner(self):
        data=dataset()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            first=evaluate(root,data,data.bars[35].date)
            self.assertEqual(first,evaluate(root,data,data.bars[35].date))
            plan=json.loads((first/'plan.json').read_text())
            self.assertEqual(plan['rules']['selection'],'none; disclose all candidates')
            comparison=json.loads((first/'comparison.json').read_text())
            self.assertEqual(len(comparison),5)
            ids=json.loads((first/'bundles.json').read_text())
            result=json.loads((root/'runs'/ids['evaluation']/'results.json').read_text())
            for row in result.values():
                self.assertEqual(row['result']['equity'][0]['date'],str(data.bars[35].date))
                self.assertEqual(row['result']['equity'][0]['equity'],'1000')
            altered=evaluate(root,data,data.bars[36].date)
            self.assertNotEqual(first,altered)

    def test_evaluation_future_cannot_change_development_results(self):
        data=dataset()
        changed=data.raw.decode().splitlines()
        changed[-1]=changed[-1].split(',')[0]+',1,1,1,1,1000'
        other=Dataset(('\n'.join(changed)+'\n').encode(),'TEST','synthetic')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            a=evaluate(root,data,data.bars[35].date)
            z=evaluate(root,other,data.bars[35].date)
            am=json.loads((a/'comparison.json').read_text())
            zm=json.loads((z/'comparison.json').read_text())
            self.assertEqual({k:v['development'] for k,v in am.items()}, {k:v['development'] for k,v in zm.items()})

    def test_insufficient_evaluation_or_warmup_rejected(self):
        data=dataset()
        for index in (10,-3):
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaisesRegex(ValueError,'warm-up'):
                    evaluate(Path(d),data,data.bars[index].date)


if __name__ == '__main__': unittest.main()
