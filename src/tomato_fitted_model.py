"""Pooled empirical tomato firmness curves; no synthetic training observations."""
from __future__ import annotations
import math
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from .hardness_conversion import map_handheld_to_g_mm2, INTERCEPT, SLOPE


def interpolate(values, temperature):
    keys = sorted(float(t) for t in values)
    lo = max((t for t in keys if t <= temperature), default=keys[0])
    hi = min((t for t in keys if t >= temperature), default=keys[-1])
    a, b = values[str(int(lo))], values[str(int(hi))]
    return a if lo == hi else a + (b-a)*(temperature-lo)/(hi-lo)


def fit_curve(points, clocks):
    """Equal weight per observed temperature/day group, not per imputed fruit.

    log(FT11) = intercept[T] + b*x - c*x*x, x = day / reference_clock[T].
    c >= 0 permits an initial rise followed by softening; neither the rise nor
    a chilling-injury onset is assumed to be a verified biological mechanism.
    """
    groups = {}
    for p in points:
        x = p['day']/clocks[str(p['temperature'])]
        groups.setdefault(p['temperature'], []).append((x, -x*x, math.log(map_handheld_to_g_mm2(p['mean']))))
    means = {t: tuple(sum(row[j] for row in rows)/len(rows) for j in range(3)) for t, rows in groups.items()}
    centered = [tuple(row[j]-means[t][j] for j in range(3)) for t, rows in groups.items() for row in rows]
    xx = sum(a*a for a,b,y in centered); zz = sum(b*b for a,b,y in centered)
    xz = sum(a*b for a,b,y in centered); xy = sum(a*y for a,b,y in centered); zy = sum(b*y for a,b,y in centered)
    det = xx*zz-xz*xz
    if det > 1e-12:
        b, c = (xy*zz-zy*xz)/det, (zy*xx-xy*xz)/det
    else:
        b, c = (xy/xx if xx > 1e-12 else 0), 0
    if c < 0:
        b, c = (xy/xx if xx > 1e-12 else 0), 0
    return dict(intercepts={str(t): y-b*x-c*z for t,(x,z,y) in means.items()}, linear=b, curvature=c, reference_clocks=clocks)


def log_firmness(model, temperature, day):
    x = day/interpolate(model['reference_clocks'], temperature)
    return interpolate(model['intercepts'], temperature)+model['linear']*x-model['curvature']*x*x


def curve_value(model, temperature, day):
    mapped = math.exp(log_firmness(model, temperature, day))
    return dict(firmness_ft11=mapped, integer_mean=INTERCEPT+SLOPE*mapped)


def infer_stage(model, temperature, mapped_hardness, total, sigma=None, horizon=None):
    """Conditional age distribution on a declared uniform-age modelling prior.

    Uses all plausible stages, not a fabricated unique solution. Equal-spaced
    trapezoidal quadrature; log-sum-exp prevents extreme inputs underflowing.
    The interval is conditional on the model, NOT validated coverage.
    """
    sigma = model['validation']['loo_log_rmse'] if sigma is None else sigma
    sigma = max(sigma, 1e-6)
    horizon = model['age_horizon_days'] if horizon is None else horizon
    count = 920
    days = [horizon*i/count for i in range(count+1)]
    scores = [-.5*((math.log(mapped_hardness)-log_firmness(model,temperature,d))/sigma)**2 for d in days]
    maximum = max(scores)
    weights = [math.exp(s-maximum)*(.5 if i in (0,count) else 1) for i,s in enumerate(scores)]
    norm = sum(weights)
    weights = [w/norm for w in weights]
    remaining = [max(0,total-d) for d in days]
    def quantile(q):
        cumulative = 0
        for value,weight in sorted(zip(remaining,weights)):
            cumulative += weight
            if cumulative >= q: return value
        return max(remaining)
    return dict(remaining_mean=sum(r*w for r,w in zip(remaining,weights)),
                remaining_range=dict(min=quantile(.1),max=quantile(.9)),
                stage_mean=sum(d*w for d,w in zip(days,weights)),
                expired_weight=sum(w for r,w in zip(remaining,weights) if r == 0))


def fitted_prediction(result):
    """Replace strict observed-knot inverse for the default integer/FT11 mode."""
    model = load_fitted_model()
    temp, total = result['storage_temperature_c'], result['reference_total_days']
    result.update(model_version=model['version'],prediction_method='tomato_pooled_fitted_inference',
        confidence_label='拟合估计 · 低可信度',
        estimation_basis='observed_groups_plus_pooled_fitted_trends',
        model_validation={k:v for k,v in model['validation'].items() if k!='held_out_groups'},
        interval_kind='conditional_model_10_90_percent_not_validated_confidence',
        model_assumptions=model['assumptions'],candidate_stage_intervals=[],
        warnings=[
            '拟合曲线仅使用原始整数硬度组均值训练；补全值不是新增实测重复。',
            '5℃仅有基线，后续形状借用其他温度的共同趋势；尚未独立验证。',
            '硬度先升后降且有波动，采用所有可能阶段的模型加权平均，不冒充唯一匹配阶段。',
            '参考终点仍为工作簿10%演示阈值（API可另设），不是已确认失效标准或食品安全期限。',
            '留组检验尚未优于常数基线；输出为低可信度探索估计，不能声称精确预测。',
            '范围为指定模型及0–23天均匀阶段先验下的10%–90%分位，非经验证置信区间。',
            'FT11沿用项目既有映射，不代表小番茄专用仪器标定；独立g/mm列未混用。',
            '0/5℃可能存在冷害；未拟合未经验证的冷害起始日或通用Q10。'])
    result['matched_curve'] = [dict(day=d,mean=curve_value(model,temp,d)['firmness_ft11'],
        fitted_integer_mean=curve_value(model,temp,d)['integer_mean'],observed_n=0,value_kind='fitted_group_mean') for d in range(24)]
    means = [p['mean'] for p in result['matched_curve']]
    result['supported_firmness_range'] = None
    result['fitted_firmness_range'] = dict(min=min(means), max=max(means))
    if total is None:
        result.update(status='reference_endpoint_unavailable',decision='硬度拟合曲线已生成，但比例记录未达到指定终点，无法计算剩余时间。')
        return result
    inference = infer_stage(model,temp,result['firmness_ft11'],total)
    alternative = infer_stage(model,temp,result['firmness_ft11'],total,horizon=min(total,model['age_horizon_days']))
    result['age_prior_sensitivity'] = dict(uniform_0_23_days_remaining=round(inference['remaining_mean'],4),
        uniform_0_reference_days_remaining=round(alternative['remaining_mean'],4))
    remaining=round(inference['remaining_mean'],4)
    result.update(estimated_remaining_days=remaining,estimated_shelf_life_days=remaining,
        remaining_days_range={k:round(v,4) for k,v in inference['remaining_range'].items()},
        estimated_stage_days=round(inference['stage_mean'],4),
        conditional_endpoint_passed_weight=round(inference['expired_weight'],4),
        status='fitted_estimate',
        decision='已结合各温度实测硬度与工作簿参考时长拟合缺失趋势，按可能阶段加权估计剩余时间；留出检验仍较弱，结果为低可信度模型估计。')
    if temp == 5:
        result['decision'] = '5℃以实测初始硬度为锚点，借用其他温度的共同趋势补全后续曲线；当前天数为低可信度拟合估计。'
    mapped=result['firmness_ft11']
    distance = min(abs(math.log(mapped)-log_firmness(model,temp,23*i/920)) for i in range(921))
    result['nearest_fit_residual_sigma'] = round(distance/model['validation']['loo_log_rmse'],4)
    if distance > 2*model['validation']['loo_log_rmse']:
        result.update(status='fitted_extrapolation',decision='检测值偏离拟合曲线较远，已返回低可信度外推估计；请勿把该数值当作实测支持的确定期限。')
    return result


def observations_digest(data):
    """Canonical JSON hash, stable across Windows/Linux line endings."""
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=True,separators=(",",":")).encode("utf8")).hexdigest()


@lru_cache(maxsize=1)
def load_fitted_model():
    folder=Path(__file__).resolve().parents[1]/'data'
    model=json.loads((folder/'tomato_fitted_model.json').read_text(encoding='utf-8'))
    if observations_digest(json.loads((folder/'tomato_observations.json').read_text(encoding='utf8')))!=model['observations_sha256']:
        raise ValueError('硬度数据已更新，请先重建拟合模型。')
    return model
