import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from tools.ttf_backtest import (
    TTFBacktestParams,
    TTFTrade,
    _parse_binance_csv,
    _simulate_exit,
    backtest_symbol,
    compute_exit_levels,
    download_month,
    normalize_candles,
    resample_closed,
    summarize,
)


def _synthetic_1m(days: int = 20, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = days * 1440
    drift = np.repeat(rng.normal(0, 0.00008, n // 720 + 1), 720)[:n]
    close = 100 * np.exp(np.cumsum(drift + rng.normal(0, 0.0008, n)))
    open_ = np.concatenate([[100.0], close[:-1]])
    wick = np.abs(rng.normal(0, 0.0005, n)) * close
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC"),
            "open": open_,
            "high": np.maximum(open_, close) + wick,
            "low": np.minimum(open_, close) - wick,
            "close": close,
            "volume": 1.0,
        }
    )


def _params(**kw) -> TTFBacktestParams:
    base = {
        "fee_rate": 0.0005,
        "slippage_pct": 0.0005,
        "min_rrr": 1.8,
        "entry_penalty_slippage": 0.001,
        "max_entry_sl_pct": 3.0,
        "risk_per_trade_pct": 1.2,
    }
    base.update(kw)
    return TTFBacktestParams(**base)


class ExitLevelsTest(unittest.TestCase):
    def test_min_distance_and_tp_multiple_buy(self):
        sl, tp, risk = compute_exit_levels("BUY", 100.0, 99.95, _params())
        self.assertAlmostEqual(risk, 0.2)  # distancia mínima 0.2%
        self.assertAlmostEqual(sl, 99.8)
        self.assertGreaterEqual(tp - 100.0, 2.5 * risk - 1e-9)

    def test_sell_polarity_and_cap(self):
        sl, tp, risk = compute_exit_levels("SELL", 100.0, 110.0, _params())
        self.assertAlmostEqual(risk, 100.0 * 3.0 * 0.95 / 100.0)
        self.assertGreater(sl, 100.0)
        self.assertLess(tp, 100.0)

    def test_invalid_sl_returns_none(self):
        self.assertIsNone(compute_exit_levels("BUY", 100.0, 0.0, _params()))


class SimulateExitTest(unittest.TestCase):
    def test_same_bar_sl_and_tp_counts_as_sl(self):
        o = np.array([100.0, 100.0])
        h = np.array([100.1, 103.0])
        low = np.array([99.9, 98.0])
        c = np.array([100.0, 100.0])
        idx, price, reason, _, _ = _simulate_exit(
            "BUY", 0, 100.0, 99.0, 102.0, o, h, low, c, _params(slippage_pct=0.0)
        )
        self.assertEqual((idx, reason), (1, "SL"))
        self.assertAlmostEqual(price, 99.0)

    def test_gap_through_stop_fills_at_open(self):
        o = np.array([100.0, 97.0])
        h = np.array([100.1, 97.5])
        low = np.array([99.5, 96.5])
        c = np.array([100.0, 97.0])
        _, price, reason, _, _ = _simulate_exit(
            "BUY", 0, 100.0, 99.0, 103.0, o, h, low, c, _params(slippage_pct=0.0)
        )
        self.assertEqual(reason, "SL")
        self.assertAlmostEqual(price, 97.0)

    def test_breakeven(self):
        o = np.array([100.0, 101.0, 100.5])
        h = np.array([100.2, 101.6, 100.6])
        low = np.array([99.9, 100.9, 99.9])
        c = np.array([100.0, 101.5, 100.0])
        _, price, reason, _, _ = _simulate_exit(
            "BUY",
            0,
            100.0,
            99.0,
            103.0,
            o,
            h,
            low,
            c,
            _params(slippage_pct=0.0, breakeven_at_r=1.5),
        )
        self.assertEqual(reason, "BREAKEVEN")
        self.assertAlmostEqual(price, 100.0)


class DataTest(unittest.TestCase):
    def test_parse_binance_csv_with_and_without_header(self):
        row = "1704067200000,100,101,99,100.5,10,1704067259999,0,0,0,0,0\n"
        header = (
            "open_time,open,high,low,close,volume,close_time,qv,count,tbv,tbqv,ignore\n"
        )
        for raw in (row, header + row):
            df = normalize_candles(_parse_binance_csv(raw.encode()))
            self.assertEqual(len(df), 1)
            self.assertEqual(df["time"].iloc[0], pd.Timestamp("2024-01-01", tz="UTC"))

    def test_microsecond_timestamps(self):
        df = pd.DataFrame(
            {
                "time": [1735689600000000],
                "open": [1],
                "high": [1],
                "low": [1],
                "close": [1],
                "volume": [1],
            }
        )
        self.assertEqual(
            normalize_candles(df)["time"].iloc[0], pd.Timestamp("2025-01-01", tz="UTC")
        )

    def test_resample_uses_open_time_labels(self):
        df = _synthetic_1m(days=1)
        r5 = resample_closed(df, "5min")
        self.assertEqual(r5["time"].iloc[1], df["time"].iloc[5])
        self.assertAlmostEqual(r5["high"].iloc[0], df["high"].iloc[:5].max())


class DownloadTest(unittest.TestCase):
    def test_download_parses_zip_and_caches(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "X-1m-2026-01.csv", "1704067200000,100,101,99,100.5,10,0,0,0,0,0,0\n"
            )
        fake = mock.MagicMock()
        fake.__enter__.return_value.read.return_value = buf.getvalue()
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch(
                "tools.ttf_backtest.urllib.request.urlopen", return_value=fake
            ) as urlopen,
        ):
            df = download_month("XUSDT", "2026-01", Path(tmp))
            self.assertEqual(len(df), 1)
            download_month("XUSDT", "2026-01", Path(tmp))  # segunda vez: caché
            self.assertEqual(urlopen.call_count, 1)


class BacktestIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = _synthetic_1m(days=20)
        cls.trades = backtest_symbol("SYN", cls.df, _params())

    def test_produces_trades_with_next_bar_entry(self):
        self.assertGreater(len(self.trades), 5)
        times = self.df.set_index("time")
        for t in self.trades[:10]:
            self.assertEqual(
                pd.Timestamp(t.entry_time) - pd.Timestamp(t.signal_time),
                pd.Timedelta(minutes=1),
            )
            expected = times.loc[pd.Timestamp(t.entry_time), "open"]
            factor = 1.0005 if t.side == "BUY" else 0.9995
            self.assertAlmostEqual(t.entry_price, expected * factor, places=9)

    def test_no_overlapping_positions(self):
        for prev, nxt in zip(self.trades, self.trades[1:]):
            self.assertGreater(
                pd.Timestamp(nxt.entry_time), pd.Timestamp(prev.exit_time)
            )

    def test_no_lookahead(self):
        """Cambiar el futuro no puede alterar señales pasadas."""
        cut = len(self.df) // 2
        cut_time = self.df["time"].iloc[cut]
        altered = self.df.copy()
        altered.loc[cut:, ["open", "high", "low", "close"]] *= 1.5
        trades_alt = backtest_symbol("SYN", altered, _params())
        before = [
            t.signal_time for t in self.trades if pd.Timestamp(t.exit_time) < cut_time
        ]
        before_alt = [
            t.signal_time for t in trades_alt if pd.Timestamp(t.exit_time) < cut_time
        ]
        self.assertTrue(before)
        self.assertEqual(before, before_alt)

    def test_costs_are_subtracted(self):
        for t in self.trades:
            self.assertAlmostEqual(t.net_r, t.gross_r - t.cost_r)
            self.assertGreater(t.cost_r, 0.0)


class SummaryTest(unittest.TestCase):
    def _trade(self, net):
        return TTFTrade(
            "X",
            "BUY",
            "t",
            "t",
            f"2026-01-01T00:{len(str(net)):02d}",
            1,
            1,
            1,
            1,
            1,
            "TP" if net > 0 else "SL",
            0.5,
            net + 0.1,
            0.1,
            net,
            1,
            0,
            0,
        )

    def test_metrics(self):
        s = summarize([self._trade(2.0), self._trade(-1.0), self._trade(-1.0)])
        self.assertEqual(s["trades"], 3)
        self.assertAlmostEqual(s["profit_factor"], 1.0)
        self.assertAlmostEqual(s["expectancy_r"], 0.0)
        self.assertEqual(s["verdict"], "MUESTRA_INSUFICIENTE")

    def test_empty(self):
        self.assertEqual(summarize([])["trades"], 0)


if __name__ == "__main__":
    unittest.main()
