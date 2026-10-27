"""Independent CLI for cherry-tomato exploratory prediction."""
import argparse
import json
from src.tomato_predictor import predict_tomato


def main():
    parser=argparse.ArgumentParser(description='小番茄阈值时长与硬度趋势（探索性，非食品安全期限）')
    parser.add_argument('temperature',type=float)
    parser.add_argument('storage_days',type=float)
    parser.add_argument('--threshold-percent',type=float,default=10)
    parser.add_argument('--metric',choices=['g_per_mm','integer'],default='g_per_mm')
    args=parser.parse_args()
    try:
        result=predict_tomato(dict(storage_temperature_c=args.temperature,storage_days=args.storage_days,
            failure_threshold=args.threshold_percent/100,firmness_metric=args.metric))
    except ValueError as exc:parser.error(str(exc))
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
