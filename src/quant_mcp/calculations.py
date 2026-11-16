"""Pure quantitative-finance routines used by the MCP server.

Everything here is deterministic numerics with no I/O, so it can be unit
tested directly. Rates are annual decimals (0.05 == 5%) unless a parameter
says otherwise. Returns are simple periodic returns (0.01 == 1%).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np
from scipy import stats
from scipy.optimize import brentq

# ---------------------------------------------------------------------------
# Options: Black-Scholes-Merton
# ---------------------------------------------------------------------------


def _d1_d2(S: float, K: float, T: float, r: float, sigma: float, q: float):
    vol_t = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vol_t
    return d1, d1 - vol_t


def _validate_option_inputs(S, K, T, sigma, option_type):
    if S <= 0 or K <= 0:
        raise ValueError("Spot and strike must be positive.")
    if T <= 0:
        raise ValueError("Time to expiry must be positive (in years).")
    if sigma <= 0:
        raise ValueError("Volatility must be positive.")
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be 'call' or 'put'.")


def black_scholes(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = "call",
    q: float = 0.0,
) -> dict:
    """European option price and Greeks under Black-Scholes-Merton.

    Units: theta is per calendar day, vega is per 1 vol point (0.01),
    rho is per 1% rate move. Gamma is per unit of spot.
    """
    option_type = option_type.lower()
    _validate_option_inputs(S, K, T, sigma, option_type)

    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    disc_r = math.exp(-r * T)
    disc_q = math.exp(-q * T)
    pdf_d1 = stats.norm.pdf(d1)
    sqrtT = math.sqrt(T)

    if option_type == "call":
        price = S * disc_q * stats.norm.cdf(d1) - K * disc_r * stats.norm.cdf(d2)
        delta = disc_q * stats.norm.cdf(d1)
        theta_yr = (
            -S * disc_q * pdf_d1 * sigma / (2 * sqrtT)
            - r * K * disc_r * stats.norm.cdf(d2)
            + q * S * disc_q * stats.norm.cdf(d1)
        )
        rho = K * T * disc_r * stats.norm.cdf(d2)
    else:
        price = K * disc_r * stats.norm.cdf(-d2) - S * disc_q * stats.norm.cdf(-d1)
        delta = disc_q * (stats.norm.cdf(d1) - 1.0)
        theta_yr = (
            -S * disc_q * pdf_d1 * sigma / (2 * sqrtT)
            + r * K * disc_r * stats.norm.cdf(-d2)
            - q * S * disc_q * stats.norm.cdf(-d1)
        )
        rho = -K * T * disc_r * stats.norm.cdf(-d2)

    gamma = disc_q * pdf_d1 / (S * sigma * sqrtT)
    vega = S * disc_q * pdf_d1 * sqrtT

    intrinsic = max(S - K, 0.0) if option_type == "call" else max(K - S, 0.0)
    return {
        "price": price,
        "intrinsic_value": intrinsic,
        "time_value": price - intrinsic,
        "d1": d1,
        "d2": d2,
        "delta": delta,
        "gamma": gamma,
        "vega_per_vol_point": vega / 100.0,
        "theta_per_day": theta_yr / 365.0,
        "rho_per_rate_pct": rho / 100.0,
    }


def implied_volatility(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    option_type: str = "call",
    q: float = 0.0,
) -> float:
    """Solve for the Black-Scholes volatility that reproduces market_price."""
    option_type = option_type.lower()
    _validate_option_inputs(S, K, T, 1.0, option_type)
    disc_r = math.exp(-r * T)
    disc_q = math.exp(-q * T)
    if option_type == "call":
        lower = max(S * disc_q - K * disc_r, 0.0)
        upper = S * disc_q
    else:
        lower = max(K * disc_r - S * disc_q, 0.0)
        upper = K * disc_r
    if not (lower < market_price < upper):
        raise ValueError(
            f"Price {market_price} is outside no-arbitrage bounds "
            f"({lower:.6f}, {upper:.6f}); no implied volatility exists."
        )

    def objective(sig: float) -> float:
        return black_scholes(S, K, T, r, sig, option_type, q)["price"] - market_price

    return brentq(objective, 1e-6, 10.0, xtol=1e-10, maxiter=500)


def american_binomial(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = "put",
    q: float = 0.0,
    steps: int = 500,
) -> dict:
    """American option via a Cox-Ross-Rubinstein binomial tree.

    Early exercise is checked at every node. Dividends are modelled as a
    continuous yield q. Greeks come from the first tree nodes and small bumps.
    The early-exercise premium is the American price minus the European
    Black-Scholes price with the same inputs.
    """
    option_type = option_type.lower()
    _validate_option_inputs(S, K, T, sigma, option_type)
    if not 10 <= steps <= 5000:
        raise ValueError("steps must be between 10 and 5000.")

    price, (Su, Vu, Sd, Vd) = _crr_tree(S, K, T, r, sigma, option_type, q, steps)

    # Delta from the first step of the tree (up and down nodes).
    delta = (Vu - Vd) / (Su - Sd)

    # Gamma, vega and theta by central/forward differences on the same tree.
    h_s = S * 0.01
    p_up, _ = _crr_tree(S + h_s, K, T, r, sigma, option_type, q, steps)
    p_dn, _ = _crr_tree(S - h_s, K, T, r, sigma, option_type, q, steps)
    gamma = (p_up - 2 * price + p_dn) / (h_s * h_s)

    h_v = 0.0001
    v_up, _ = _crr_tree(S, K, T, r, sigma + h_v, option_type, q, steps)
    v_dn, _ = _crr_tree(S, K, T, r, sigma - h_v, option_type, q, steps)
    vega = (v_up - v_dn) / (2 * h_v) / 100.0

    theta = None
    h_t = 1.0 / 365.0
    if 2 * h_t < T:
        t_short, _ = _crr_tree(S, K, T - h_t, r, sigma, option_type, q, steps)
        theta = (t_short - price) / h_t / 365.0  # per calendar day, sign = change as time passes

    european = black_scholes(S, K, T, r, sigma, option_type, q)["price"]
    intrinsic = max(S - K, 0.0) if option_type == "call" else max(K - S, 0.0)
    return {
        "price": price,
        "european_price_bs": european,
        "early_exercise_premium": price - european,
        "intrinsic_value": intrinsic,
        "delta": float(delta),
        "gamma": float(gamma),
        "vega_per_vol_point": float(vega),
        "theta_per_day": None if theta is None else float(theta),
        "steps": steps,
    }


def _crr_tree(S, K, T, r, sigma, option_type, q, steps):
    """Cox-Ross-Rubinstein backward induction with early exercise.

    Returns (price, step1) where step1 = (S_up, V_up, S_down, V_down) are the
    option values one step ahead, used for delta. Pure function, no recursion.
    """
    dt = T / steps
    u = math.exp(sigma * math.sqrt(dt))
    d = 1.0 / u
    p = (math.exp((r - q) * dt) - d) / (u - d)
    if not 0.0 < p < 1.0:
        raise ValueError("Risk-neutral probability outside (0,1); increase steps.")
    disc = math.exp(-r * dt)
    sign = 1.0 if option_type == "call" else -1.0

    j = np.arange(steps + 1)
    ST = S * (u ** (steps - j)) * (d**j)
    values = np.maximum(sign * (ST - K), 0.0)

    step1 = None
    for i in range(steps - 1, -1, -1):
        jj = np.arange(i + 1)
        Si = S * (u ** (i - jj)) * (d**jj)
        cont = disc * (p * values[:-1] + (1.0 - p) * values[1:])
        values = np.maximum(cont, np.maximum(sign * (Si - K), 0.0))
        if i == 1:
            # Index k at any time = number of down-moves so far: index 0 is the up node.
            step1 = (S * u, float(values[0]), S * d, float(values[1]))
    return float(values[0]), step1


# ---------------------------------------------------------------------------
# Fixed income
# ---------------------------------------------------------------------------


def _bond_cashflows(face, coupon_rate, years, frequency):
    if frequency not in (1, 2, 4, 12):
        raise ValueError("frequency must be 1, 2, 4 or 12 payments per year.")
    n = round(years * frequency)
    if n < 1:
        raise ValueError("Bond must have at least one remaining coupon period.")
    c = face * coupon_rate / frequency
    cfs = np.full(n, c, dtype=float)
    cfs[-1] += face
    return n, cfs


def bond_price_from_yield(face, coupon_rate, years, ytm, frequency=2) -> float:
    n, cfs = _bond_cashflows(face, coupon_rate, years, frequency)
    y = ytm / frequency
    k = np.arange(1, n + 1)
    return float(np.sum(cfs / (1 + y) ** k))


def yield_from_bond_price(face, coupon_rate, years, price, frequency=2) -> float:
    if price <= 0:
        raise ValueError("Price must be positive.")
    return brentq(
        lambda y: bond_price_from_yield(face, coupon_rate, years, y, frequency) - price,
        -0.99,
        5.0,
        xtol=1e-12,
        maxiter=500,
    )


def bond_analytics(face, coupon_rate, years, frequency=2, ytm=None, price=None) -> dict:
    """Price, yield, duration, convexity and DV01 for a plain fixed-coupon bond.

    Supply either ytm (annual, compounded at `frequency`) or a clean-ish
    price (dirty price is assumed; no accrued-interest adjustment).
    """
    if (ytm is None) == (price is None):
        raise ValueError("Provide exactly one of ytm or price.")
    if price is None:
        price = bond_price_from_yield(face, coupon_rate, years, ytm, frequency)
    else:
        ytm = yield_from_bond_price(face, coupon_rate, years, price, frequency)

    n, cfs = _bond_cashflows(face, coupon_rate, years, frequency)
    y = ytm / frequency
    k = np.arange(1, n + 1)
    pv = cfs / (1 + y) ** k
    p = float(pv.sum())

    t_years = k / frequency
    macaulay = float(np.sum(t_years * pv) / p)
    modified = macaulay / (1 + y)
    convexity = float(np.sum(cfs * k * (k + 1) / (1 + y) ** (k + 2)) / p / frequency**2)
    dv01 = modified * p / 10000.0

    return {
        "price": p,
        "ytm": ytm,
        "macaulay_duration_years": macaulay,
        "modified_duration": modified,
        "convexity": convexity,
        "dv01_per_bp": dv01,
        "periods": n,
    }


# ---------------------------------------------------------------------------
# Time value of money
# ---------------------------------------------------------------------------


def npv_irr(cashflows: Sequence[float], rate: float | None = None) -> dict:
    """NPV at `rate` (if given) and IRR of cashflows at t = 0, 1, 2, ..."""
    cf = np.asarray(cashflows, dtype=float)
    if cf.size < 2:
        raise ValueError("Need at least two cashflows.")
    t = np.arange(cf.size)
    out: dict = {}
    if rate is not None:
        out["npv"] = float(np.sum(cf / (1 + rate) ** t))
    has_sign_change = cf.min() < 0 < cf.max()
    if has_sign_change:

        def npv_at(r: float) -> float:
            return float(np.sum(cf / (1 + r) ** t))

        try:
            out["irr"] = brentq(npv_at, -0.9999, 100.0, maxiter=500)
        except ValueError:
            out["irr"] = None
            out["irr_note"] = "No IRR found in search bracket (-99.99% to 10,000%)."
    else:
        out["irr"] = None
        out["irr_note"] = "IRR undefined: cashflows need both a negative and a positive value."
    return out


# ---------------------------------------------------------------------------
# Risk
# ---------------------------------------------------------------------------


def _as_array(x, name="returns") -> np.ndarray:
    a = np.asarray(x, dtype=float)
    if a.ndim != 1 or a.size < 2:
        raise ValueError(f"{name} must be a 1-D list with at least 2 values.")
    if not np.all(np.isfinite(a)):
        raise ValueError(f"{name} contains non-finite values.")
    return a


def value_at_risk(
    returns: Sequence[float],
    confidence: float = 0.95,
    horizon_days: int = 1,
    method: str = "historical",
) -> dict:
    """VaR and expected shortfall as positive loss fractions of portfolio value.

    method: 'historical' (empirical quantile), 'parametric' (normal),
            or 'cornish_fisher' (normal adjusted for skew and kurtosis).
    Multi-day horizons use square-root-of-time scaling.
    """
    if not 0.5 < confidence < 1.0:
        raise ValueError("confidence must be in (0.5, 1).")
    r = _as_array(returns)
    alpha = 1.0 - confidence
    scale = math.sqrt(horizon_days)
    mu, sd = float(r.mean()), float(r.std(ddof=1))

    if method == "historical":
        q = float(np.quantile(r, alpha))
        tail = r[r <= q]
        es = float(-tail.mean()) if tail.size else float(-q)
        var = -q
    elif method == "parametric":
        z = stats.norm.ppf(alpha)
        var = -(mu + z * sd)
        es = -(mu - sd * stats.norm.pdf(z) / alpha)
    elif method == "cornish_fisher":
        z = stats.norm.ppf(alpha)
        s = float(stats.skew(r, bias=False))
        k = float(stats.kurtosis(r, fisher=True, bias=False))
        zc = z + (z * z - 1) * s / 6 + (z**3 - 3 * z) * k / 24 - (2 * z**3 - 5 * z) * s * s / 36
        var = -(mu + zc * sd)
        es = None
    else:
        raise ValueError("method must be 'historical', 'parametric' or 'cornish_fisher'.")

    result = {
        "method": method,
        "confidence": confidence,
        "horizon_days": horizon_days,
        "var": float(var * scale),
        "expected_shortfall": None if es is None else float(es * scale),
        "observations": int(r.size),
    }
    if method == "historical" and r.size < 250:
        result["warning"] = "Fewer than 250 observations: historical VaR tail estimates are noisy."
    return result


def max_drawdown(returns: Sequence[float]) -> dict:
    """Maximum peak-to-trough drawdown of the compounded equity curve."""
    r = _as_array(returns)
    equity = np.cumprod(1.0 + r)
    equity = np.concatenate(([1.0], equity))
    running_peak = np.maximum.accumulate(equity)
    dd = equity / running_peak - 1.0
    trough = int(np.argmin(dd))
    peak = int(np.argmax(equity[: trough + 1]))
    return {
        "max_drawdown": float(dd[trough]),
        "peak_index": peak,
        "trough_index": trough,
        "note": "Indices are positions on the equity curve (0 = starting value, i = after return i).",
    }


def performance_metrics(
    returns: Sequence[float],
    periods_per_year: int = 252,
    risk_free_annual: float = 0.0,
) -> dict:
    """Standard return/risk statistics for a periodic return series."""
    r = _as_array(returns)
    n = r.size
    ppy = periods_per_year
    rf_p = risk_free_annual / ppy
    excess = r - rf_p

    total = float(np.prod(1.0 + r) - 1.0)
    cagr = float((1.0 + total) ** (ppy / n) - 1.0) if total > -1.0 else -1.0
    ann_return = float(r.mean() * ppy)
    ann_vol = float(r.std(ddof=1) * math.sqrt(ppy))
    sd_ex = float(excess.std(ddof=1))
    sharpe = float(excess.mean() / sd_ex * math.sqrt(ppy)) if sd_ex > 0 else None
    downside = np.minimum(excess, 0.0)
    down_dev = math.sqrt(float(np.mean(downside**2))) * math.sqrt(ppy)
    sortino = float(excess.mean() * ppy / down_dev) if down_dev > 0 else None
    mdd = max_drawdown(r.tolist())["max_drawdown"]
    calmar = float(cagr / abs(mdd)) if mdd < 0 else None

    return {
        "observations": n,
        "total_return": total,
        "cagr": cagr,
        "annualized_return_arithmetic": ann_return,
        "annualized_volatility": ann_vol,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown": mdd,
        "calmar_ratio": calmar,
        "skewness": float(stats.skew(r, bias=False)),
        "excess_kurtosis": float(stats.kurtosis(r, fisher=True, bias=False)),
        "hit_rate": float(np.mean(r > 0)),
        "best_period": float(r.max()),
        "worst_period": float(r.min()),
    }


def returns_from_prices(prices: Sequence[float]) -> list[float]:
    p = _as_array(prices, "prices")
    if np.any(p <= 0):
        raise ValueError("Prices must be strictly positive.")
    return (p[1:] / p[:-1] - 1.0).tolist()


def correlation_matrix(series: Mapping[str, Sequence[float]]) -> dict:
    names, mat = _aligned(series)
    corr = np.corrcoef(mat)
    return {"assets": names, "correlation": corr.tolist()}


def _aligned(series: Mapping[str, Sequence[float]]):
    if len(series) < 1:
        raise ValueError("Provide at least one return series.")
    lengths = {len(v) for v in series.values()}
    if len(lengths) != 1:
        raise ValueError("All return series must have the same length.")
    names = list(series.keys())
    mat = np.vstack([_as_array(series[k], k) for k in names])
    return names, mat


def portfolio_risk(
    returns: Mapping[str, Sequence[float]],
    weights: Mapping[str, float],
    periods_per_year: int = 252,
    risk_free_annual: float = 0.0,
) -> dict:
    """Portfolio return/vol plus each asset's share of total risk.

    Weights are normalised to sum to 1 (negative weights allowed = shorts).
    """
    names, mat = _aligned(returns)
    missing = [n for n in names if n not in weights]
    extra = [n for n in weights if n not in returns]
    if missing or extra:
        raise ValueError(f"weights must match returns keys. Missing: {missing}, unknown: {extra}")
    w = np.array([weights[n] for n in names], dtype=float)
    if abs(w.sum()) < 1e-12:
        raise ValueError("Weights sum to zero; cannot normalise.")
    w = w / w.sum()

    cov = np.cov(mat, ddof=1) * periods_per_year
    mu = mat.mean(axis=1) * periods_per_year
    port_var = float(w @ cov @ w)
    port_vol = math.sqrt(port_var)
    port_ret = float(w @ mu)
    marginal = cov @ w
    contrib = w * marginal / port_var if port_var > 0 else np.zeros_like(w)

    sharpe = (port_ret - risk_free_annual) / port_vol if port_vol > 0 else None
    return {
        "assets": names,
        "weights": dict(zip(names, w.tolist(), strict=False)),
        "expected_return_annual": port_ret,
        "volatility_annual": port_vol,
        "sharpe_ratio": sharpe,
        "risk_contribution_pct": dict(zip(names, (contrib * 100).tolist(), strict=False)),
        "asset_volatility_annual": dict(zip(names, np.sqrt(np.diag(cov)).tolist(), strict=False)),
    }


def capm_regression(
    asset_returns: Sequence[float],
    market_returns: Sequence[float],
    periods_per_year: int = 252,
    risk_free_annual: float = 0.0,
) -> dict:
    """OLS of excess asset returns on excess market returns."""
    a = _as_array(asset_returns, "asset_returns")
    m = _as_array(market_returns, "market_returns")
    if a.size != m.size:
        raise ValueError("asset_returns and market_returns must be the same length.")
    rf_p = risk_free_annual / periods_per_year
    ex_a, ex_m = a - rf_p, m - rf_p
    res = stats.linregress(ex_m, ex_a)
    alpha_p = float(res.intercept)
    return {
        "alpha_annualized": alpha_p * periods_per_year,
        "beta": float(res.slope),
        "r_squared": float(res.rvalue**2),
        "beta_p_value": float(res.pvalue),
        "beta_std_error": float(res.stderr),
        "tracking_error_annual": float(np.std(a - m, ddof=1) * math.sqrt(periods_per_year)),
        "observations": int(a.size),
    }


# ---------------------------------------------------------------------------
# Position sizing
# ---------------------------------------------------------------------------


def kelly_fraction(win_prob: float, payoff_ratio: float) -> dict:
    """Kelly stake for a binary bet: f* = p - (1 - p) / b.

    payoff_ratio b = profit per unit staked when you win.
    Negative f* means don't bet. Many practitioners use a fraction of it.
    """
    if not 0.0 <= win_prob <= 1.0:
        raise ValueError("win_prob must be between 0 and 1.")
    if payoff_ratio <= 0:
        raise ValueError("payoff_ratio must be positive.")
    f = win_prob - (1.0 - win_prob) / payoff_ratio
    return {
        "full_kelly": f,
        "half_kelly": f / 2.0,
        "edge_per_unit": win_prob * payoff_ratio - (1.0 - win_prob),
        "bet": f > 0,
    }


def kelly_continuous(mean_excess_return: float, variance: float) -> dict:
    """Continuous-time Kelly leverage approximation: f* = mu / sigma^2.

    Inputs are per the same period (e.g. both annual). Overstates risk when
    returns are fat-tailed; half-Kelly is a common conservative choice.
    """
    if variance <= 0:
        raise ValueError("variance must be positive.")
    f = mean_excess_return / variance
    return {"full_kelly": f, "half_kelly": f / 2.0}


def position_size(
    account_value: float,
    risk_fraction: float,
    entry_price: float,
    stop_price: float,
) -> dict:
    """Shares so that hitting the stop loses `risk_fraction` of the account."""
    if account_value <= 0 or entry_price <= 0 or stop_price <= 0:
        raise ValueError("Account value and prices must be positive.")
    if not 0 < risk_fraction < 1:
        raise ValueError("risk_fraction must be between 0 and 1.")
    per_share = abs(entry_price - stop_price)
    if per_share == 0:
        raise ValueError("Entry and stop must differ.")
    risk_amount = account_value * risk_fraction
    shares = math.floor(risk_amount / per_share)
    notional = shares * entry_price
    return {
        "shares": shares,
        "risk_amount": risk_amount,
        "risk_per_share": per_share,
        "notional": notional,
        "notional_pct_of_account": notional / account_value,
        "direction": "long" if stop_price < entry_price else "short",
    }


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------


def monte_carlo_gbm(
    S0: float,
    mu: float,
    sigma: float,
    T: float,
    paths: int = 10000,
    seed: int | None = 42,
    strike: float | None = None,
    option_type: str = "call",
) -> dict:
    """Simulate terminal prices under geometric Brownian motion.

    The terminal distribution of GBM is lognormal, so it is sampled exactly in
    one step (no time discretisation error). If strike is given, also returns
    the Monte Carlo price of a European option with that strike, discounted at
    mu (pass the risk-free rate as mu for a risk-neutral price).
    """
    if S0 <= 0 or sigma <= 0 or T <= 0:
        raise ValueError("S0, sigma and T must be positive.")
    if paths < 100 or paths > 5_000_000:
        raise ValueError("paths must be between 100 and 5,000,000.")

    rng = np.random.default_rng(seed)
    z = rng.standard_normal(paths)
    ST = np.exp(math.log(S0) + (mu - 0.5 * sigma * sigma) * T + sigma * math.sqrt(T) * z)

    qs = np.quantile(ST, [0.05, 0.25, 0.5, 0.75, 0.95])
    out = {
        "paths": paths,
        "mean_terminal": float(ST.mean()),
        "std_terminal": float(ST.std(ddof=1)),
        "percentiles": {"p05": qs[0], "p25": qs[1], "p50": qs[2], "p75": qs[3], "p95": qs[4]},
        "prob_below_start": float(np.mean(ST < S0)),
    }
    if strike is not None:
        if strike <= 0:
            raise ValueError("strike must be positive.")
        ot = option_type.lower()
        if ot == "call":
            payoff = np.maximum(ST - strike, 0.0)
        elif ot == "put":
            payoff = np.maximum(strike - ST, 0.0)
        else:
            raise ValueError("option_type must be 'call' or 'put'.")
        disc = math.exp(-mu * T)
        price = disc * payoff.mean()
        se = disc * payoff.std(ddof=1) / math.sqrt(paths)
        out["option"] = {
            "type": ot,
            "strike": strike,
            "price": float(price),
            "std_error": float(se),
        }
    return out
