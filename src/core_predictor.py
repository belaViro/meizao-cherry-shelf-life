from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass
from functools import lru_cache


SUPPORTED_STORAGE_TEMPERATURES_C = (0.0, 5.0, 10.0, 15.0, 20.0, 25.0)
MIN_TEMPERATURE_C = 0.0
MAX_TEMPERATURE_C = 25.0
MIN_HANDHELD_HARDNESS = 40.0
MAX_HANDHELD_HARDNESS = 90.0
POLYNOMIAL_TEMPERATURE_RANGE_C = {
    "min": MIN_TEMPERATURE_C,
    "max": MAX_TEMPERATURE_C,
}
POLYNOMIAL_FORMULA = (
    "L = -0.00177778*T^3 + 0.0952381*T^2 - 2.03175*T + 24.2381"
)

# (temperature C, handheld hardness, target days,
#  temperature influence width, hardness influence width)
# The 0 C/hardness-70, 5 C/hardness-70 and 25 C/hardness-60 values are
# retained calibration anchors. The other hardness-70 values keep the
# temperature curve smooth between the six selectable temperatures.
CALIBRATION_CONTROL_POINTS = (
    (0.0, 70.0, 37.0, 7.5, math.inf),
    (5.0, 70.0, 25.0, 7.5, math.inf),
    (10.0, 70.0, 17.0, 7.5, math.inf),
    (15.0, 70.0, 11.0, 7.5, math.inf),
    (20.0, 70.0, 7.0, 7.5, math.inf),
    (25.0, 70.0, 4.0, 7.5, math.inf),
    (25.0, 60.0, 2.0, 7.5, 8.0),
)

FIRMNESS_FACTOR_POINTS = (
    (0.0, ((50.0, 0.25), (70.0, 0.79), (90.0, 1.12))),
    (5.0, ((50.0, 0.25), (70.0, 0.79), (90.0, 1.12))),
    (10.0, ((50.0, 0.21), (70.0, 0.78), (90.0, 1.12))),
    (15.0, ((50.0, 0.16), (70.0, 0.76), (90.0, 1.12))),
    (20.0, ((50.0, 0.10), (70.0, 0.73), (90.0, 1.12))),
    (25.0, ((50.0, 0.10), (70.0, 0.72), (90.0, 1.12))),
)


@dataclass(frozen=True)
class ShelfLifeResult:
    storage_temperature_c: float
    handheld_hardness: float
    firmness_g_mm2: float
    estimated_shelf_life_days: float
    range_min_days: float
    range_max_days: float
    risk_level: str
    confidence: float
    decision: str
    recommendations: tuple[str, ...]
    temperature_baseline_days: float
    firmness_adjustment_factor: float
    calibration_factor: float


def predict_shelf_life(
    storage_temperature_c: float,
    handheld_hardness: float,
) -> ShelfLifeResult:
    """Predict cherry shelf life using only the local mathematical model."""
    temperature_c = normalize_temperature(storage_temperature_c)
    hardness = normalize_hardness(handheld_hardness)
    firmness_g_mm2 = map_handheld_to_g_mm2(hardness)

    baseline_days = cubic_polynomial_shelf_life(temperature_c)
    hardness_factor = firmness_factor(hardness, temperature_c)
    calibration = reference_calibration_factor(temperature_c, hardness)
    raw_estimated_days = max(0.3, baseline_days * hardness_factor * calibration)

    range_width = prediction_range_width(temperature_c, firmness_g_mm2)
    range_min_days = max(0.3, raw_estimated_days * (1.0 - range_width))
    range_max_days = raw_estimated_days * (1.0 + range_width)
    risk = risk_level(raw_estimated_days, temperature_c, firmness_g_mm2)

    return ShelfLifeResult(
        storage_temperature_c=temperature_c,
        handheld_hardness=round(hardness, 2),
        firmness_g_mm2=round(firmness_g_mm2, 2),
        estimated_shelf_life_days=round(raw_estimated_days, 1),
        range_min_days=round(range_min_days, 1),
        range_max_days=round(range_max_days, 1),
        risk_level=risk,
        confidence=prediction_confidence(temperature_c, firmness_g_mm2),
        decision=decision_text(risk),
        recommendations=tuple(recommendations(temperature_c, risk)),
        temperature_baseline_days=round(baseline_days, 2),
        firmness_adjustment_factor=round(hardness_factor, 3),
        calibration_factor=round(calibration, 3),
    )


def normalize_temperature(value: float) -> float:
    temperature_c = _finite_number(value, "储藏温度")
    temperature_c = round(temperature_c, 3)
    if MIN_TEMPERATURE_C <= temperature_c <= MAX_TEMPERATURE_C:
        return temperature_c
    raise ValueError(
        f"储藏温度必须在 {MIN_TEMPERATURE_C:g}-{MAX_TEMPERATURE_C:g} ℃之间。"
    )


def normalize_hardness(value: float) -> float:
    hardness = _finite_number(value, "手持硬度")
    if MIN_HANDHELD_HARDNESS <= hardness <= MAX_HANDHELD_HARDNESS:
        return hardness
    raise ValueError(
        f"硬度检测值必须在 {MIN_HANDHELD_HARDNESS:g}-{MAX_HANDHELD_HARDNESS:g} 之间。"
    )


def _finite_number(value: float, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name}必须是数字。") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name}必须是有限数字。")
    return number


def map_handheld_to_g_mm2(handheld_hardness: float) -> float:
    return (handheld_hardness - 32.714) / 0.14


def cubic_polynomial_shelf_life(temperature_c: float) -> float:
    return (
        -0.00177778 * temperature_c**3
        + 0.0952381 * temperature_c**2
        - 2.03175 * temperature_c
        + 24.2381
    )


def firmness_factor(handheld_hardness: float, temperature_c: float) -> float:
    if temperature_c <= FIRMNESS_FACTOR_POINTS[0][0]:
        return quadratic_interpolate(FIRMNESS_FACTOR_POINTS[0][1], handheld_hardness)
    if temperature_c >= FIRMNESS_FACTOR_POINTS[-1][0]:
        return quadratic_interpolate(FIRMNESS_FACTOR_POINTS[-1][1], handheld_hardness)

    temperatures = [point[0] for point in FIRMNESS_FACTOR_POINTS]
    insert_at = bisect_left(temperatures, temperature_c)
    t0, hardness_points0 = FIRMNESS_FACTOR_POINTS[insert_at - 1]
    t1, hardness_points1 = FIRMNESS_FACTOR_POINTS[insert_at]
    factor0 = quadratic_interpolate(hardness_points0, handheld_hardness)
    factor1 = quadratic_interpolate(hardness_points1, handheld_hardness)
    ratio = (temperature_c - t0) / (t1 - t0)
    return factor0 + ratio * (factor1 - factor0)


def reference_calibration_factor(
    temperature_c: float,
    handheld_hardness: float,
) -> float:
    weights = _calibration_weights()
    log_correction = sum(
        weight * calibration_basis(temperature_c, handheld_hardness, control_point)
        for weight, control_point in zip(weights, CALIBRATION_CONTROL_POINTS)
    )
    return math.exp(log_correction)


@lru_cache(maxsize=1)
def _calibration_weights() -> tuple[float, ...]:
    matrix = [
        [
            calibration_basis(t_i, h_i, control_point)
            for control_point in CALIBRATION_CONTROL_POINTS
        ]
        for t_i, h_i, _, _, _ in CALIBRATION_CONTROL_POINTS
    ]
    log_ratios = []
    for temperature_c, hardness, target_days, _, _ in CALIBRATION_CONTROL_POINTS:
        raw_days = cubic_polynomial_shelf_life(temperature_c) * firmness_factor(
            hardness, temperature_c
        )
        log_ratios.append(math.log(target_days / raw_days))
    return tuple(solve_linear_system(matrix, log_ratios))


def calibration_basis(
    temperature_c: float,
    handheld_hardness: float,
    control_point: tuple[float, float, float, float, float],
) -> float:
    reference_temperature_c, reference_hardness, _, temperature_width_c, hardness_width = (
        control_point
    )
    temperature_distance = (
        temperature_c - reference_temperature_c
    ) / temperature_width_c
    hardness_distance = (handheld_hardness - reference_hardness) / hardness_width
    return math.exp(-(temperature_distance**2 + hardness_distance**2))


def solve_linear_system(
    matrix: list[list[float]],
    values: list[float],
) -> list[float]:
    size = len(values)
    augmented = [row[:] + [value] for row, value in zip(matrix, values)]

    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("校准控制点产生了不可求解的奇异矩阵。")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]

        pivot_value = augmented[column][column]
        augmented[column] = [value / pivot_value for value in augmented[column]]

        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                current - factor * pivot_current
                for current, pivot_current in zip(augmented[row], augmented[column])
            ]

    return [augmented[row][-1] for row in range(size)]


def quadratic_interpolate(
    points: tuple[tuple[float, float], ...],
    x_value: float,
) -> float:
    if len(points) != 3:
        raise ValueError("二次插值必须提供三个控制点。")

    x_value = min(max(x_value, points[0][0]), points[-1][0])
    result = 0.0
    for index, (x_i, y_i) in enumerate(points):
        basis = 1.0
        for other_index, (x_j, _) in enumerate(points):
            if index != other_index:
                basis *= (x_value - x_j) / (x_i - x_j)
        result += y_i * basis
    return result


def linear_interpolate(
    points: tuple[tuple[float, float], ...],
    x_value: float,
) -> float:
    if x_value <= points[0][0]:
        return points[0][1]
    if x_value >= points[-1][0]:
        return points[-1][1]

    insert_at = bisect_left([point[0] for point in points], x_value)
    x0, y0 = points[insert_at - 1]
    x1, y1 = points[insert_at]
    ratio = (x_value - x0) / (x1 - x0)
    return y0 + ratio * (y1 - y0)


def prediction_range_width(temperature_c: float, firmness_g_mm2: float) -> float:
    width = 0.18
    if temperature_c >= 8:
        width += 0.06
    if firmness_g_mm2 < 260:
        width += 0.06
    return min(width, 0.35)


def risk_level(
    estimated_days: float,
    temperature_c: float,
    firmness_g_mm2: float,
) -> str:
    if temperature_c >= 20 or estimated_days < 4 or firmness_g_mm2 < 240:
        return "high"
    if temperature_c >= 8 or estimated_days < 10 or firmness_g_mm2 < 300:
        return "medium"
    return "low"


def prediction_confidence(temperature_c: float, firmness_g_mm2: float) -> float:
    confidence = 0.74
    if 0 <= temperature_c <= 4:
        confidence += 0.08
    if 240 <= firmness_g_mm2 <= 450:
        confidence += 0.08
    if temperature_c >= 20:
        confidence -= 0.08
    return round(max(0.45, min(confidence, 0.9)), 2)


def decision_text(risk: str) -> str:
    if risk == "low":
        return "适合冷链贮藏，可按正常销售节奏安排。"
    if risk == "medium":
        return "建议优先销售，并保持贮藏温度稳定。"
    return "建议尽快销售或加工，不宜安排长时间贮藏。"


def recommendations(temperature_c: float, risk: str) -> list[str]:
    items = [
        "保持包装完整并减少频繁开箱，降低温度波动对果实品质的影响。",
        "贮藏期间定期复测硬度，并检查是否出现腐烂。",
    ]
    if temperature_c > 4:
        items.insert(0, "条件允许时，将果实转入 0-4 ℃ 冷链环境。")
    if risk == "high":
        items.append("缩短巡检间隔，及时剔除软化或损伤果。")
    return items
