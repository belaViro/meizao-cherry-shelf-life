from __future__ import annotations

import json
import os
import re
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnableSerializable

from src.schemas import NormalizedShelfLifeInput, ShelfLifePrediction, ShelfLifeRequest

from src.core_predictor import (
    POLYNOMIAL_FORMULA,
    POLYNOMIAL_TEMPERATURE_RANGE_C,
    SUPPORTED_STORAGE_TEMPERATURES_C,
    cubic_polynomial_shelf_life,
    map_handheld_to_g_mm2,
    normalize_temperature,
    predict_shelf_life,
)

DEFAULT_SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_SILICONFLOW_MODEL = "Qwen/Qwen2.5-7B-Instruct"

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _normalize_input(payload: dict) -> NormalizedShelfLifeInput:
    request = ShelfLifeRequest.model_validate(payload)
    selected_temperature = normalize_temperature(request.storage_temperature_c)
    firmness_g_mm2 = map_handheld_to_g_mm2(request.firmness)

    return NormalizedShelfLifeInput(
        storage_temperature_c=selected_temperature,
        handheld_hardness=round(request.firmness, 2),
        firmness_g_mm2=round(firmness_g_mm2, 3),
        original_firmness=request.firmness,
        original_firmness_unit=request.firmness_unit,
        prediction_method=request.prediction_method,
    )


def _predict_shelf_life(data: NormalizedShelfLifeInput) -> ShelfLifePrediction:
    if data.prediction_method == "polynomial_regression":
        return _predict_with_polynomial_regression(data)
    if data.prediction_method == "llm_structured":
        return _predict_with_llm_structured_output(data)
    raise ValueError("Unsupported prediction_method.")


def _predict_with_polynomial_regression(data: NormalizedShelfLifeInput) -> ShelfLifePrediction:
    result = predict_shelf_life(
        data.storage_temperature_c,
        data.handheld_hardness,
    )

    return ShelfLifePrediction(
        cultivar=data.cultivar,
        prediction_method="polynomial_regression",
        storage_temperature_c=result.storage_temperature_c,
        handheld_hardness=result.handheld_hardness,
        firmness_g_mm2=result.firmness_g_mm2,
        estimated_shelf_life_days=result.estimated_shelf_life_days,
        shelf_life_range_days={
            "min": result.range_min_days,
            "max": result.range_max_days,
        },
        risk_level=result.risk_level,
        confidence=result.confidence,
        decision=result.decision,
        method_details={
            "formula": POLYNOMIAL_FORMULA,
            "temperature_regression_shelf_life_days": result.temperature_baseline_days,
            "handheld_hardness": result.handheld_hardness,
            "mapped_firmness_g_mm2": result.firmness_g_mm2,
            "mapping_formula": "linear: y = 0.14x + 32.714 (x = (y - 32.714) / 0.14)",
            "firmness_adjustment_factor": result.firmness_adjustment_factor,
            "reference_calibration_factor": result.calibration_factor,
            "calibration_method": "2D log-space Gaussian RBF correction over the original formula",
            "calibration_references": "0 C / hardness 70 -> 37 days; 5 C / hardness 70 -> 25 days; 25 C / hardness 60 -> 2 days",
            "temperature_smoothing_controls": "hardness 70: 10 C -> 17 days; 15 C -> 11 days; 20 C -> 7 days; 25 C -> 4 days",
            "temperature_unit": "C",
            "shelf_life_unit": "days",
        },
        assumptions=[
            "The original formula retains the three measured anchors and uses intermediate control points to smooth the temperature curve.",
            "The two-dimensional Gaussian calibration remains positive, continuous, and monotonic over the accepted input grid.",
            "T is storage temperature in Celsius and L is temperature-based shelf life in days.",
            "Handheld hardness is mapped to g*mm^-2 by linear equation: x = (y - 32.714) / 0.14 before prediction.",
            "Low-hardness fruit uses a temperature-sensitive correction table so soft fruit is prioritized for sale.",
            "Prediction assumes clean fruit, intact stems, no visible decay, and stable storage temperature.",
        ],
        recommendations=list(result.recommendations),
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
    regression_days = cubic_polynomial_shelf_life(data.storage_temperature_c)

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a postharvest quality prediction assistant. Return exactly one JSON object. "
                "No markdown, no code fences, no comments, no null output.",
            ),
            (
                "human",
                "请预测樱桃货架期，使用保守的冷链贮藏判断，并用中文填写 decision、assumptions 和 recommendations。\n"
                "Input:\n"
                "storage_temperature_c={temperature_c}\n"
                "handheld_hardness={handheld_hardness}\n"
                "firmness_g_mm2={firmness_g_mm2}\n"
                "polynomial_formula={formula}\n"
                "polynomial_baseline_days={regression_days}\n\n"
                "Return JSON with exactly this shape and compatible value types:\n"
                "{{\n"
                "  \"cultivar\": \"Cherry\",\n"
                "  \"prediction_method\": \"llm_structured\",\n"
                "  \"storage_temperature_c\": {temperature_c},\n"
                "  \"handheld_hardness\": {handheld_hardness},\n"
                "  \"firmness_g_mm2\": {firmness_g_mm2},\n"
                "  \"estimated_shelf_life_days\": 0.0,\n"
                "  \"shelf_life_range_days\": {{\"min\": 0.0, \"max\": 0.0}},\n"
                "  \"risk_level\": \"low\",\n"
                "  \"confidence\": 0.0,\n"
                "  \"decision\": \"中文处理建议\",\n"
                "  \"method_details\": {{\n"
                "    \"llm_provider\": \"siliconflow\",\n"
                "    \"llm_model\": \"{model_name}\",\n"
                "    \"reference_formula\": \"{formula}\",\n"
                "    \"polynomial_baseline_days\": {regression_days},\n"
                "    \"mapping_formula\": \"linear: y = 0.14x + 32.714 (x = (y - 32.714) / 0.14)\"\n"
                "  }},\n"
                "  \"assumptions\": [\"中文假设\"],\n"
                "  \"recommendations\": [\"中文操作建议\"]\n"
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


def _to_structured_dict(prediction: ShelfLifePrediction) -> dict:
    return prediction.model_dump()


def build_shelf_life_chain() -> RunnableSerializable[dict, dict]:
    return (
        RunnableLambda(_normalize_input).with_config(run_name="normalize_input")
        | RunnableLambda(_predict_shelf_life).with_config(run_name="predict_shelf_life")
        | RunnableLambda(_to_structured_dict).with_config(run_name="structured_output")
    )
