"""Independent CLI for cherry-tomato exploratory prediction."""
import argparse
import json
import sys
from src.tomato_predictor import predict_tomato


def main():
    # Emit portable UTF-8 JSON even when Windows redirects stdout with a GBK locale.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description='小番茄温度与实测硬度预测剩余货架期（探索性）')
    parser.add_argument('temperature',type=float)
    parser.add_argument('storage_days',type=float,nargs='?',help='兼容旧版天数查询；不可与 --firmness 同用')
    parser.add_argument('--firmness',type=float,help='实测硬度，与 --metric 指标一致')
    parser.add_argument('--threshold-percent',type=float,default=10)
    parser.add_argument('--metric',choices=['handheld','g_per_mm','integer'],default='handheld')
    args=parser.parse_args()
    if (args.firmness is None) == (args.storage_days is None):
        parser.error('请指定 --firmness（推荐），或旧版 storage_days，两者不可同时使用。')
    payload=dict(storage_temperature_c=args.temperature, failure_threshold=args.threshold_percent/100, firmness_metric=args.metric)
    payload.update({'firmness':args.firmness} if args.firmness is not None else {'storage_days':args.storage_days})
    if args.metric == 'handheld':
        payload.pop('firmness_metric')
        if args.firmness is not None:
            payload['firmness_unit'] = 'handheld'
    try:
        result=predict_tomato(payload)
    except ValueError as exc:parser.error(str(exc))
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
