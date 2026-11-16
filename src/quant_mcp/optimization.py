"""Portfolio construction: mean-variance optimisation, risk parity and HRP.

All functions take per-asset periodic return series and return weights that
sum to one. Covariance and expected returns are annualised using
``periods_per_year``. ``long_only=True`` restricts weights to [0, max_weight].
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.optimize import minimize
from scipy.spatial.distance import squareform

from quant_mcp.validation import ValidationError, aligned_matrix, check_fraction, check_positive_int


def _inputs(
    returns: Mapping[str, Sequence[float]],
    periods_per_year: int,
    max_weight: float,
    long_only: bool,
):
    names, mat = aligned_matrix(returns, min_length=3)
    check_positive_int(periods_per_year, "periods_per_year", maximum=366)
    check_fraction(max_weight, "max_weight", allow_zero=False)
    if long_only and max_weight * len(names) < 1.0 - 1e-12:
        raise ValidationError(
            f"max_weight={max_weight} is infeasible for {len(names)} assets (need max_weight >= 1/N)."
        )
    mu = mat.mean(axis=1) * periods_per_year
    cov = np.cov(mat, ddof=1) * periods_per_year
    lower = 0.0 if long_only else -1.0
    upper = max_weight if long_only else 1.0
    return names, mat, mu, cov, lower, upper


def _solve(objective, x0, bounds, extra_constraints=()):
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}, *extra_constraints]
    res = minimize(
        objective,
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 500, "ftol": 1e-12},
    )
    if not res.success:
        raise ValidationError(f"Optimiser did not converge: {res.message}")
    return res.x


def _portfolio_stats(w: np.ndarray, mu: np.ndarray, cov: np.ndarray, rf: float) -> dict:
    ret = float(w @ mu)
    vol = math.sqrt(max(float(w @ cov @ w), 0.0))
    return {
        "expected_return_annual": ret,
        "volatility_annual": vol,
        "sharpe_ratio": (ret - rf) / vol if vol > 0 else None,
    }


def _pack(names: list[str], w: np.ndarray, mu, cov, rf: float, method: str) -> dict:
    if np.all(w >= -1e-9):
        w = np.clip(w, 0.0, None)  # remove solver noise below zero for long-only results
    w = w / w.sum()
    out = {"method": method, "weights": dict(zip(names, [float(x) for x in w], strict=False))}
    out.update(_portfolio_stats(w, mu, cov, rf))
    return out


def min_variance(
    returns: Mapping[str, Sequence[float]],
    periods_per_year: int = 252,
    long_only: bool = True,
    max_weight: float = 1.0,
    risk_free_annual: float = 0.0,
) -> dict:
    """Global minimum-variance portfolio."""
    names, _, mu, cov, lo, hi = _inputs(returns, periods_per_year, max_weight, long_only)
    n = len(names)
    x0 = np.full(n, 1.0 / n)
    w = _solve(lambda w: float(w @ cov @ w), x0, [(lo, hi)] * n)
    return _pack(names, w, mu, cov, risk_free_annual, "min_variance")


def max_sharpe(
    returns: Mapping[str, Sequence[float]],
    periods_per_year: int = 252,
    risk_free_annual: float = 0.0,
    long_only: bool = True,
    max_weight: float = 1.0,
) -> dict:
    """Tangency (maximum Sharpe ratio) portfolio."""
    names, _, mu, cov, lo, hi = _inputs(returns, periods_per_year, max_weight, long_only)
    n = len(names)

    def neg_sharpe(w: np.ndarray) -> float:
        vol = math.sqrt(max(float(w @ cov @ w), 1e-16))
        return -(float(w @ mu) - risk_free_annual) / vol

    x0 = np.full(n, 1.0 / n)
    w = _solve(neg_sharpe, x0, [(lo, hi)] * n)
    return _pack(names, w, mu, cov, risk_free_annual, "max_sharpe")


def risk_parity(
    returns: Mapping[str, Sequence[float]],
    periods_per_year: int = 252,
    risk_free_annual: float = 0.0,
) -> dict:
    """Equal risk contribution portfolio (long-only, fully invested)."""
    names, _, mu, cov, _lo, hi = _inputs(returns, periods_per_year, 1.0, True)
    n = len(names)
    target = 1.0 / n

    def objective(w: np.ndarray) -> float:
        port_var = float(w @ cov @ w)
        if port_var <= 0:
            return 1e6
        rc = w * (cov @ w) / port_var
        return float(np.sum((rc - target) ** 2))

    x0 = np.full(n, 1.0 / n)
    w = _solve(objective, x0, [(1e-6, hi)] * n)
    out = _pack(names, w, mu, cov, risk_free_annual, "risk_parity")
    port_var = float(w @ cov @ w)
    out["risk_contribution_pct"] = dict(
        zip(names, [float(x) * 100 for x in (w * (cov @ w) / port_var)], strict=False)
    )
    return out


def efficient_frontier(
    returns: Mapping[str, Sequence[float]],
    points: int = 20,
    periods_per_year: int = 252,
    risk_free_annual: float = 0.0,
    long_only: bool = True,
    max_weight: float = 1.0,
) -> dict:
    """Mean-variance efficient frontier between min-variance and max-return portfolios."""
    if not 2 <= points <= 200:
        raise ValidationError("points must be between 2 and 200.")
    names, _, mu, cov, lo, hi = _inputs(returns, periods_per_year, max_weight, long_only)
    n = len(names)
    x0 = np.full(n, 1.0 / n)
    bounds = [(lo, hi)] * n

    mv = _solve(lambda w: float(w @ cov @ w), x0, bounds)
    r_min = float(mv @ mu)
    r_max = float(mu.max())
    targets = np.linspace(r_min, r_max, points)

    frontier = []
    for t in targets:
        cons = [{"type": "eq", "fun": (lambda w, t=t: float(w @ mu) - t)}]
        try:
            w = _solve(lambda w: float(w @ cov @ w), mv, bounds, cons)
        except ValidationError:
            continue
        s = _portfolio_stats(w, mu, cov, risk_free_annual)
        frontier.append(
            {
                "target_return": float(t),
                "volatility_annual": s["volatility_annual"],
                "sharpe_ratio": s["sharpe_ratio"],
                "weights": dict(zip(names, [float(x) for x in w], strict=False)),
            }
        )
    if not frontier:
        raise ValidationError("No feasible frontier points found; check the data or constraints.")
    return {"assets": names, "points": frontier}


def _quasi_diagonal_order(corr: np.ndarray, cov: np.ndarray) -> list[int]:
    dist = np.sqrt(np.clip((1.0 - corr) / 2.0, 0.0, 1.0))
    np.fill_diagonal(dist, 0.0)
    link = linkage(squareform(dist, checks=False), method="single")
    return [int(i) for i in leaves_list(link)]


def _cluster_var(cov: np.ndarray, items: list[int]) -> float:
    sub = cov[np.ix_(items, items)]
    inv_diag = 1.0 / np.diag(sub)
    w = inv_diag / inv_diag.sum()
    return float(w @ sub @ w)


def hrp(
    returns: Mapping[str, Sequence[float]],
    periods_per_year: int = 252,
    risk_free_annual: float = 0.0,
) -> dict:
    """Hierarchical Risk Parity (Lopez de Prado, 2016).

    Clusters assets by correlation, orders them so similar assets sit together,
    then splits capital between clusters inversely to their variance. Needs no
    matrix inversion, so it is stable when the covariance is ill-conditioned.
    """
    names, mat = aligned_matrix(returns, min_length=3)
    check_positive_int(periods_per_year, "periods_per_year", maximum=366)
    n = len(names)
    cov = np.atleast_2d(np.cov(mat, ddof=1))
    corr = np.atleast_2d(np.corrcoef(mat))
    mu = mat.mean(axis=1) * periods_per_year
    cov_a = cov * periods_per_year

    if n == 1:
        w = np.array([1.0])
    else:
        order = _quasi_diagonal_order(corr, cov)
        w_all = np.ones(n)
        clusters = [order]
        while clusters:
            next_clusters = []
            for c in clusters:
                if len(c) <= 1:
                    continue
                half = len(c) // 2
                left, right = c[:half], c[half:]
                v_l = _cluster_var(cov, left)
                v_r = _cluster_var(cov, right)
                alpha = 1.0 - v_l / (v_l + v_r)
                w_all[left] *= alpha
                w_all[right] *= 1.0 - alpha
                next_clusters += [left, right]
            clusters = next_clusters
        w = w_all / w_all.sum()  # w_all is indexed by original asset position

    weights = {name: float(x) for name, x in zip(names, w, strict=False)}
    port_ret = float(w @ mu)
    port_vol = math.sqrt(max(float(w @ cov_a @ w), 0.0))
    return {
        "method": "hrp",
        "weights": weights,
        "expected_return_annual": port_ret,
        "volatility_annual": port_vol,
        "sharpe_ratio": (port_ret - risk_free_annual) / port_vol if port_vol > 0 else None,
    }
