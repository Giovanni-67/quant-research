from dataclasses import replace
from datetime import date,timedelta
from decimal import Decimal as D, Inexact, localcontext
from pathlib import Path
import json
import math
import random
import tempfile
import unittest

from test_core import bars
from test_walk_forward import synthetic, SMALL
from quant_research.engine import run
from quant_research.models import Config
from quant_research.strategies import BuyAndHold,CashOnly
from quant_research.uncertainty import (
    NAMES, BENCHMARK, FoldSample, UncertaintyConfig, analyze, paired_sample, holm, circular_indices, _quantile,
)
from quant_research.walk_forward import walk_forward


def samples(length=60):
    result=[]
    for f in range(2):
        dates=tuple(date(2025,1,1)+timedelta(days=f*length+i) for i in range(length))
        noise=tuple((((i*i*17+f*3)%101)-50)*.00004 for i in range(length))
        center=math.fsum(noise)/length
        rows=tuple((.02+v-center, -.02+v-center, v-center) for v in noise)
        result.append(FoldSample(dates,rows,(20,20,20)))
    return tuple(result)


FAST=UncertaintyConfig(repetitions=199,block_lengths=(3,5,10),min_sessions=100,min_blocks=10)


class UncertaintyTests(unittest.TestCase):
    def test_holm_hand_calculation_and_original_order(self):
        self.assertEqual(holm((.01,.04,.03)),(.03,.06,.06))
        self.assertEqual(holm((.5,.8,.1))[:2],(1.,1.))
        self.assertAlmostEqual(holm((.5,.8,.1))[2],.3)
        self.assertEqual(holm((0.,1.,.01)),(0.,1.,.02))
        self.assertEqual(holm((.02,.02,.02)),(.06,.06,.06))

    def test_invalid_pvalues_and_config(self):
        for values in ((),(-.1,), (float('nan'),), (1.1,), (True,)):
            with self.assertRaises(ValueError): holm(values)
        for kwargs in ({'repetitions':98},{'seed':True},{'block_lengths':(5,3)},
                       {'block_lengths':(0,)},{'alpha':float('nan')},{'min_blocks':0}):
            with self.assertRaises(ValueError): UncertaintyConfig(**kwargs)

    def test_circular_blocks_wrap_and_preserve_adjacent_indices(self):
        class Last:
            def randrange(self,n): return n-1
        self.assertEqual(circular_indices(7,3,Last()),(6,0,1,6,0,1,6))
        with self.assertRaises(ValueError): circular_indices(3,4,Last())

    def test_quantiles_match_linear_interpolation(self):
        self.assertEqual(_quantile([0.,10.,20.],.25),5.)
        self.assertEqual(_quantile([0.,10.,20.],.5),10.)
        self.assertEqual(_quantile([0.,10.,20.],1.),20.)

    def test_paired_equity_returns_hand_calculation_and_alignment(self):
        cfg=Config(max_position_weight=D(1),fee_bps=D(0),slippage_bps=D(0))
        b=bars([100,100,110,100])
        cash=run(b,CashOnly(),cfg)
        benchmark=run(b,BuyAndHold(),cfg)
        r={name:cash for name in NAMES}; r[BENCHMARK]=benchmark
        paired=paired_sample(r)
        self.assertEqual(paired.dates,tuple(x.date for x in b[1:]))
        self.assertEqual(paired.differences[0],(0.,0.,0.))
        self.assertEqual(paired.differences[1],(-.1,-.1,-.1))
        self.assertAlmostEqual(paired.differences[2][0],1/11)
        r[NAMES[0]]=replace(cash,equity=cash.equity[:-1])
        with self.assertRaisesRegex(ValueError,'identical'): paired_sample(r)

    def test_mismatched_costs_or_actions_cannot_be_paired(self):
        b=bars([100,100,110])
        benchmark=run(b,BuyAndHold())
        r={name:run(b,CashOnly()) for name in NAMES};r[BENCHMARK]=benchmark
        r[NAMES[0]]=replace(r[NAMES[0]],actions_sha256='other')
        with self.assertRaisesRegex(ValueError,'identical'): paired_sample(r)
        r[NAMES[0]]=run(b,CashOnly(),Config(fee_bps=D(10)))
        with self.assertRaisesRegex(ValueError,'identical'): paired_sample(r)

    def test_synthetic_positive_negative_and_null_differentials(self):
        result=analyze(samples(),FAST)
        self.assertEqual(result['family_size'],9)
        for row in result['rows']:
            if row['candidate']==NAMES[0]:
                self.assertTrue(row['exploratory_reject_null'])
                self.assertGreater(row['exploratory_percentile_interval'][0],0)
                self.assertGreater(row['raw_pvalue'],0)
            else:
                self.assertFalse(row['exploratory_reject_null'])
                self.assertGreaterEqual(row['raw_pvalue'],.05)

    def test_identical_candidate_columns_share_bootstrap_draws(self):
        ss=tuple(replace(s,differences=tuple((row[0],)*3 for row in s.differences)) for s in samples())
        result=analyze(ss,FAST)
        for i in range(0,9,3):
            rows=result['rows'][i:i+3]
            self.assertEqual(rows[0]['raw_pvalue'],rows[1]['raw_pvalue'])
            self.assertEqual(rows[1]['exploratory_percentile_interval'],rows[2]['exploratory_percentile_interval'])

    def test_sparse_trials_remain_in_family_with_pvalues_withheld(self):
        ss=tuple(replace(s,round_trips=(0,0,0)) for s in samples())
        result=analyze(ss,FAST)
        self.assertEqual(result['family_size'],9)
        for row in result['rows']:
            self.assertIsNone(row['raw_pvalue'])
            self.assertIsNone(row['holm_pvalue'])
            self.assertIn('too_few_completed_trades',row['withheld_reasons'])
            self.assertFalse(row['exploratory_reject_null'])

    def test_constant_and_short_samples_do_not_claim_certainty(self):
        constant=tuple(replace(s,differences=tuple((.1,0.,-.1) for _ in s.differences)) for s in samples())
        result=analyze(constant,FAST)
        for row in result['rows']:
            self.assertIsNone(row['exploratory_percentile_interval'])
            self.assertIsNone(row['raw_pvalue'])
            self.assertIn('constant_differential',row['withheld_reasons'])
        short=analyze(samples(6),FAST)
        self.assertTrue(all('too_few_sessions' in row['withheld_reasons'] for row in short['rows']))

    def test_nonconstant_periodic_series_with_collapsed_bootstrap_is_withheld(self):
        periodic=tuple(replace(s,differences=tuple(((.002 if i%2 else -.002),)*3 for i in range(len(s.dates)))) for s in samples())
        result=analyze(periodic,replace(FAST,block_lengths=(10,)))
        for row in result['rows']:
            self.assertIn('degenerate_bootstrap',row['withheld_reasons'])
            self.assertIsNone(row['raw_pvalue'])

    def test_invalid_fold_dates_and_numeric_inputs(self):
        ss=samples()
        with self.assertRaisesRegex(ValueError,'non-overlapping'): analyze((ss[0],ss[0]),FAST)
        with self.assertRaises(ValueError): replace(ss[0],differences=((math.nan,0.,0.),)*60)
        with self.assertRaises(ValueError): replace(ss[0],dates=tuple(reversed(ss[0].dates)))
        with self.assertRaises(ValueError): analyze((),FAST)

    def test_seed_reproducible_and_global_random_state_untouched(self):
        state=random.getstate()
        first=analyze(samples(),FAST)
        self.assertEqual(state,random.getstate())
        self.assertEqual(first,analyze(samples(),FAST))
        # A different seed is a different registered assumption, not a search for significance.
        self.assertNotEqual(first['rows'],analyze(samples(),replace(FAST,seed=FAST.seed+1))['rows'])

    def test_registered_before_computation_and_end_to_end_artifacts(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            cfg=replace(FAST,repetitions=99)
            result=walk_forward(root,synthetic(),protocol=SMALL,uncertainty=cfg)
            plan=json.loads((result/'plan.json').read_text())
            self.assertEqual(plan['uncertainty']['seed'],cfg.seed)
            self.assertEqual(plan['uncertainty_family']['cost_scenario'],'base_only')
            self.assertTrue((result/'uncertainty.html').exists())
            self.assertTrue((result/'paired_returns.json').exists())
            diagnostic=json.loads((result/'uncertainty.json').read_text())
            self.assertEqual(diagnostic['family_size'],9)
            self.assertEqual(result,walk_forward(root,synthetic(),protocol=SMALL,uncertainty=cfg))
            without=walk_forward(root,synthetic(),protocol=SMALL)
            self.assertNotEqual(result,without)
            with localcontext() as ctx:
                ctx.prec=3
                ctx.traps[Inexact]=True
                self.assertEqual(result,walk_forward(root,synthetic(),protocol=SMALL,uncertainty=cfg))


if __name__ == '__main__': unittest.main()
