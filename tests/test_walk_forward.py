from dataclasses import replace
from decimal import Decimal as D, Inexact, localcontext
from pathlib import Path
import csv
import json
import tempfile
import unittest
from unittest.mock import patch

from test_core import bars
from quant_research.data import Dataset
from quant_research.models import Config
from quant_research.strategies import BreakoutConfig
from quant_research.walk_forward import (
    ACTIVE, TrainingScore, WalkForwardConfig, folds_for, select_candidate, walk_forward,
    _window_results,
)


def synthetic(prices=None, actions=b''):
    prices = prices if prices is not None else ([100]*20+[90,95,100,105,102,98])*5
    raw='date,open,high,low,close,volume\n'+''.join(
        f'{b.date},{b.open},{b.high},{b.low},{b.close},{b.volume}\n' for b in bars(prices))
    return Dataset(raw.encode(),'TEST','synthetic',actions_raw=actions)


SMALL = WalkForwardConfig(train_sessions=30, test_sessions=25, gap_sessions=3,
                          min_training_round_trips=1, cost_multipliers=(D(1), D(2)))


class FoldTests(unittest.TestCase):
    def test_rolling_windows_gap_and_nonoverlapping_tests(self):
        folds=folds_for(250,WalkForwardConfig())
        self.assertEqual((folds[0].train_start,folds[0].train_end,folds[0].test_start,folds[0].test_end),(21,101,106,146))
        self.assertEqual([f.test_end-f.test_start for f in folds],[40,40,40,24])
        for f in folds:
            self.assertEqual(f.train_end-f.train_start,80)
            self.assertEqual(f.test_start-f.train_end,5)
        for a,b in zip(folds,folds[1:]): self.assertEqual(a.test_end,b.test_start)

    def test_singleton_tail_explicitly_omitted(self):
        folds=folds_for(187,WalkForwardConfig())
        self.assertEqual(len(folds),2)
        self.assertEqual(folds[-1].test_end,186)

    def test_bad_config_and_insufficient_history(self):
        for kwargs in ({'train_sessions':True},{'test_sessions':1},{'gap_sessions':-1},
                       {'min_training_round_trips':0},{'cost_multipliers':(D(2),)},
                       {'cost_multipliers':(D(1),D(1))},{'cost_multipliers':(D('NaN'),)}):
            with self.assertRaises(ValueError): WalkForwardConfig(**kwargs)
        with self.assertRaisesRegex(ValueError,'two test folds'): folds_for(146,WalkForwardConfig())


class SelectionTests(unittest.TestCase):
    def scores(self,returns,counts=(3,3,3)):
        return tuple(TrainingScore(name,D(value),count) for name,value,count in zip(ACTIVE,returns,counts))

    def test_highest_eligible_return_and_cash_fallback(self):
        self.assertEqual(select_candidate(self.scores(['.02','.05','.03']),3),'breakout_retest')
        self.assertEqual(select_candidate(self.scores(['.02','.50','.03'],(3,1,3)),3),'trend_swing')
        self.assertEqual(select_candidate(self.scores(['-.02','0','-.03']),3),'cash')
        self.assertEqual(select_candidate(self.scores(['.02','.05','.03'],(2,2,2)),3),'cash')

    def test_ties_are_stable_and_input_order_does_not_matter(self):
        s=self.scores(['.03','.03','.03'])
        self.assertEqual(select_candidate(s,3),'bollinger_swing')
        self.assertEqual(select_candidate(tuple(reversed(s)),3),'bollinger_swing')

    def test_missing_duplicate_or_invalid_scores_fail(self):
        scores=self.scores(['0','0','0'])
        for s in (scores[:2],(scores[0],scores[0],scores[2])):
            with self.assertRaises(ValueError): select_candidate(s,3)
        with self.assertRaises(ValueError): TrainingScore('trend_swing',D('NaN'),3)
        with self.assertRaises(ValueError): TrainingScore('trend_swing',D(0),True)

    def test_selector_not_affected_by_callers_decimal_context(self):
        s=self.scores(['.030001','.030002','.03'])
        with localcontext() as ctx:
            ctx.prec=2
            ctx.traps[Inexact]=True
            self.assertEqual(select_candidate(s,3),'breakout_retest')


class WalkForwardTests(unittest.TestCase):
    def test_training_receivable_and_test_dividend_do_not_cross_account_boundary(self):
        data=synthetic()
        fold=folds_for(len(data.bars),SMALL)[0]
        events=[{'type':'dividend','ex_date':str(data.bars[fold.train_end-1].date),
                 'pay_date':str(data.bars[fold.test_start+2].date),'amount':'1','source':'synthetic'},
                {'type':'dividend','ex_date':str(data.bars[fold.test_start+3].date),
                 'pay_date':str(data.bars[fold.test_start+5].date),'amount':'.5','source':'synthetic'}]
        actions=json.dumps({'schema_version':1,'symbol':'TEST','price_basis':'as_traded','events':events}).encode()
        dataset=synthetic(actions=actions)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            result=walk_forward(root,dataset,protocol=SMALL)
            record=json.loads((result/'folds.json').read_text())[0]
            training=json.loads((root/'runs'/record['selection']['training_bundle']/'results.json').read_text())
            baseline=training['buy_and_hold_same_allocation']['result']
            self.assertGreater(D(baseline['equity'][-1]['receivable']),0)
            testing=json.loads((root/'runs'/record['scenarios'][0]['test_bundle']/'results.json').read_text())
            baseline=testing['buy_and_hold_same_allocation']['result']
            ledger=baseline['action_ledger']
            self.assertTrue(ledger)
            self.assertTrue(all(a['event_date']==events[1]['ex_date'] for a in ledger))
            self.assertEqual(baseline['equity'][0]['receivable'],'0')

    def test_future_corporate_action_amount_cannot_change_training_scores(self):
        data=synthetic()
        fold=folds_for(len(data.bars),SMALL)[0]
        def with_dividend(amount):
            event={'type':'dividend','ex_date':str(data.bars[fold.test_start+3].date),
                   'pay_date':str(data.bars[fold.test_start+5].date),'amount':amount,'source':'synthetic'}
            raw=json.dumps({'schema_version':1,'symbol':'TEST','price_basis':'as_traded','events':[event]}).encode()
            return synthetic(actions=raw)
        with tempfile.TemporaryDirectory() as d:
            a=walk_forward(Path(d)/'a',with_dividend('1'),protocol=SMALL)
            b=walk_forward(Path(d)/'b',with_dividend('2'),protocol=SMALL)
            x=json.loads((a/'folds.json').read_text())[0]['selection']
            y=json.loads((b/'folds.json').read_text())[0]['selection']
            self.assertEqual(x['scores'],y['scores'])
            self.assertEqual(x['selected'],y['selected'])
            self.assertEqual(x['training_actions_sha256'],y['training_actions_sha256'])

    def test_end_to_end_reproducibility_and_cost_scenarios(self):
        data=synthetic()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            result=walk_forward(root,data,protocol=SMALL)
            self.assertEqual(result,walk_forward(root,data,protocol=SMALL))
            records=json.loads((result/'folds.json').read_text())
            summary=json.loads((result/'summary.json').read_text())
            self.assertEqual(summary['fold_count'],3)
            self.assertEqual(summary['test_sessions'],75)
            self.assertEqual(summary['unused_tail_sessions'],1)
            self.assertTrue(any(r['selection']['selected'] != 'cash' for r in records))
            for record in records:
                selected=record['selection']['selected']
                self.assertEqual(len(record['scenarios']),2)
                for scenario in record['scenarios']:
                    self.assertEqual(scenario['selected'],selected)
                    self.assertEqual(len(scenario['metrics']),5)
                    saved=json.loads((root/'runs'/scenario['test_bundle']/'results.json').read_text())
                    for row in saved.values():
                        r=row['result']
                        self.assertEqual(r['equity'][0]['cash'],'1000')
                        self.assertEqual(r['equity'][0]['quantity'],'0')
                        self.assertEqual(r['equity'][0]['receivable'],'0')
                        self.assertEqual(r['equity'][0]['date'],str(data.bars[record['fold']['test_start']].date))
                        self.assertTrue(all(f['signal_date'] >= r['equity'][0]['date'] and f['date'] > f['signal_date'] for f in r['fills']))
            with (result/'fold_metrics.csv').open(newline='') as handle:
                self.assertEqual(len(list(csv.DictReader(handle))),30)

    def test_test_and_gap_price_changes_cannot_change_first_selection(self):
        base=[100]*20+[90,95,100,105,102,98]
        prices=base*5
        data=synthetic(prices)
        cutoff=folds_for(len(prices),SMALL)[0].train_end
        changed=synthetic(prices[:cutoff]+[10000]*(len(prices)-cutoff))
        with tempfile.TemporaryDirectory() as d:
            a=walk_forward(Path(d)/'original',data,protocol=SMALL)
            b=walk_forward(Path(d)/'mutated',changed,protocol=SMALL)
            first=json.loads((a/'folds.json').read_text())[0]
            other=json.loads((b/'folds.json').read_text())[0]
            self.assertEqual(first['selection']['selected'],other['selection']['selected'])
            self.assertEqual(first['selection']['scores'],other['selection']['scores'])
            self.assertEqual(first['selection']['training_bars_sha256'],other['selection']['training_bars_sha256'])
            self.assertEqual(first['training_metrics'],other['training_metrics'])

    def test_later_fold_mutation_preserves_entire_first_test_ledger(self):
        data=synthetic()
        cutoff=folds_for(len(data.bars),SMALL)[0].test_end
        changed=synthetic([b.close for b in data.bars[:cutoff]]+[D(200)]*(len(data.bars)-cutoff))
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            a=walk_forward(root/'a',data,protocol=SMALL)
            b=walk_forward(root/'b',changed,protocol=SMALL)
            ar=json.loads((a/'folds.json').read_text())[0]
            br=json.loads((b/'folds.json').read_text())[0]
            for x,y in zip(ar['scenarios'],br['scenarios']):
                ax=(root/'a'/'runs'/x['test_bundle']/'results.json').read_bytes()
                by=(root/'b'/'runs'/y['test_bundle']/'results.json').read_bytes()
                self.assertEqual(ax,by)

    def test_engines_never_receive_future_bars_and_selector_called_once_per_fold(self):
        data=synthetic()
        windows=folds_for(len(data.bars),SMALL)
        seen=[]
        def inspect(dataset,start,config,breakout):
            seen.append((len(dataset.bars),start))
            return _window_results(dataset,start,config,breakout)
        with tempfile.TemporaryDirectory() as d:
            with patch('quant_research.walk_forward._window_results',side_effect=inspect), patch(
                'quant_research.walk_forward.select_candidate',wraps=select_candidate) as selection:
                walk_forward(Path(d),data,protocol=SMALL)
            self.assertEqual(selection.call_count,len(windows))
        expected=[]
        for f in windows: expected.extend([(f.train_end,f.train_start)]+[(f.test_end,f.test_start)]*2)
        self.assertEqual(seen,expected)

    def test_frozen_choice_survives_test_failure(self):
        data=synthetic()
        calls=0
        def fail(dataset,start,config,breakout):
            nonlocal calls
            calls+=1
            if calls==2: raise ValueError('test failed')
            return _window_results(dataset,start,config,breakout)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch('quant_research.walk_forward._window_results',side_effect=fail):
                with self.assertRaisesRegex(ValueError,'test failed'): walk_forward(root,data,protocol=SMALL)
            self.assertEqual(len(list((root/'plans').glob('*/plan.json'))),1)
            self.assertEqual(len(list((root/'selections').glob('*/selection.json'))),1)
            self.assertFalse((root/'comparisons').exists())

    def test_changed_protocol_changes_identity(self):
        data=synthetic()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            first=walk_forward(root,data,protocol=SMALL)
            second=walk_forward(root,data,protocol=replace(SMALL,min_training_round_trips=2))
            self.assertNotEqual(first,second)

    def test_invalid_stress_costs_fail_before_registration(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(ValueError):
                walk_forward(root,synthetic(),Config(fee_bps=D(6000)),SMALL)
            self.assertFalse((root/'plans').exists())

    def test_decimal_isolation_of_whole_workflow(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            data=synthetic()
            first=walk_forward(root,data,protocol=SMALL)
            with localcontext() as ctx:
                ctx.prec=3
                ctx.traps[Inexact]=True
                self.assertEqual(first,walk_forward(root,data,protocol=SMALL))


if __name__ == '__main__': unittest.main()
