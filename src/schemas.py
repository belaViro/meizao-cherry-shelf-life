from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


FirmnessUnit = Literal["N", "kgf"]
PredictionMethod = Literal["polynomial_regression", "llm_structured"]
RiskLevel = Literal["low", "medium", "high"]


class ShelfLifeRequest(BaseModel):
    storage_temperature_c: float = Field(
        ...,
        description="Selected storage temperature in Celsius.",
        examples=[0, 2, 4, 8, 20],
    )
    firmness: float = Field(
        ...,
        gt=0,
        description="Measured fruit firmness.",
        examples=[7.2],
    )
    firmness_unit: FirmnessUnit = Field(
        default="N",
        description="Firmness unit. Supported values are N and kgf.",
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
    firmness_n: float
    original_firmness: float
    original_firmness_unit: FirmnessUnit
    prediction_method: PredictionMethod


class ShelfLifePrediction(BaseModel):
    cultivar: str
    prediction_method: PredictionMethod
    storage_temperature_c: float
    firmness_n: float
    estimated_shelf_life_days: float
    shelf_life_range_days: dict[str, float]
    risk_level: RiskLevel
    confidence: float = Field(ge=0, le=1)
    decision: str
    method_details: dict[str, float | str | None]
    assumptions: list[str]
    recommendations: list[str]
