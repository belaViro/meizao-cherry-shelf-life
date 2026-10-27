"""Existing project instrument mapping, not a universal FT11 calibration."""
SLOPE = 0.14
INTERCEPT = 32.714
MIN_READING = 40
MAX_READING = 90
CONVERSION_CONFIG = dict(slope=SLOPE, intercept=INTERCEPT, minimum=MIN_READING, maximum=MAX_READING)


def map_handheld_to_g_mm2(reading: float) -> float:
    return (reading - INTERCEPT) / SLOPE
