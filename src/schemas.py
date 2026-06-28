from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


FirmnessUnit = Literal["handheld"]
PredictionMethod = Literal["polynomial_regression", "llm_structured"]
RiskLevel = Literal["low", "medium", "high"]


class ShelfLifeRequest(BaseModel):
    storage_temperature_c: float = Field(
        ...,
        description="Selected storage temperature in Celsius.",
        examples=[0, 5, 10, 15, 20, 25],
    )
    firmness: float = Field(
        ...,
        ge=50,
        le=90,
        description="Handheld hardness meter reading. Accepted range: 50-90.",
        examples=[70],
    )
    firmness_unit: FirmnessUnit = Field(
        default="handheld",
        description="Input hardness unit. Only handheld meter reading is accepted.",
    )
    prediction_method: PredictionMethod = Field(
        default="polynomial_regression",
        description="Prediction method: polynomial_regression or llm_structured.",
    )

    @field_validator("storage_temperature_c")
    @classmethod
    def round_temperature(cls, value: float) -> float:
        return float(value)


class NormalizedShelfLifeInput(BaseModel):
    cultivar: str = "Meizao cherry"
    storage_temperature_c: float
    handheld_hardness: float
    firmness_g_mm2: float
    original_firmness: float
    original_firmness_unit: FirmnessUnit
    prediction_method: PredictionMethod


class ShelfLifePrediction(BaseModel):
    cultivar: str
    prediction_method: PredictionMethod
    storage_temperature_c: float
    handheld_hardness: float
    firmness_g_mm2: float
    estimated_shelf_life_days: float
    shelf_life_range_days: dict[str, float]
    risk_level: RiskLevel
    confidence: float = Field(ge=0, le=1)
    decision: str
    method_details: dict[str, float | str | None]
    assumptions: list[str]
    recommendations: list[str]
