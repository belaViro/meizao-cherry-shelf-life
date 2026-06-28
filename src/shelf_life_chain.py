from __future__ import annotations

import json
import os
import re
from bisect import bisect_left
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnableSerializable

from src.schemas import NormalizedShelfLifeInput, ShelfLifePrediction, ShelfLifeRequest


POLYNOMIAL_TEMPERATURE_RANGE_C = {"min": 0.0, "max": 25.0}
POLYNOMIAL_FORMULA = "L = -0.00133333*T^3 + 0.068095*T^2 - 1.445238*T + 19.904762"
DEFAULT_SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_SILICONFLOW_MODEL = "Qwen/Qwen2.5-7B-Instruct"

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _normalize_input(payload: dict) -> NormalizedShelfLifeInput:
    request = ShelfLifeRequest.model_validate(payload)
    selected_temperature = _require_temperature_in_range(request.storage_temperature_c)
    firmness_g_mm2 = _map_handheld_to_g_mm2(request.firmness, request.firmness_unit)

    return NormalizedShelfLifeInput(
        storage_temperature_c=selected_temperature,
        handheld_hardness=round(request.firmness, 2),
        firmness_g_mm2=round(firmness_g_mm2, 3),
        original_firmness=request.firmness,
        original_firmness_unit=request.firmness_unit,
        prediction_method=request.prediction_method,
    )


def _require_temperature_in_range(value: float) -> float:
    normalized = round(float(value), 3)
    min_temperature = POLYNOMIAL_TEMPERATURE_RANGE_C["min"]
    max_temperature = POLYNOMIAL_TEMPERATURE_RANGE_C["max"]
    if min_temperature <= normalized <= max_temperature:
        return normalized

    raise ValueError(
        "Unsupported storage_temperature_c. "
        f"Supported range: {min_temperature:g}-{max_temperature:g} C."
    )


def _map_handheld_to_g_mm2(value: float, unit: str) -> float:
    if unit != "handheld":
        raise ValueError("Unsupported firmness_unit. Only handheld is accepted.")
    return 200 + (value - 50) * (300 / 40)


def _predict_shelf_life(data: NormalizedShelfLifeInput) -> ShelfLifePrediction:
    if data.prediction_method == "polynomial_regression":
        return _predict_with_polynomial_regression(data)
    if data.prediction_method == "llm_structured":
        return _predict_with_llm_structured_output(data)
    raise ValueError("Unsupported prediction_method.")


def _predict_with_polynomial_regression(data: NormalizedShelfLifeInput) -> ShelfLifePrediction:
    regression_days = _cubic_polynomial_shelf_life(data.storage_temperature_c)
    firmness_factor = _firmness_factor(data.firmness_g_mm2)
    estimated_days = max(0.5, regression_days * firmness_factor)

    range_width = _range_width(data.storage_temperature_c, data.firmness_g_mm2)
    low_days = max(0.5, estimated_days * (1 - range_width))
    high_days = estimated_days * (1 + range_width)
    risk_level = _risk_level(estimated_days, data.storage_temperature_c, data.firmness_g_mm2)

    return ShelfLifePrediction(
        cultivar=data.cultivar,
        prediction_method="polynomial_regression",
        storage_temperature_c=data.storage_temperature_c,
        handheld_hardness=round(data.handheld_hardness, 2),
        firmness_g_mm2=round(data.firmness_g_mm2, 2),
        estimated_shelf_life_days=round(estimated_days, 1),
        shelf_life_range_days={"min": round(low_days, 1), "max": round(high_days, 1)},
        risk_level=risk_level,
        confidence=_confidence(data.storage_temperature_c, data.firmness_g_mm2),
        decision=_decision_text(risk_level),
        method_details={
            "formula": POLYNOMIAL_FORMULA,
            "temperature_regression_shelf_life_days": round(regression_days, 2),
            "handheld_hardness": round(data.handheld_hardness, 2),
            "mapped_firmness_g_mm2": round(data.firmness_g_mm2, 2),
            "mapping_formula": "g_mm2 = 200 + (handheld - 50) * 7.5",
            "firmness_adjustment_factor": round(firmness_factor, 3),
            "temperature_unit": "C",
            "shelf_life_unit": "days",
        },
        assumptions=[
            "Temperature baseline is calculated by cubic polynomial regression.",
            "T is storage temperature in Celsius and L is temperature-based shelf life in days.",
            "Handheld hardness is linearly mapped from 50-90 to 200-500 g*mm^-2 before prediction.",
            "Prediction assumes clean fruit, intact stems, no visible decay, and stable storage temperature.",
        ],
        recommendations=_recommendations(data.storage_temperature_c, risk_level),
    )


def _predict_with_llm_structured_output(data: NormalizedShelfLifeInput) -> ShelfLifePrediction:
    api_key = os.getenv("SILICONFLOW_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("llm_structured requires SILICONFLOW_API_KEY in the environment.")

    try:
        import httpx
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise ValueError("llm_structured requires langchain-openai and httpx. Run: pip install -r requirements.txt") from exc

    base_url = os.getenv("SILICONFLOW_BASE_URL", DEFAULT_SILICONFLOW_BASE_URL)
    model_name = os.getenv("SILICONFLOW_MODEL", DEFAULT_SILICONFLOW_MODEL)
    regression_days = _cubic_polynomial_shelf_life(data.storage_temperature_c)

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a postharvest quality prediction assistant. Return exactly one JSON object. "
                "No markdown, no code fences, no comments, no null output.",
            ),
            (
                "human",
                "Predict Meizao cherry shelf life. Use conservative cold-chain reasoning.\n"
                "Input:\n"
                "storage_temperature_c={temperature_c}\n"
                "handheld_hardness={handheld_hardness}\n"
                "firmness_g_mm2={firmness_g_mm2}\n"
                "polynomial_formula={formula}\n"
                "polynomial_baseline_days={regression_days}\n\n"
                "Return JSON with exactly this shape and compatible value types:\n"
                "{{\n"
                "  \"cultivar\": \"Meizao cherry\",\n"
                "  \"prediction_method\": \"llm_structured\",\n"
                "  \"storage_temperature_c\": {temperature_c},\n"
                "  \"handheld_hardness\": {handheld_hardness},\n"
                "  \"firmness_g_mm2\": {firmness_g_mm2},\n"
                "  \"estimated_shelf_life_days\": 0.0,\n"
                "  \"shelf_life_range_days\": {{\"min\": 0.0, \"max\": 0.0}},\n"
                "  \"risk_level\": \"low\",\n"
                "  \"confidence\": 0.0,\n"
                "  \"decision\": \"string\",\n"
                "  \"method_details\": {{\n"
                "    \"llm_provider\": \"siliconflow\",\n"
                "    \"llm_model\": \"{model_name}\",\n"
                "    \"reference_formula\": \"{formula}\",\n"
                "    \"polynomial_baseline_days\": {regression_days},\n"
                "    \"mapping_formula\": \"g_mm2 = 200 + (handheld - 50) * 7.5\"\n"
                "  }},\n"
                "  \"assumptions\": [\"string\"],\n"
                "  \"recommendations\": [\"string\"]\n"
                "}}\n\n"
                "Constraints:\n"
                "- risk_level must be low, medium, or high.\n"
                "- confidence must be between 0 and 1.\n"
                "- shelf_life_range_days.min <= estimated_shelf_life_days <= shelf_life_range_days.max.\n"
                "- method_details values must be only strings or numbers.\n"
                "- Output must start with {{ and end with }}.",
            ),
        ]
    )

    http_client = httpx.Client(trust_env=False, timeout=60.0)
    llm = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
        timeout=60,
        max_retries=1,
        max_tokens=800,
        model_kwargs={"response_format": {"type": "json_object"}},
        http_client=http_client,
    )
    raw_message = (prompt | llm).invoke(
        {
            "temperature_c": data.storage_temperature_c,
            "handheld_hardness": round(data.handheld_hardness, 2),
            "firmness_g_mm2": round(data.firmness_g_mm2, 2),
            "formula": POLYNOMIAL_FORMULA,
            "regression_days": round(regression_days, 2),
            "model_name": model_name,
        }
    )
    parsed = _extract_json_object(raw_message.content)
    return ShelfLifePrediction.model_validate(parsed)


def _extract_json_object(content: Any) -> dict[str, Any]:
    if isinstance(content, list):
        content = "".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content)
    text = str(content or "").strip()
    if not text or text.lower() == "null":
        raise ValueError("LLM returned empty or null content instead of structured JSON.")

    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text).strip()

    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise ValueError(f"LLM output did not contain a JSON object: {text[:300]}")
        loaded = json.loads(match.group(0))

    if not isinstance(loaded, dict):
        raise ValueError(f"LLM output must be a JSON object, got {type(loaded).__name__}.")
    return loaded


def _cubic_polynomial_shelf_life(temperature_c: float) -> float:
    return (
        -0.00133333 * temperature_c**3
        + 0.068095 * temperature_c**2
        - 1.445238 * temperature_c
        + 19.904762
    )


def _firmness_factor(firmness_n: float) -> float:
    points = [
        (200.0, 0.65),
        (260.0, 0.8),
        (320.0, 1.0),
        (380.0, 1.12),
        (440.0, 1.22),
        (500.0, 1.3),
    ]
    return _linear_interpolate(points, firmness_n)


def _linear_interpolate(points: list[tuple[float, float]], x_value: float) -> float:
    if x_value <= points[0][0]:
        return points[0][1]
    if x_value >= points[-1][0]:
        return points[-1][1]

    insert_at = bisect_left([point[0] for point in points], x_value)
    x0, y0 = points[insert_at - 1]
    x1, y1 = points[insert_at]
    ratio = (x_value - x0) / (x1 - x0)
    return y0 + ratio * (y1 - y0)


def _range_width(temperature_c: float, firmness_n: float) -> float:
    width = 0.18
    if temperature_c >= 8:
        width += 0.06
    if firmness_n < 260:
        width += 0.06
    return min(width, 0.35)


def _risk_level(estimated_days: float, temperature_c: float, firmness_n: float) -> str:
    if temperature_c >= 20 or estimated_days < 4 or firmness_n < 240:
        return "high"
    if temperature_c >= 8 or estimated_days < 10 or firmness_n < 300:
        return "medium"
    return "low"


def _confidence(temperature_c: float, firmness_n: float) -> float:
    confidence = 0.74
    if 0 <= temperature_c <= 4:
        confidence += 0.08
    if 240 <= firmness_n <= 450:
        confidence += 0.08
    if temperature_c >= 20:
        confidence -= 0.08
    return round(max(0.45, min(confidence, 0.9)), 2)


def _decision_text(risk_level: str) -> str:
    if risk_level == "low":
        return "Suitable for cold-chain storage and normal sale planning."
    if risk_level == "medium":
        return "Prioritize sale and keep temperature stable."
    return "Sell or process as soon as possible; do not plan long storage."


def _recommendations(temperature_c: float, risk_level: str) -> list[str]:
    recommendations = [
        "Keep relative humidity high enough to limit water loss.",
        "Recheck hardness and visible decay during storage.",
    ]
    if temperature_c > 4:
        recommendations.insert(0, "Move fruit to 0-4 C cold-chain storage when possible.")
    if risk_level == "high":
        recommendations.append("Shorten inspection interval and separate softened or damaged fruit.")
    return recommendations


def _to_structured_dict(prediction: ShelfLifePrediction) -> dict:
    return prediction.model_dump()


def build_shelf_life_chain() -> RunnableSerializable[dict, dict]:
    return (
        RunnableLambda(_normalize_input).with_config(run_name="normalize_input")
        | RunnableLambda(_predict_shelf_life).with_config(run_name="predict_shelf_life")
        | RunnableLambda(_to_structured_dict).with_config(run_name="structured_output")
    )







