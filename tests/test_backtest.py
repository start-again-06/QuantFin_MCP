import math

import numpy as np
import pytest

from quant_mcp import backtest as bt
from quant_mcp.validation import ValidationError


def test_buy_and_hold_no_costs_matches_compounding(three_asset_returns):
    w = {"AAA": 0.5, "BBB": 0.3, "CCC": 0.2}
    out = bt.backtest_portfolio(three_asset_returns, w, rebalance_every=None, cost_bps=0.0)
    # Recompute by hand: drifting weights, no rebalance, no costs.
    names = list(w)
    mat = np.array([three_asset_returns[n] for n in names])
    holdings = np.array([w[n] for n in names]) * 1.0
    expected = []
    for t in range(mat.shape[1]):
        gross = float(np.sum(holdings * (1 + mat[:, t])))
        expected.append(gross - 1)
        holdings = holdings * (1 + mat[:, t]) / gross
    assert np.allclose(out["net_returns"], expected, atol=1e-12)


def test_costs_reduce_return(three_asset_returns):
    w = {"AAA": 1 / 3, "BBB": 1 / 3, "CCC": 1 / 3}
    free = bt.backtest_portfolio(three_asset_returns, w, rebalance_every=5, cost_bps=0.0)
    costly = bt.backtest_portfolio(three_asset_returns, w, rebalance_every=5, cost_bps=50.0)
    assert sum(costly["net_returns"]) < sum(free["net_returns"])
    assert costly["total_costs_return"] > 0


def test_turnover_is_zero_for_static_single_asset():
    out = bt.backtest_portfolio({"A": [0.01, 0.02, -0.01, 0.0]}, {"A": 1.0}, rebalance_every=2, cost_bps=0.0)
    assert out["total_turnover"] == pytest.approx(1.0)  # only the initial purchase


def test_weights_must_match_assets(three_asset_returns):
    with pytest.raises(ValidationError):
        bt.backtest_portfolio(three_asset_returns, {"AAA": 1.0})


def test_cost_bounds_enforced(three_asset_returns):
    with pytest.raises(ValidationError):
        bt.backtest_portfolio(three_asset_returns, {"AAA": 1 / 3, "BBB": 1 / 3, "CCC": 1 / 3}, cost_bps=-1)


def _prices(n=400, seed=5):
    rng = np.random.default_rng(seed)
    return (100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, n)))).tolist()


def test_crossover_has_no_lookahead():
    # Property: changing prices after day k must not change any strategy return that
    # depends only on information up to day k. A look-ahead bug would break this.
    base = _prices(300, seed=9)
    changed = base[:200] + [p * 1.5 for p in base[200:]]
    a = bt.moving_average_crossover(base, fast=5, slow=20, cost_bps=0.0)["net_returns"]
    b = bt.moving_average_crossover(changed, fast=5, slow=20, cost_bps=0.0)["net_returns"]
    # Return index k uses prices up to k+1 and signals up to k-1, so indices < 198 are unaffected.
    assert a[:198] == pytest.approx(b[:198], abs=0.0)
    assert a[198:] != b[198:]


def test_crossover_metrics_and_fields():
    out = bt.moving_average_crossover(_prices(), fast=10, slow=50, cost_bps=5.0)
    assert 0 <= out["time_in_market"] <= 1
    assert math.isfinite(out["strategy_metrics"]["cagr"])
    assert "buy_and_hold_metrics" in out


def test_crossover_parameter_validation():
    with pytest.raises(ValidationError):
        bt.moving_average_crossover(_prices(), fast=50, slow=10)
    with pytest.raises(ValidationError):
        bt.moving_average_crossover([1.0, 2.0, -3.0] * 5)
