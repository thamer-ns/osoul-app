#test/test_critical.py
import unittest
import pandas as pd
import numpy as np

from ai_engine_core.liquidity_gate import evaluate_liquidity_gate
from ai_engine_core.multi_timeframe import evaluate_daily_weekly_alignment, resample_weekly_saudi
from ai_engine_core.score_normalization import normalize_score
from ai_engine_core.portfolio import compute_market_value


class TestCriticalEnhancements(unittest.TestCase):
    def _make_df(self, n=80, low_liq=False):
        idx = pd.date_range('2025-01-01', periods=n, freq='B')
        close = pd.Series(np.linspace(20, 30, n), index=idx)
        open_ = close * 0.99
        high = close * 1.01
        low = close * 0.98
        vol = pd.Series((1000 if low_liq else 250000), index=idx)
        return pd.DataFrame({'Open':open_, 'High':high, 'Low':low, 'Close':close, 'Volume':vol}, index=idx)

    def test_liquidity_gate_flags_low_liquidity(self):
        df = self._make_df(low_liq=True)
        g = evaluate_liquidity_gate(df)
        self.assertIsInstance(g, dict)
        self.assertFalse(g.get('pass', True))
        self.assertLessEqual(float(g.get('confidence_cap') or 100), 60)

    def test_weekly_alignment_works(self):
        df = self._make_df(low_liq=False)
        w = resample_weekly_saudi(df)
        self.assertFalse(w.empty)
        res = evaluate_daily_weekly_alignment(df, daily_bias='buy')
        self.assertIn('aligned', res)
        self.assertIn('weekly_trend', res)

    def test_score_normalization_with_injected_rows(self):
        rows = [1,2,3,4,5,6,7,8,9,10]*4
        cal = normalize_score(raw_score=9, rows=rows, timeframe='1d', sector='banks')
        self.assertTrue(cal['available'])
        self.assertGreaterEqual(cal['percentile'], 70)
        self.assertIsNotNone(cal['zscore'])

    def test_compute_market_value(self):
        self.assertAlmostEqual(compute_market_value(100, 28.18), 2818.0, places=6)
        self.assertAlmostEqual(compute_market_value('100', '28.18'), 2818.0, places=6)


if __name__ == '__main__':
    unittest.main()
