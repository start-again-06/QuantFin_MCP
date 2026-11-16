"""Historical price data for the quant tools, via yfinance.

yfinance is imported lazily, so the calculators work without it installed.
Data comes from Yahoo Finance, which needs direct internet access from the
machine running the server. It is not a licensed or real-time feed: prices
can be delayed, adjusted for splits and dividends, and occasionally wrong.
"""

from __future__ import annotations

import datetime as _dt
import os
import re

ALLOWED_PERIODS = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}
ALLOWED_INTERVALS = {"1d", "5d", "1wk", "1mo", "3mo"}
_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-=^]{1,20}$")


PROVIDERS = {"yahoo", "alphavantage"}
DEFAULT_ENABLED_PROVIDERS = "yahoo"


def enabled_providers() -> set[str]:
    """Providers this server will call. Set QUANT_MCP_ENABLED_PROVIDERS to change.

    Default is 'yahoo' only. Enabling 'alphavantage' lets callers spend your
    Alpha Vantage daily quota, so enable it only if callers are controlled by your own access layer.
    """
    raw = os.environ.get("QUANT_MCP_ENABLED_PROVIDERS", DEFAULT_ENABLED_PROVIDERS)
    return {p.strip().lower() for p in raw.split(",") if p.strip()} & PROVIDERS


_PERIOD_DAYS = {
    "1d": 1,
    "5d": 5,
    "1mo": 31,
    "3mo": 92,
    "6mo": 183,
    "1y": 366,
    "2y": 732,
    "5y": 1830,
    "10y": 3660,
}
_ALPHAVANTAGE_URL = "https://www.alphavantage.co/query"


def price_history(
    ticker: str,
    period: str = "1y",
    interval: str = "1d",
    adjusted: bool = True,
    provider: str = "yahoo",
) -> dict:
    """Daily (or coarser) closing prices for one ticker, with dates.

    adjusted=True applies split and dividend adjustments, which is what you
    want for return and risk calculations.

    provider: 'yahoo' (default, no key needed) or 'alphavantage' (needs the
    ALPHAVANTAGE_API_KEY environment variable; daily data only).
    """
    t = ticker.strip().upper()
    if not _TICKER_RE.match(t):
        raise ValueError(f"Invalid ticker symbol: {ticker!r}")
    if period not in ALLOWED_PERIODS:
        raise ValueError(f"period must be one of {sorted(ALLOWED_PERIODS)}")
    if interval not in ALLOWED_INTERVALS:
        raise ValueError(f"interval must be one of {sorted(ALLOWED_INTERVALS)}")
    provider = provider.lower()
    if provider not in PROVIDERS:
        raise ValueError(f"provider must be one of {sorted(PROVIDERS)}")
    if provider not in enabled_providers():
        raise ValueError(
            f"provider '{provider}' is not enabled on this server "
            "(the operator sets QUANT_MCP_ENABLED_PROVIDERS)."
        )
    if provider == "alphavantage":
        if interval != "1d":
            raise ValueError("alphavantage provider supports interval '1d' only.")
        return _alphavantage_history(t, period, adjusted)

    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("yfinance is not installed. Run: pip install yfinance") from exc

    try:
        df = yf.Ticker(t).history(period=period, interval=interval, auto_adjust=adjusted)
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch data for {t}: {exc}") from exc

    if df is None or len(df) == 0 or "Close" not in df:
        raise ValueError(f"No price data returned for {t} (check the ticker, period or network access).")

    closes = [float(x) for x in df["Close"].tolist() if x == x]  # drop NaN
    dates = [
        idx.strftime("%Y-%m-%d") for idx, x in zip(df.index, df["Close"].tolist(), strict=False) if x == x
    ]
    return {
        "ticker": t,
        "period": period,
        "interval": interval,
        "adjusted": adjusted,
        "observations": len(closes),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "dates": dates,
        "closes": closes,
        "source": "Yahoo Finance via yfinance (not a licensed or real-time feed)",
    }


def _alphavantage_history(ticker: str, period: str, adjusted: bool) -> dict:
    """Daily prices from Alpha Vantage. The API key is read from the environment
    and is never included in returned data or error messages."""
    import json
    import os
    import urllib.parse
    import urllib.request

    key = os.environ.get("ALPHAVANTAGE_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "ALPHAVANTAGE_API_KEY is not set. Get a free key from alphavantage.co and "
            "export it in the environment that starts the server."
        )

    function = "TIME_SERIES_DAILY_ADJUSTED" if adjusted else "TIME_SERIES_DAILY"
    query = urllib.parse.urlencode(
        {
            "function": function,
            "symbol": ticker,
            "outputsize": "full",
            "apikey": key,
        }
    )
    try:
        with urllib.request.urlopen(f"{_ALPHAVANTAGE_URL}?{query}", timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        # Scrub the key in case the exception text contains the URL.
        msg = str(exc).replace(key, "***")
        raise RuntimeError(f"Alpha Vantage request failed for {ticker}: {msg}") from None

    if "Error Message" in payload:
        raise ValueError(f"Alpha Vantage rejected {ticker}: {payload['Error Message']}")
    if "Note" in payload or "Information" in payload:
        raise RuntimeError(
            "Alpha Vantage rate or usage limit: " + str(payload.get("Note") or payload.get("Information"))
        )

    series = payload.get("Time Series (Daily)")
    if not series:
        raise ValueError(f"No daily price data returned for {ticker}.")

    close_key = "5. adjusted close" if adjusted else "4. close"
    rows = sorted(series.items())  # ISO dates sort chronologically
    days = _PERIOD_DAYS.get(period)
    if period == "ytd":
        cutoff = f"{_dt.date.today().year}-01-01"
        rows = [r for r in rows if r[0] >= cutoff]
    elif days is not None:  # 'max' has no entry in _PERIOD_DAYS and is left untrimmed
        cutoff = (_dt.date.today() - _dt.timedelta(days=days)).isoformat()
        rows = [r for r in rows if r[0] >= cutoff]

    dates = [d for d, v in rows if close_key in v]
    closes = [float(v[close_key]) for d, v in rows if close_key in v]
    if not closes:
        raise ValueError(f"No '{close_key}' values returned for {ticker}.")
    return {
        "ticker": ticker,
        "period": period,
        "interval": "1d",
        "adjusted": adjusted,
        "observations": len(closes),
        "first_date": dates[0],
        "last_date": dates[-1],
        "dates": dates,
        "closes": closes,
        "source": "Alpha Vantage (requires your API key; subject to Alpha Vantage's terms and rate limits)",
    }
