from datetime import date, datetime, timezone
from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from quant_research.calendar import schedule
from quant_research.market_data import _parse, create_snapshot, load_snapshot, request_url

START, END = date(2025, 1, 6), date(2025, 1, 11)


def payload():
    sessions = schedule(START, END)
    n = len(sessions)
    return {"chart": {"error": None, "result": [{
        "meta": {"symbol": "XLF", "currency": "USD", "instrumentType": "ETF",
                 "exchangeName": "PCX", "exchangeTimezoneName": "America/New_York", "dataGranularity": "1d"},
        "timestamp": [int(s.open_utc.timestamp()) for s in sessions],
        "indicators": {"quote": [{"open": [50]*n, "high": [51]*n, "low": [49]*n, "close": [50]*n, "volume": [100000]*n}]}
    }]}}


def raw(p): return json.dumps(p).encode()


class CalendarTests(unittest.TestCase):
    def test_national_mourning_closure_and_weekends(self):
        self.assertEqual([s.date.day for s in schedule(START, END)], [6, 7, 8, 10])

    def test_2025_session_count(self):
        self.assertEqual(len(schedule(date(2025, 1, 1), date(2026, 1, 1))), 250)

    def test_holidays_and_early_close(self):
        sessions = schedule(date(2025, 7, 3), date(2025, 7, 7))
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].close_utc.hour, 17)
        self.assertEqual((sessions[0].close_utc-sessions[0].open_utc).total_seconds(), 3.5*3600)

    def test_dst_changes_utc_hours(self):
        before = schedule(date(2025, 3, 7), date(2025, 3, 8))[0]
        after = schedule(date(2025, 3, 10), date(2025, 3, 11))[0]
        self.assertEqual((before.open_utc.hour, after.open_utc.hour), (14, 13))

    def test_outside_coverage_is_rejected(self):
        with self.assertRaises(ValueError): schedule(date(2024, 1, 1), date(2025, 1, 1))


class ProviderTests(unittest.TestCase):
    def test_nyse_stock_uses_same_strict_admission(self):
        p=payload()
        p['chart']['result'][0]['meta'].update(symbol='TEST',instrumentType='EQUITY',exchangeName='NYQ')
        normalized,quality=_parse(raw(p),'TEST',START,END)
        self.assertEqual(quality['provider_metadata']['instrumentType'],'EQUITY')
        self.assertEqual(quality['session_count'],4)

    def dividend_fixture(self, amount='0.178776'):
        p=payload()
        stamp=p['chart']['result'][0]['timestamp'][1]
        p['chart']['result'][0]['events']={'dividends':{str(stamp):{'date':stamp,'amount':0.179}}}
        supplement={'schema_version':1,'symbol':'XLF','price_basis':'as_traded','events':[
            {'type':'dividend','ex_date':'2025-01-07','pay_date':'2025-01-08','amount':amount,'source':'issuer fixture'}]}
        return raw(p),raw(supplement)

    def test_supplement_preserves_exact_amount_and_records_vendor_rounding(self):
        vendor,actions=self.dividend_fixture()
        normalized,quality=_parse(vendor,'XLF',START,END,actions)
        self.assertEqual(quality['reported_action_count'],1)
        self.assertEqual(quality['dividend_reconciliation'][0]['match'],'vendor_rounded_to_0.001')
        with tempfile.TemporaryDirectory() as d:
            p=create_snapshot(Path(d),vendor,'XLF',START,END,'2025-02-01T00:00:00+00:00',request_url('XLF',START,END),actions)
            loaded=load_snapshot(p)
            self.assertEqual(str(loaded.actions[0].amount),'0.178776')
            self.assertEqual(loaded.actions_raw,actions)
            (p/'actions.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'integrity'): load_snapshot(p)

    def test_mismatched_or_missing_supplement_never_silently_passes(self):
        vendor,actions=self.dividend_fixture('0.17')
        with self.assertRaisesRegex(ValueError,'disagrees'): _parse(vendor,'XLF',START,END,actions)
        vendor,actions=self.dividend_fixture()
        with self.assertRaisesRegex(ValueError,'supplement'): _parse(vendor,'XLF',START,END)
        with self.assertRaisesRegex(ValueError,'disagrees'): _parse(raw(payload()),'XLF',START,END,actions)

    def test_pay_date_before_ex_date_is_rejected(self):
        vendor,actions=self.dividend_fixture()
        p=json.loads(actions)
        p['events'][0]['pay_date']='2025-01-06'
        with self.assertRaisesRegex(ValueError,'pay_date'): _parse(vendor,'XLF',START,END,raw(p))

    def test_round_trip_snapshot_and_revalidation(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = create_snapshot(root, raw(payload()), "XLF", START, END, "2025-02-01T00:00:00+00:00", request_url("XLF", START, END))
            data = load_snapshot(p)
            self.assertEqual(len(data.bars), 4)
            self.assertEqual(data.symbol, "XLF")
            self.assertEqual(json.loads(data.provenance_json)["quality"]["status"], "passed")

    def test_missing_first_middle_or_last_session_is_rejected(self):
        for index in (0, 1, -1):
            p = payload(); r = p["chart"]["result"][0]
            r["timestamp"].pop(index)
            for values in r["indicators"]["quote"][0].values(): values.pop(index)
            with self.assertRaisesRegex(ValueError, "session mismatch"):
                _parse(raw(p), "XLF", START, END)

    def test_unexpected_closed_session_is_rejected(self):
        p = payload(); r = p["chart"]["result"][0]
        r["timestamp"][-1] = int(datetime(2025, 1, 9, 14, 30, tzinfo=timezone.utc).timestamp())
        with self.assertRaisesRegex(ValueError, "session mismatch"):
            _parse(raw(p), "XLF", START, END)

    def test_actions_are_not_silently_ignored(self):
        for category in ("dividends", "splits", "capitalGains", "unknownAction"):
            p = payload(); p["chart"]["result"][0]["events"] = {category: {"123": {"date": 123}}}
            with self.assertRaisesRegex(ValueError, "corporate actions"):
                _parse(raw(p), "XLF", START, END)

    def test_nulls_duplicates_and_misalignment_are_rejected(self):
        for kind in ("null", "duplicate", "misaligned", "volume"):
            p = payload(); r = p["chart"]["result"][0]; q = r["indicators"]["quote"][0]
            if kind == "null": q["close"][0] = None
            elif kind == "duplicate": r["timestamp"][1] = r["timestamp"][0]
            elif kind == "misaligned": q["open"].pop()
            else: q["volume"][0] = 0
            with self.assertRaises(ValueError): _parse(raw(p), "XLF", START, END)

    def test_wrong_instrument_contract_rejected(self):
        for field, value in (("symbol", "SPY"), ("currency", "EUR"), ("instrumentType", "MUTUALFUND"), ("dataGranularity", "1h"), ("exchangeName", "NMS")):
            p = payload(); p["chart"]["result"][0]["meta"][field] = value
            with self.assertRaises(ValueError): _parse(raw(p), "XLF", START, END)

    def test_incomplete_session_not_admitted(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "not completed"):
                create_snapshot(Path(d), raw(payload()), "XLF", START, END, "2025-01-10T15:00:00+00:00", request_url("XLF", START, END))

    def test_tampered_snapshot_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = create_snapshot(Path(d), raw(payload()), "XLF", START, END, "2025-02-01T00:00:00+00:00", request_url("XLF", START, END))
            (p / "bars.csv").write_bytes(b"altered")
            with self.assertRaisesRegex(ValueError, "integrity"):
                load_snapshot(p)


if __name__ == "__main__": unittest.main()
