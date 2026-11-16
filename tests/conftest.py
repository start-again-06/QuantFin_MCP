import numpy as np
import pytest


@pytest.fixture(scope="session")
def three_asset_returns():
    """Deterministic correlated daily returns for three assets, 750 observations."""
    rng = np.random.default_rng(11)
    cov = np.array(
        [
            [0.0004, 0.0001, 0.00005],
            [0.0001, 0.0009, 0.00010],
            [0.00005, 0.0001, 0.0016],
        ]
    )
    mat = rng.multivariate_normal([0.0004, 0.0005, 0.0003], cov, size=750)
    return {"AAA": mat[:, 0].tolist(), "BBB": mat[:, 1].tolist(), "CCC": mat[:, 2].tolist()}
