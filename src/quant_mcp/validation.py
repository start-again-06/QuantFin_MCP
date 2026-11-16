"""Input validation shared by all tools.

Every public tool validates its inputs before doing any work, so malformed or
oversized requests fail fast with a clear message rather than producing NaNs
or consuming excessive CPU and memory.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np

MAX_OBSERVATIONS = 100_000
MAX_ASSETS = 200


class ValidationError(ValueError):
    """Raised when a tool receives inputs it cannot process."""


def check_positive(value: float, name: str) -> float:
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValidationError(f"{name} must be a positive finite number.")
    return float(value)


def check_fraction(value: float, name: str, allow_zero: bool = True) -> float:
    lo_ok = value >= 0 if allow_zero else value > 0
    if not isinstance(value, (int, float)) or not math.isfinite(value) or not lo_ok or value > 1:
        bound = "[0, 1]" if allow_zero else "(0, 1]"
        raise ValidationError(f"{name} must be in {bound}.")
    return float(value)


def check_positive_int(value: int, name: str, maximum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValidationError(f"{name} must be a positive integer.")
    if maximum is not None and value > maximum:
        raise ValidationError(f"{name} must be at most {maximum}.")
    return value


def check_series(values: Sequence[float], name: str, min_length: int = 2) -> np.ndarray:
    if isinstance(values, (str, bytes)):
        raise ValidationError(f"{name} must be a list of numbers.")
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1:
        raise ValidationError(f"{name} must be a flat list of numbers.")
    if arr.size < min_length:
        raise ValidationError(f"{name} needs at least {min_length} values (got {arr.size}).")
    if arr.size > MAX_OBSERVATIONS:
        raise ValidationError(f"{name} has more than {MAX_OBSERVATIONS} values.")
    if not np.all(np.isfinite(arr)):
        raise ValidationError(f"{name} contains NaN or infinite values.")
    return arr


def aligned_matrix(
    series: Mapping[str, Sequence[float]],
    min_length: int = 2,
) -> tuple[list[str], np.ndarray]:
    """Validate a {name: values} mapping and stack it into an (assets x obs) matrix."""
    if not isinstance(series, Mapping) or len(series) == 0:
        raise ValidationError("Provide a non-empty mapping of asset name to return series.")
    if len(series) > MAX_ASSETS:
        raise ValidationError(f"At most {MAX_ASSETS} assets are supported.")
    names = list(series.keys())
    rows = [check_series(series[n], f"series '{n}'", min_length) for n in names]
    lengths = {r.size for r in rows}
    if len(lengths) != 1:
        raise ValidationError("All return series must have the same length.")
    return names, np.vstack(rows)
