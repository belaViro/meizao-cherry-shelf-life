from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from src.core_predictor import ShelfLifeResult, predict_shelf_life


RISK_LABELS = {
    "low": "低",
    "medium": "中",
    "high": "高",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="根据储藏温度和手持硬度预测樱桃货架期。",
    )
    parser.add_argument(
        "temperature",
        type=float,
        nargs="?",
        help="储藏温度（0-25 ℃）",
    )
    parser.add_argument(
        "hardness",
        type=float,
        nargs="?",
        help="手持硬度计读数（60-90）",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="显示基础多项式、硬度系数和校准系数",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式输出",
    )
    return parser


def read_interactive_input() -> tuple[float, float]:
    print("樱桃货架期预测终端程序")
    print("输入范围：储藏温度 0-25 ℃，手持硬度 60-90。\n")
    temperature = float(input("请输入储藏温度（℃）：").strip())
    hardness = float(input("请输入手持硬度计读数：").strip())
    return temperature, hardness


def print_result(result: ShelfLifeResult, show_details: bool = False) -> None:
    print("\n========== 预测结果 ==========")
    print(f"储藏温度：{result.storage_temperature_c:g} ℃")
    print(f"手持硬度：{result.handheld_hardness:g}")
    print(f"换算硬度：{result.firmness_g_mm2:g} g/mm^2")
    print(f"预计货架期：{result.estimated_shelf_life_days:.1f} 天")
    print(f"预测范围：{result.range_min_days:.1f}-{result.range_max_days:.1f} 天")
    print(f"风险等级：{RISK_LABELS[result.risk_level]}")
    print(f"置信度：{result.confidence:.0%}")
    print(f"处理建议：{result.decision}")

    if show_details:
        print("\n---------- 计算明细 ----------")
        print(f"温度多项式基础值：{result.temperature_baseline_days:.2f} 天")
        print(f"硬度修正系数：{result.firmness_adjustment_factor:.3f}")
        print(f"二维校准系数：{result.calibration_factor:.3f}")

    print("\n---------- 操作建议 ----------")
    for index, recommendation in enumerate(result.recommendations, start=1):
        print(f"{index}. {recommendation}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if (args.temperature is None) != (args.hardness is None):
        parser.error("请同时提供温度和硬度，或者不提供参数进入交互输入。")

    try:
        if args.temperature is None:
            temperature, hardness = read_interactive_input()
        else:
            temperature, hardness = args.temperature, args.hardness
        result = predict_shelf_life(temperature, hardness)
    except (ValueError, EOFError) as exc:
        parser.exit(2, f"输入错误：{exc}\n")

    if args.json:
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    else:
        print_result(result, show_details=args.details)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
