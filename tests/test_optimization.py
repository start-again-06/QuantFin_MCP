import numpy as np
import pytest

from quant_mcp import optimization as opt
from quant_mcp.validation import ValidationError


def _sums_to_one(weights):
    return pytest.approx(1.0, abs=1e-8) == sum(weights.values())


def test_min_variance_is_fully_invested_and_long_only(three_asset_returns):
    out = opt.min_variance(three_asset_returns)
    assert _sums_to_one(out["weights"])
    assert all(w >= -1e-9 for w in out["weights"].values())


def test_min_variance_beats_equal_weight_on_variance(three_asset_returns):
    mv = opt.min_variance(three_asset_returns)
    names = list(three_asset_returns)
    mat = np.array([three_asset_returns[n] for n in names])
    cov = np.cov(mat, ddof=1) * 252
    eq = np.full(3, 1 / 3)
    w = np.array([mv["weights"][n] for n in names])
    assert w @ cov @ w <= eq @ cov @ eq + 1e-10


def test_max_sharpe_is_at_least_as_good_as_min_variance(three_asset_returns):
    ms = opt.max_sharpe(three_asset_returns, risk_free_annual=0.02)
    mv = opt.min_variance(three_asset_returns, risk_free_annual=0.02)
    assert ms["sharpe_ratio"] >= mv["sharpe_ratio"] - 1e-6


def test_max_weight_constraint_is_respected(three_asset_returns):
    out = opt.min_variance(three_asset_returns, max_weight=0.4)
    assert max(out["weights"].values()) <= 0.4 + 1e-6


def test_infeasible_max_weight_rejected(three_asset_returns):
    with pytest.raises(ValidationError):
        opt.min_variance(three_asset_returns, max_weight=0.2)  # 3 * 0.2 < 1


def test_risk_parity_equalises_risk_contributions(three_asset_returns):
    out = opt.risk_parity(three_asset_returns)
    contrib = np.array(list(out["risk_contribution_pct"].values()))
    assert np.allclose(contrib, 100 / 3, atol=0.5)


def test_efficient_frontier_is_monotone_in_return(three_asset_returns):
    out = opt.efficient_frontier(three_asset_returns, points=8)
    rets = [p["target_return"] for p in out["points"]]
    assert rets == sorted(rets)
    assert len(out["points"]) >= 2
    for p in out["points"]:
        assert _sums_to_one(p["weights"])


def test_hrp_weights_valid_and_sum_to_one(three_asset_returns):
    out = opt.hrp(three_asset_returns)
    assert _sums_to_one(out["weights"])
    assert all(w > 0 for w in out["weights"].values())


def test_hrp_single_asset():
    out = opt.hrp({"ONLY": [0.01, -0.005, 0.002, 0.003]})
    assert out["weights"] == {"ONLY": 1.0}


def test_hrp_gives_less_weight_to_the_riskiest_asset(three_asset_returns):
    out = opt.hrp(three_asset_returns)
    assert out["weights"]["CCC"] < out["weights"]["AAA"]  # CCC has the highest variance
