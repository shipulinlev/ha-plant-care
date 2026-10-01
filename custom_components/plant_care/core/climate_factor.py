"""Climate multiplier for the watering interval."""

from .models import ClimateReading, ClimateStatus, SpeciesProfile


def _deviation(
    value: float | None, low: float | None, high: float | None
) -> float | None:
    """Signed distance outside [low, high] relative to the range width.

    Positive above the range, negative below, 0 inside. None when the value or
    a usable range is missing.
    """
    if value is None or low is None or high is None or high <= low:
        return None
    if value > high:
        return (value - high) / (high - low)
    if value < low:
        return (value - low) / (high - low)
    return 0.0


def climate_multiplier(
    reading: ClimateReading,
    profile: SpeciesProfile | None,
    lower: float,
    upper: float,
) -> tuple[float, ClimateStatus]:
    """Scale factor for the watering interval and the climate status.

    Hotter or drier than the species range shortens the interval; colder or more
    humid lengthens it. The result is clamped to [lower, upper].
    """
    if profile is None:
        return 1.0, ClimateStatus.UNKNOWN
    temp = _deviation(reading.temperature, profile.min_temp, profile.max_temp)
    humid = _deviation(reading.humidity, profile.min_env_humid, profile.max_env_humid)
    if temp is None and humid is None:
        return 1.0, ClimateStatus.UNKNOWN

    factor = (1.0 - (temp or 0.0)) * (1.0 + (humid or 0.0))
    status = ClimateStatus.OUT_OF_RANGE if temp or humid else ClimateStatus.OK
    return min(max(factor, lower), upper), status
