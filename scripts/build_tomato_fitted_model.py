"""Rebuild fitted trends and validation from observed groups only (stdlib)."""
import csv
import json
import math
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.tomato_fitted_model import fit_curve, curve_value, log_firmness, interpolate, observations_digest
from src.hardness_conversion import map_handheld_to_g_mm2
from src.tomato_predictor import crossing


def build(data):
    points = [dict(p) for p in data['firmness'] if p['metric']=='integer']
    clocks = {str(t):crossing(t,.1)['days'] for t in range(0,26,5)}
    model = fit_curve(points,clocks)
    held_out=[]
    for i,p in enumerate(points):
        train=points[:i]+points[i+1:]
        fold=fit_curve(train,clocks)
        pred=curve_value(fold,p['temperature'],p['day'])['integer_mean']
        means={str(t):sum(q['mean'] for q in train if q['temperature']==t)/sum(q['temperature']==t for q in train) for t in {q['temperature'] for q in train}}
        held_out.append(dict(temperature=p['temperature'],day=p['day'],observed=p['mean'],predicted=pred,
            error=pred-p['mean'],baseline_error=interpolate(means,p['temperature'])-p['mean'],
            log_error=log_firmness(fold,p['temperature'],p['day'])-math.log(map_handheld_to_g_mm2(p['mean']))))
    rmse=lambda values: math.sqrt(sum(v*v for v in values)/len(values))
    model.update(version='tomato-pooled-fit-20261027-v1',age_horizon_days=23,
        formula='log(FT11) = intercept(T) + b*(day/L(T)) - c*(day/L(T))^2; c >= 0',
        source_sha256=data['source_sha256'],training_group_count=len(points),
        validation=dict(training_rmse_integer=rmse([curve_value(model,p['temperature'],p['day'])['integer_mean']-p['mean'] for p in points]),
            loo_rmse_integer=rmse([r['error'] for r in held_out]),loo_log_rmse=rmse([r['log_error'] for r in held_out]),
            baseline_loo_rmse_integer=rmse([r['baseline_error'] for r in held_out]),held_out_groups=held_out,
            method='Leave one temperature/day mean out; refit all hardness coefficients; reference clocks fixed from separate workbook',
            warning='Hardness fit validation is not shelf-life validation; baseline comparison retained even if model is worse.'),
        assumptions=['Equal weight per observed group; imputed values never enter training.',
            'Shared normalized-time shape; 5C intercept anchored by baseline, shape borrowed from other temperatures.',
            'Temperature interpolation uses intercepts and workbook reference clocks; no assumed universal Q10 or chilling onset.',
            'Inverse age prior uniform over 0..23 days; Gaussian log-hardness residual scale from grouped leave-out errors.',
            '10th–90th conditional quantiles are not independently calibrated confidence intervals.',
            'Reference endpoint remains the unvalidated workbook 10% demonstration threshold.'],
        references=[dict(url='https://www.fao.org/4/t0073e/T0073E02.htm',sections='4.9, 4.10.2',
            use='Tomato ripening and low-temperature chilling susceptibility; qualitative limits only, no numeric rate imported.',accessed='2026-10-27')])
    model['validation']['beats_constant_baseline']=model['validation']['loo_rmse_integer']<model['validation']['baseline_loo_rmse_integer']
    return model


def export(model,data,out):
    (out/'tomato_fitted_model.json').write_text(json.dumps(model,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    rows=[]
    observed={(p['temperature'],p['day']):p for p in data['firmness'] if p['metric']=='integer'}
    for t in range(0,26,5):
        last=max(d for temp,d in observed if temp==t)
        for day in range(24):
            p=observed.get((t,day)); fit=curve_value(model,t,day)
            rows.append(dict(temperature_c=t,day=day,observed_integer_mean=p['mean'] if p else None,observed_n=p['n'] if p else 0,
                fitted_integer_mean=fit['integer_mean'],fitted_ft11=fit['firmness_ft11'],
                value_kind='fitted_group_mean_not_individual_measurement',
                support='observed_group_fit' if p else 'borrowed_temperature_shape' if t==5 else 'time_extrapolation' if day>last else 'time_interpolation'))
    with (out/'tomato_fitted_daily.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
    print(json.dumps({k:v for k,v in model['validation'].items() if k!='held_out_groups'},ensure_ascii=False,indent=2))

if __name__=='__main__':
    data=json.loads((ROOT/'data/tomato_observations.json').read_text(encoding='utf8'))
    model=build(data)
    model['observations_sha256']=observations_digest(data)
    model['observations_hash_format']='sha256 canonical JSON sort_keys, ASCII, compact separators'
    export(model,data,ROOT/'data')
