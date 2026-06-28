from __future__ import annotations

from flask import Flask, jsonify, request
from pydantic import ValidationError

from src.shelf_life_chain import POLYNOMIAL_TEMPERATURE_RANGE_C, build_shelf_life_chain


PREDICTION_METHODS = ["polynomial_regression", "llm_structured"]


def create_app() -> Flask:
    app = Flask(__name__)
    shelf_life_chain = build_shelf_life_chain()

    @app.get("/")
    def index():
        return jsonify(
            {
                "name": "Meizao cherry shelf-life predictor",
                "status": "running",
                "endpoints": {
                    "health": "GET /health",
                    "methods": "GET /methods",
                    "predict": "POST /predict",
                },
                "example_request": {
                    "storage_temperature_c": 2,
                    "firmness": 7.5,
                    "firmness_unit": "N",
                    "prediction_method": "polynomial_regression",
                },
            }
        )
    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/methods")
    def methods():
        return jsonify(
            {
                "prediction_methods": PREDICTION_METHODS,
                "default_prediction_method": "polynomial_regression",
                "temperature_range_c": POLYNOMIAL_TEMPERATURE_RANGE_C,
                "llm_structured_provider": "siliconflow",
                "llm_structured_requires": ["SILICONFLOW_API_KEY", "langchain-openai"],
            }
        )

    @app.post("/predict")
    def predict():
        payload = request.get_json(silent=True) or {}

        try:
            result = shelf_life_chain.invoke(payload)
        except ValidationError as exc:
            return jsonify({"error": "validation_error", "details": exc.errors()}), 400
        except ValueError as exc:
            return jsonify({"error": "invalid_input", "message": str(exc)}), 400
        except Exception as exc:
            return (
                jsonify(
                    {
                        "error": "prediction_failed",
                        "message": str(exc),
                        "hint": "For llm_structured, check SiliconFlow network access, API key, model name, and proxy settings.",
                    }
                ),
                502,
            )

        return jsonify(result), 200

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

