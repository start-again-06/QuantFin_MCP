import asyncio
import sys
from pathlib import Path

import pytest

from quant_mcp import server

EXPECTED_TOOLS = {
    "black_scholes",
    "american_option",
    "implied_volatility",
    "monte_carlo_gbm",
    "bond_analytics",
    "npv_irr",
    "value_at_risk",
    "performance_metrics",
    "max_drawdown",
    "returns_from_prices",
    "correlation_matrix",
    "capm_regression",
    "portfolio_risk",
    "min_variance_portfolio",
    "max_sharpe_portfolio",
    "risk_parity_portfolio",
    "efficient_frontier",
    "hrp_portfolio",
    "backtest_portfolio",
    "moving_average_crossover",
    "kelly_fraction",
    "kelly_continuous",
    "position_size",
    "price_history",
}


def test_all_expected_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    assert {t.name for t in tools} == EXPECTED_TOOLS


def test_every_tool_has_a_description():
    tools = asyncio.run(server.mcp.list_tools())
    assert all(t.description and len(t.description) > 20 for t in tools)


def test_validation_errors_become_value_errors():
    wrapped = server._tool(lambda: (_ for _ in ()).throw(server.ValidationError("bad input")))
    with pytest.raises(ValueError, match="bad input"):
        wrapped()


def test_logs_do_not_contain_inputs(caplog):
    import logging

    caplog.set_level(logging.INFO, logger="quant_mcp")

    @server._tool
    def secret_tool(payload):
        return {"ok": True}

    secret_tool([0.123456789, 9.87654321])
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "tool=secret_tool" in text
    assert "0.123456789" not in text


def test_stdio_server_speaks_mcp_and_keeps_stdout_clean():
    """End-to-end: launch the server as a subprocess and call a tool over stdio."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    src = str(Path(__file__).resolve().parents[1] / "src")

    async def run():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "quant_mcp"],
            env={"PYTHONPATH": src, "PATH": "", "QUANT_MCP_LOG_LEVEL": "ERROR"},
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool(
                "black_scholes",
                {"spot": 100, "strike": 100, "time_years": 1, "rate": 0.05, "volatility": 0.2},
            )
            assert not res.isError
            return res.content[0].text

    text = asyncio.run(run())
    assert "price" in text


@pytest.mark.network
def test_price_history_live_yahoo():
    import os

    if os.environ.get("QUANT_MCP_RUN_NETWORK_TESTS") != "1":
        pytest.skip("set QUANT_MCP_RUN_NETWORK_TESTS=1 to run live provider tests")
    from quant_mcp import market_data

    out = market_data.price_history("SPY", "1mo")
    assert out["observations"] > 5
