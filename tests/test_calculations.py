import math
import unittest

import numpy as np

from quant_mcp import calculations as quant
from quant_mcp import market_data


class BlackScholesTests(unittest.TestCase):
    def test_textbook_atm_prices(self):
        # S=K=100, T=1, r=5%, sigma=20%: call 10.4506, put 5.5735 (Hull's reference values)
        c = quant.black_scholes(100, 100, 1, 0.05, 0.20, "call")
        p = quant.black_scholes(100, 100, 1, 0.05, 0.20, "put")
        self.assertAlmostEqual(c["price"], 10.4506, places=4)
        self.assertAlmostEqual(p["price"], 5.5735, places=4)
        self.assertAlmostEqual(c["delta"], 0.6368, places=4)

    def test_put_call_parity(self):
        S, K, T, r, q, sig = 105.0, 100.0, 0.75, 0.03, 0.01, 0.25
        c = quant.black_scholes(S, K, T, r, sig, "call", q)["price"]
        p = quant.black_scholes(S, K, T, r, sig, "put", q)["price"]
        self.assertAlmostEqual(c - p, S * math.exp(-q * T) - K * math.exp(-r * T), places=9)

    def test_implied_vol_round_trip(self):
        price = quant.black_scholes(250, 260, 0.5, 0.04, 0.31, "put", 0.02)["price"]
        iv = quant.implied_volatility(price, 250, 260, 0.5, 0.04, "put", 0.02)
        self.assertAlmostEqual(iv, 0.31, places=6)

    def test_implied_vol_rejects_arbitrage_price(self):
        with self.assertRaises(ValueError):
            quant.implied_volatility(200.0, 100, 100, 1, 0.05, "call")

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            quant.black_scholes(100, 100, 0, 0.05, 0.2)
        with self.assertRaises(ValueError):
            quant.black_scholes(100, 100, 1, 0.05, 0.2, "straddle")


class AmericanOptionTests(unittest.TestCase):
    def test_non_dividend_call_equals_european(self):
        am = quant.american_binomial(100, 100, 1, 0.05, 0.2, "call", 0.0, steps=1000)["price"]
        eu = quant.black_scholes(100, 100, 1, 0.05, 0.2, "call")["price"]
        self.assertAlmostEqual(am, eu, delta=0.01)

    def test_american_put_has_early_exercise_premium(self):
        out = quant.american_binomial(100, 100, 1, 0.05, 0.2, "put", 0.0, steps=1000)
        self.assertGreater(out["early_exercise_premium"], 0.1)
        self.assertGreaterEqual(out["price"], out["intrinsic_value"])

    def test_matches_independent_naive_tree(self):
        # Reference: plain nested-loop CRR tree, written separately from quant.py.
        def naive(S, K, T, r, sig, q, n):
            dt = T / n
            u = math.exp(sig * math.sqrt(dt))
            d = 1 / u
            p = (math.exp((r - q) * dt) - d) / (u - d)
            disc = math.exp(-r * dt)

            def f(s):
                return max(K - s, 0.0)

            V = [f(S * u**k * d ** (n - k)) for k in range(n + 1)]
            for i in range(n - 1, -1, -1):
                V = [
                    max(disc * (p * V[k + 1] + (1 - p) * V[k]), f(S * u**k * d ** (i - k)))
                    for k in range(i + 1)
                ]
            return V[0]

        for args in [(50, 50, 5 / 12, 0.10, 0.40, 0.0), (100, 110, 0.5, 0.03, 0.3, 0.02)]:
            ref = naive(*args, 400)
            got = quant.american_binomial(*args[:5], "put", args[5], steps=400)["price"]
            self.assertAlmostEqual(got, ref, places=9)

    def test_converges_as_steps_grow(self):
        a = quant.american_binomial(50, 50, 5 / 12, 0.10, 0.40, "put", 0.0, steps=500)["price"]
        b = quant.american_binomial(50, 50, 5 / 12, 0.10, 0.40, "put", 0.0, steps=2000)["price"]
        self.assertAlmostEqual(a, b, delta=0.01)

    def test_high_dividend_call_is_exercised_early(self):
        out = quant.american_binomial(100, 90, 1, 0.05, 0.25, "call", 0.12, steps=500)
        self.assertGreater(out["early_exercise_premium"], 0.05)

    def test_signs_of_greeks(self):
        put = quant.american_binomial(100, 100, 1, 0.05, 0.2, "put", steps=300)
        call = quant.american_binomial(100, 100, 1, 0.05, 0.2, "call", steps=300)
        self.assertLess(put["delta"], 0)
        self.assertGreater(call["delta"], 0)
        self.assertGreater(call["gamma"], 0)
        self.assertGreater(call["vega_per_vol_point"], 0)

    def test_steps_bounds(self):
        with self.assertRaises(ValueError):
            quant.american_binomial(100, 100, 1, 0.05, 0.2, "put", steps=3)


class MarketDataTests(unittest.TestCase):
    def _install_fake_yfinance(self, frame):
        import sys
        import types

        fake = types.ModuleType("yfinance")

        class _Ticker:
            def __init__(self, sym):
                self.sym = sym

            def history(self, **kwargs):
                self.kwargs = kwargs
                return frame

        fake.Ticker = _Ticker
        sys.modules["yfinance"] = fake

    def tearDown(self):
        import sys

        sys.modules.pop("yfinance", None)

    def test_parses_closes_and_dates(self):
        import pandas as pd

        idx = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])
        frame = pd.DataFrame({"Close": [100.0, float("nan"), 102.5]}, index=idx)
        self._install_fake_yfinance(frame)
        out = market_data.price_history("aapl", "5d")
        self.assertEqual(out["ticker"], "AAPL")
        self.assertEqual(out["closes"], [100.0, 102.5])
        self.assertEqual(out["dates"], ["2026-01-02", "2026-01-06"])

    def test_empty_frame_raises(self):
        import pandas as pd

        self._install_fake_yfinance(pd.DataFrame())
        with self.assertRaises(ValueError):
            market_data.price_history("AAPL")

    def _fake_av_response(self, body):
        import json
        from unittest import mock

        raw = json.dumps(body).encode("utf-8")
        cm = mock.MagicMock()
        cm.__enter__.return_value.read.return_value = raw
        cm.__exit__.return_value = False
        return mock.patch("urllib.request.urlopen", return_value=cm)

    def test_alphavantage_parses_adjusted_closes(self):
        import os
        from unittest import mock

        body = {
            "Time Series (Daily)": {
                "2026-01-06": {"4. close": "102.0", "5. adjusted close": "101.5"},
                "2026-01-05": {"4. close": "101.0", "5. adjusted close": "100.5"},
            }
        }
        with (
            mock.patch.dict(
                os.environ,
                {"ALPHAVANTAGE_API_KEY": "TESTKEY123", "QUANT_MCP_ENABLED_PROVIDERS": "yahoo,alphavantage"},
            ),
            self._fake_av_response(body) as up,
        ):
            out = market_data.price_history("ibm", "max", provider="alphavantage")
        self.assertEqual(out["dates"], ["2026-01-05", "2026-01-06"])
        self.assertEqual(out["closes"], [100.5, 101.5])
        self.assertIn("function=TIME_SERIES_DAILY_ADJUSTED", up.call_args[0][0])
        self.assertNotIn("TESTKEY123", str(out))

    def test_alphavantage_needs_key(self):
        import os
        from unittest import mock

        with (
            mock.patch.dict(os.environ, {"QUANT_MCP_ENABLED_PROVIDERS": "yahoo,alphavantage"}, clear=True),
            self.assertRaises(RuntimeError) as ctx,
        ):
            market_data.price_history("IBM", provider="alphavantage")
        self.assertIn("ALPHAVANTAGE_API_KEY", str(ctx.exception))

    def test_alphavantage_surfaces_rate_limit_and_errors(self):
        import os
        from unittest import mock

        with (
            mock.patch.dict(
                os.environ, {"ALPHAVANTAGE_API_KEY": "K", "QUANT_MCP_ENABLED_PROVIDERS": "yahoo,alphavantage"}
            ),
            self._fake_av_response({"Note": "limit reached"}),
            self.assertRaises(RuntimeError),
        ):
            market_data.price_history("IBM", provider="alphavantage")
        with (
            mock.patch.dict(
                os.environ, {"ALPHAVANTAGE_API_KEY": "K", "QUANT_MCP_ENABLED_PROVIDERS": "yahoo,alphavantage"}
            ),
            self._fake_av_response({"Error Message": "bad symbol"}),
            self.assertRaises(ValueError),
        ):
            market_data.price_history("IBM", provider="alphavantage")

    def test_alphavantage_rejects_intraday(self):
        with self.assertRaises(ValueError):
            market_data.price_history("IBM", interval="1wk", provider="alphavantage")

    def test_unknown_provider(self):
        with self.assertRaises(ValueError):
            market_data.price_history("IBM", provider="bloomberg")

    def test_rejects_bad_inputs_before_network(self):
        with self.assertRaises(ValueError):
            market_data.price_history("bad ticker!")
        with self.assertRaises(ValueError):
            market_data.price_history("AAPL", period="45y")
        with self.assertRaises(ValueError):
            market_data.price_history("AAPL", interval="7s")


class BondTests(unittest.TestCase):
    def test_par_bond_prices_at_par(self):
        r = quant.bond_analytics(100, 0.05, 10, 2, ytm=0.05)
        self.assertAlmostEqual(r["price"], 100.0, places=8)

    def test_yield_round_trip(self):
        price = quant.bond_price_from_yield(1000, 0.06, 7, 0.0725, 2)
        ytm = quant.yield_from_bond_price(1000, 0.06, 7, price, 2)
        self.assertAlmostEqual(ytm, 0.0725, places=8)

    def test_duration_below_maturity_and_dv01_sign(self):
        r = quant.bond_analytics(100, 0.05, 10, 2, ytm=0.05)
        self.assertGreater(r["macaulay_duration_years"], 0)
        self.assertLess(r["macaulay_duration_years"], 10)
        # Par 10y semiannual bond at 5%: closed form Macaulay = ((1+y)/y)(1-(1+y)^-n)/m
        # with y=0.025, n=20 gives 7.9895y; modified = Macaulay/(1+y/m) = 7.7946
        self.assertAlmostEqual(r["modified_duration"], 7.7946, places=3)

    def test_requires_exactly_one_of_ytm_or_price(self):
        with self.assertRaises(ValueError):
            quant.bond_analytics(100, 0.05, 10)
        with self.assertRaises(ValueError):
            quant.bond_analytics(100, 0.05, 10, ytm=0.05, price=100)


class NPVIRRTests(unittest.TestCase):
    def test_irr_of_simple_project(self):
        r = quant.npv_irr([-100, 60, 60], rate=0.0)
        self.assertAlmostEqual(r["irr"], 0.1307, places=4)
        self.assertAlmostEqual(r["npv"], 20.0, places=9)

    def test_irr_undefined_without_sign_change(self):
        r = quant.npv_irr([100, 50])
        self.assertIsNone(r["irr"])


class RiskTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(0)
        self.r = rng.normal(0.0005, 0.01, 2000).tolist()

    def test_parametric_var_matches_normal_formula(self):
        r = np.array(self.r)
        expected = -(r.mean() - 1.6448536 * r.std(ddof=1))
        got = quant.value_at_risk(self.r, 0.95, 1, "parametric")["var"]
        self.assertAlmostEqual(got, expected, places=5)

    def test_expected_shortfall_exceeds_var(self):
        for m in ("historical", "parametric"):
            v = quant.value_at_risk(self.r, 0.99, 1, m)
            self.assertGreater(v["expected_shortfall"], v["var"])

    def test_sqrt_time_scaling(self):
        one = quant.value_at_risk(self.r, 0.95, 1, "historical")["var"]
        ten = quant.value_at_risk(self.r, 0.95, 10, "historical")["var"]
        self.assertAlmostEqual(ten / one, math.sqrt(10), places=9)

    def test_max_drawdown_known_path(self):
        # equity: 1 -> 1.2 -> 0.6 -> 0.9 ; peak 1.2, trough 0.6 => -50%
        r = quant.max_drawdown([0.2, -0.5, 0.5])
        self.assertAlmostEqual(r["max_drawdown"], -0.5, places=12)
        self.assertEqual(r["peak_index"], 1)
        self.assertEqual(r["trough_index"], 2)

    def test_performance_sanity(self):
        m = quant.performance_metrics(self.r, 252, 0.0)
        self.assertAlmostEqual(m["annualized_volatility"], 0.01 * math.sqrt(252), delta=0.01)
        self.assertGreater(m["sharpe_ratio"], 0)
        self.assertLess(m["max_drawdown"], 0)

    def test_returns_from_prices(self):
        got = quant.returns_from_prices([100, 110, 99])
        self.assertAlmostEqual(got[0], 0.10, places=12)
        self.assertAlmostEqual(got[1], -0.10, places=12)

    def test_portfolio_risk_contributions_sum_to_100(self):
        rng = np.random.default_rng(1)
        data = {"A": rng.normal(0, 0.01, 500).tolist(), "B": rng.normal(0, 0.02, 500).tolist()}
        out = quant.portfolio_risk(data, {"A": 0.6, "B": 0.4})
        self.assertAlmostEqual(sum(out["risk_contribution_pct"].values()), 100.0, places=8)

    def test_portfolio_weights_must_match(self):
        with self.assertRaises(ValueError):
            quant.portfolio_risk({"A": [0.1, 0.2]}, {"B": 1.0})

    def test_capm_recovers_beta(self):
        rng = np.random.default_rng(2)
        m = rng.normal(0, 0.01, 1000)
        a = 1.3 * m + rng.normal(0, 0.001, 1000)
        out = quant.capm_regression(a.tolist(), m.tolist())
        self.assertAlmostEqual(out["beta"], 1.3, delta=0.02)


class SizingTests(unittest.TestCase):
    def test_kelly_binary(self):
        out = quant.kelly_fraction(0.6, 1.0)
        self.assertAlmostEqual(out["full_kelly"], 0.2, places=12)
        self.assertAlmostEqual(out["half_kelly"], 0.1, places=12)
        self.assertTrue(out["bet"])

    def test_kelly_no_edge(self):
        self.assertFalse(quant.kelly_fraction(0.4, 1.0)["bet"])

    def test_position_size(self):
        out = quant.position_size(100_000, 0.01, 50.0, 48.0)
        self.assertEqual(out["shares"], 500)  # $1000 risk / $2 per share
        self.assertEqual(out["direction"], "long")


class MonteCarloTests(unittest.TestCase):
    def test_terminal_mean_is_forward_price(self):
        out = quant.monte_carlo_gbm(100, 0.05, 0.2, 1.0, paths=200_000, seed=7)
        self.assertAlmostEqual(out["mean_terminal"], 100 * math.exp(0.05), delta=0.3)

    def test_mc_call_close_to_black_scholes(self):
        mc = quant.monte_carlo_gbm(100, 0.05, 0.2, 1.0, paths=400_000, seed=3, strike=100)
        bs = quant.black_scholes(100, 100, 1, 0.05, 0.2, "call")["price"]
        self.assertAlmostEqual(mc["option"]["price"], bs, delta=4 * mc["option"]["std_error"] + 0.01)


if __name__ == "__main__":
    unittest.main()
