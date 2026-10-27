"""Cherry tomato only. No cherry calibration or imputed individual measurements."""
from __future__ import annotations
import json
import math
from functools import lru_cache
from pathlib import Path

TEMPERATURES=(0,5,10,15,20,25)

@lru_cache(maxsize=1)
def load_data():
    return json.loads((Path(__file__).resolve().parents[1]/'data/tomato_observations.json').read_text(encoding='utf-8'))


def number(payload,key,default=None,low=0,high=25):
    value=payload.get(key,default)
    if isinstance(value,bool) or value is None or isinstance(value,(dict,list)):
        raise ValueError(f'{key} 必须是有限数值。')
    try:value=float(value)
    except (ValueError,TypeError):raise ValueError(f'{key} 必须是有限数值。')
    if not math.isfinite(value) or not low<=value<=high:
        raise ValueError(f'{key} 必须在 {low}–{high} 之间。')
    return value


def crossing(temp,threshold):
    points=sorted((r for r in load_data()['ratios'] if r['temperature']==temp),key=lambda r:r['day'])
    for previous,current in zip(points,points[1:]):
        if previous['ratio']<threshold<=current['ratio']:
            w=(threshold-previous['ratio'])/(current['ratio']-previous['ratio'])
            return dict(days=previous['day']+w*(current['day']-previous['day']),
                        temperature=temp,status='threshold_interpolation',bracket=[previous,current])
    return dict(days=None,temperature=temp,status='not_observed',last_observation=points[-1])


def firmness_at(temp,day,metric):
    data=load_data()
    points=sorted((r for r in data['firmness'] if r['temperature']==temp and r['metric']==metric),key=lambda r:r['day'])
    for p in points:
        if p['day']==day:
            return dict(mean=p['mean'],status='observed_group_mean',method='原始实测组均值',observed_n=p['n'],sources=[p])
    left=[p for p in points if p['day']<day];right=[p for p in points if p['day']>day]
    if left and right:
        a,b=left[-1],right[0];w=(day-a['day'])/(b['day']-a['day'])
        return dict(mean=a['mean']*(1-w)+b['mean']*w,status='time_interpolation',method='同温度相邻实测均值线性插值',observed_n=0,sources=[a,b])
    if temp==5 and day<=14:
        h0=points[0]['mean'];k,c=data['scenario_coefficients'][metric]
        ten=sorted((r for r in data['firmness'] if r['temperature']==10 and r['metric']==metric),key=lambda r:r['day'])
        local_k=max(0,math.log(ten[0]['mean']/ten[-1]['mean'])/3)
        def estimate(q,rate,c_factor):
            return h0*math.exp(-rate*day*q**(-.5)-c_factor*c*.5*max(day-7,0))
        values=[estimate(q,rate,cf) for q in (1.5,2,3) for rate in (0,k,2*k,local_k) for cf in (0,1,2)]
        return dict(mean=estimate(2,k,1),status='assumed_scenario',method='仅5℃基线锚定的软化假设情景（未经验证）',observed_n=0,
                    scenario_range={'min':min(values),'max':max(values)},sources=points,
                    caveat='Q10=2、7天低温拐点仅为假设。全局模型验证较差；范围不是置信区间。')
    if temp==10 and day<=9 and left:
        a,b=points[0],points[-1];k=max(0,math.log(a['mean']/b['mean'])/(b['day']-a['day']))
        value=b['mean']*math.exp(-k*(day-b['day']))
        return dict(mean=value,status='extrapolation_scenario',method='0/3d局部指数速率，3d锚定外推',observed_n=0,sources=points,
                    scenario_range={'min':b['mean']*math.exp(-2*k*(day-b['day'])),'max':b['mean']},
                    caveat='只有两个实测时间点；未来速率0–2倍范围不是置信区间。')
    return dict(mean=None,status='unsupported',method='超出支持时间范围，不外推',observed_n=0,sources=[])


def predict_tomato(payload):
    temp=number(payload,'storage_temperature_c')
    day=number(payload,'storage_days',0,0,23)
    threshold=number(payload,'failure_threshold',.1,.01,.30)
    metric=payload.get('firmness_metric','g_per_mm')
    if metric not in ('g_per_mm','integer'):raise ValueError('firmness_metric 只能为 g_per_mm 或 integer。')
    lower=max(t for t in TEMPERATURES if t<=temp);upper=min(t for t in TEMPERATURES if t>=temp)
    anchors=[crossing(t,threshold) for t in sorted({lower,upper})]
    if all(a['days'] is not None for a in anchors):
        total=anchors[0]['days'] if lower==upper else anchors[0]['days']+(anchors[1]['days']-anchors[0]['days'])*(temp-lower)/(upper-lower)
        remaining=max(0,total-day)
        status='threshold_interpolation' if lower==upper else 'temperature_interpolation'
    else:total=remaining=None;status='threshold_not_observed'
    if lower==upper:firmness=firmness_at(temp,day,metric)
    else:firmness=dict(mean=None,status='unsupported_temperature',method='硬度仅支持六个实测温度；不跨温度制造读数',observed_n=0,sources=[])
    firmness['metric']=metric;firmness['unit']='g/mm' if metric=='g_per_mm' else '原始整数指标（组均值可含小数）'
    series=[dict(temperature=t,points=[dict(day=r['day'],ratio=r['ratio']) for r in load_data()['ratios'] if r['temperature']==t]) for t in sorted({lower,upper})]
    return dict(product='cherry_tomato',product_label='小番茄',model_version=load_data()['version'],
        prediction_method='tomato_observed_threshold',storage_temperature_c=temp,storage_days=day,failure_threshold=threshold,
        estimated_shelf_life_days=None if total is None else round(total,4),
        estimated_remaining_days=None if remaining is None else round(remaining,4),
        status=status,confidence_label='探索性估计，未经独立验证',shelf_life_sources=anchors,firmness=firmness,ratio_series=series,
        decision='记录范围内未观察到阈值跨越，无法给出货架期。' if total is None else ('已达到设定的比例阈值；请复核实际品质。' if remaining==0 else '按设定阈值估计剩余时间；同时检查实际品质。'),
        warnings=[load_data()['provenance']['ratio_interpretation'],
          '10%是可调整的演示阈值，不是已经确认的该批实验失效标准。',
          '总时长从实验第0天计算；剩余时间=总时长−已贮藏天数，不根据硬度反推果龄。',
          '工作簿空白不作为0；取首次跨阈值，原有波动保留。比例和硬度未证明逐果配对，不相互换算。',
          '低温可能产生冷害，结果不能证明0℃优于5℃或保证食用安全。'])
