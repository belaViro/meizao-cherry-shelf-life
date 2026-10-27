"""Cherry tomato only. No cherry calibration or imputed individual measurements."""
from __future__ import annotations
import json
import math
from functools import lru_cache
from pathlib import Path
from src.hardness_conversion import map_handheld_to_g_mm2, MIN_READING, MAX_READING

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


def predict_tomato_by_day(payload):
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


def _observed_curve(temp, metric):
    return sorted((p for p in load_data()['firmness']
                   if p['temperature'] == temp and p['metric'] == metric),
                  key=lambda p: p['day'])


def _interpolate_curve(points, day):
    for point in points:
        if point['day'] == day:
            return point['mean']
    for a, b in zip(points, points[1:]):
        if a['day'] <= day <= b['day']:
            weight = (day-a['day'])/(b['day']-a['day'])
            return a['mean'] + weight*(b['mean']-a['mean'])
    raise ValueError('硬度曲线不支持该时点，禁止外推。')


def predict_tomato_from_firmness(payload, mapped_mode=False):
    """Invert observed group-mean curves; preserve ambiguity and reject extrapolation.

    This is an exploratory stage-matching model, not a validated individual-fruit
    shelf-life regression. The reference endpoint remains an unvalidated ratio
    threshold, and candidate ranges are not confidence intervals.
    """
    temp = number(payload, 'storage_temperature_c')
    hardness = number(payload, 'firmness', low=0.000001, high=1000000)
    input_hardness = hardness
    if mapped_mode:
        hardness = number(payload, 'firmness', low=MIN_READING, high=MAX_READING)
        if not hardness.is_integer():
            raise ValueError('硬度检测值必须为40–90之间的整数。')
        hardness = map_handheld_to_g_mm2(hardness)
    metric = 'integer' if mapped_mode else payload.get('firmness_metric', 'g_per_mm')
    if metric not in ('g_per_mm', 'integer'):
        raise ValueError('firmness_metric 只能为 g_per_mm 或 integer。')
    if 'storage_days' in payload:
        raise ValueError('硬度预测与天数查询不能同时提交，请只输入温度和硬度。')
    threshold = number(payload, 'failure_threshold', .1, .01, .30)
    lower = max(t for t in TEMPERATURES if t <= temp)
    upper = min(t for t in TEMPERATURES if t >= temp)
    temperatures = sorted({lower, upper})
    curves = [_observed_curve(t, metric) for t in temperatures]
    if mapped_mode:
        # Apply the SAME mapping to input and integer observations. Never relabel
        # the separate g/mm measurements as g/mm² or treat mapped values as measured.
        curves = [[dict(p, mean=map_handheld_to_g_mm2(p['mean']),
                        original_integer_mean=p['mean'], unit='g/mm²',
                        value_kind='mapped_integer_group_mean') for p in curve] for curve in curves]
    anchors = [crossing(t, threshold) for t in temperatures]
    weight = 0 if lower == upper else (temp-lower)/(upper-lower)
    total = None
    if all(a['days'] is not None for a in anchors):
        total = anchors[0]['days'] if lower == upper else (1-weight)*anchors[0]['days']+weight*anchors[1]['days']
    result = dict(
        product='cherry_tomato', product_label='小番茄',
        model_version=load_data()['version']+('-ft11-v2' if mapped_mode else '-firmness-inverse-v1'),
        prediction_method='tomato_firmness_stage_matching',
        storage_temperature_c=temp, firmness=input_hardness, firmness_metric='ft11_mapped' if mapped_mode else metric,
        firmness_unit='handheld' if mapped_mode else ('g/mm' if metric == 'g_per_mm' else '原始整数指标'),
        failure_threshold=threshold, reference_total_days=total,
        estimated_shelf_life_days=None, estimated_remaining_days=None,
        remaining_days_range=None, candidate_stage_intervals=[],
        supported_firmness_range=None, matched_curve=[],
        firmness_sources=[p for curve in curves for p in curve],
        shelf_life_sources=anchors, status='insufficient_data',
        confidence_label='探索性估计 · 未验证',
        decision='该温度缺少连续时间点的实测硬度，无法根据硬度推算剩余货架期。',
        warnings=[
            '以实测组均值曲线匹配贮藏阶段，再由参考总时长扣除阶段天数；不是逐果验证的寿命模型。',
            '参考终点沿用原比例记录的10%演示阈值（API可指定）；判定口径未确认，不是已验证的失效或食品安全标准。',
            '硬度均值有波动，同一硬度可能对应多个阶段；范围仅包含记录支持的解，不是置信区间。',
            '只在已有时间覆盖内插值，不使用补全值作为实测，不外推未记录阶段；范围外不能据此判定新鲜或失效。',
            '非实测温度仅在相邻温度共同覆盖的时间内插值。两种硬度指标互不换算，也不套用樱桃模型。',
            '测量方法、批次和冷害可能影响结果，预测不能保证实际品质或食用安全。'])
    if mapped_mode:
        result.update(handheld_hardness=input_hardness, firmness_ft11=hardness,
                      firmness_g_mm2=hardness, mapped_firmness_unit='g/mm²',
                      mapping_formula='FT11 = (硬度检测值 - 32.714) / 0.14',
                      conversion_status='existing_project_mapping')
        result['warnings'][4] = '输入整数检测值与原始整数硬度组均值均按项目既有线性式转换到FT11映射尺度，再匹配阶段；原g/mm列不混用。'
        result['warnings'].append('FT11数值是项目既有公式的映射值，并非新增仪器实测或已验证的小番茄专用标定。')
    if any(len(curve) < 2 for curve in curves):
        return result
    start = max(curve[0]['day'] for curve in curves)
    end = min(curve[-1]['day'] for curve in curves)
    if end <= start:
        return result
    days = sorted({start, end} | {p['day'] for curve in curves for p in curve if start <= p['day'] <= end})
    points = []
    for day in days:
        values = [_interpolate_curve(curve, day) for curve in curves]
        mean = values[0] if lower == upper else (1-weight)*values[0]+weight*values[1]
        points.append(dict(day=day, mean=mean))
    result['matched_curve'] = points
    result['supported_firmness_range'] = dict(min=min(p['mean'] for p in points), max=max(p['mean'] for p in points))
    candidates = []
    for a, b in zip(points, points[1:]):
        if math.isclose(a['mean'], b['mean'], abs_tol=1e-10, rel_tol=0):
            if math.isclose(hardness, a['mean'], abs_tol=1e-8, rel_tol=0):
                candidates.append([a['day'], b['day']])
        elif min(a['mean'], b['mean'])-1e-8 <= hardness <= max(a['mean'], b['mean'])+1e-8:
            w = max(0, min(1, (hardness-a['mean'])/(b['mean']-a['mean'])))
            day = a['day']+w*(b['day']-a['day'])
            candidates.append([day, day])
    merged = []
    for lo, hi in sorted(candidates):
        if merged and lo <= merged[-1][1]+1e-8:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    result['candidate_stage_intervals'] = [dict(min=lo, max=hi) for lo, hi in merged]
    if not merged:
        result.update(status='firmness_out_of_support', decision='输入硬度超出该温度曲线支持范围，无法估计；请核对硬度单位与测量方法。')
        return result
    if total is None:
        result.update(status='reference_endpoint_unavailable', decision='已匹配硬度阶段，但比例记录未达到参考终点，无法估计剩余货架期。')
        return result
    low = max(0, total-merged[-1][1])
    high = max(0, total-merged[0][0])
    result['remaining_days_range'] = dict(min=round(low,4), max=round(high,4))
    unique = len(merged) == 1 and math.isclose(merged[0][0], merged[0][1], abs_tol=1e-8)
    if unique:
        result.update(status='matched', estimated_remaining_days=round(low,4),
                      estimated_shelf_life_days=round(low,4),
                      decision='根据温度与实测硬度匹配贮藏阶段，得到参考终点下的预计剩余货架期。')
    else:
        result.update(status='ambiguous', decision='同一硬度对应多个可能阶段，仅提供剩余时间范围，不强行给出单一数值。')
    return result


def predict_tomato(payload):
    if 'firmness' in payload:
        unit = payload.get('firmness_unit')
        if unit is not None and unit != 'handheld':
            raise ValueError('网页硬度输入仅支持整数检测值，firmness_unit 应为 handheld。')
        if unit == 'handheld' and 'firmness_metric' in payload:
            raise ValueError('整数检测值自动换算FT11，不可同时指定其他硬度指标。')
        mapped_mode = unit == 'handheld' or 'firmness_metric' not in payload
        return predict_tomato_from_firmness(payload, mapped_mode=mapped_mode)
    if 'storage_days' in payload:
        # Explicit legacy API/CLI compatibility; the web page never uses this mode.
        return predict_tomato_by_day(payload)
    raise ValueError('请输入实测硬度 firmness。')
