'use strict';
(() => {
  const $ = (id) => document.getElementById(id);
  const form = $('tomatoForm'), temp = $('temperature'), button = $('submitButton');
  const labels = {observed_group_mean:'实测组均值',time_interpolation:'时间插值估计 · 非实测',assumed_scenario:'假设情景 · 可信度很低',extrapolation_scenario:'外推情景 · 可信度很低',unsupported:'无支持数据',unsupported_temperature:'非实测温度，硬度不估计',threshold_interpolation:'同温度首次阈值跨越插值',temperature_interpolation:'相邻温度阈值时长插值',threshold_not_observed:'记录内未观测到阈值跨越'};
  let latest = null, generation = 0;
  const fmt = v => v === null || v === undefined ? '无法估计' : Number(v).toLocaleString('zh-CN',{maximumFractionDigits:2});
  function sync() { document.querySelectorAll('[data-temp]').forEach(b=>b.setAttribute('aria-pressed',String(temp.value!=='' && Number(b.dataset.temp)===Number(temp.value)))); }
  function invalidate() { generation++; latest=null; $('result').hidden=true; $('emptyState').hidden=false; $('error').hidden=true; $('saveStatus').textContent='等待计算'; }
  form.addEventListener('input',()=>{sync();invalidate();});
  form.addEventListener('change',invalidate);
  document.querySelectorAll('[data-temp]').forEach(b=>b.addEventListener('click',()=>{temp.value=b.dataset.temp;sync();invalidate();}));
  form.addEventListener('submit', async event => {
    event.preventDefault(); const requestGeneration=++generation;
    button.disabled=true;button.textContent='计算中…';$('saveStatus').textContent='计算中…';$('error').hidden=true;
    const payload={product:'cherry_tomato',storage_temperature_c:Number(temp.value),storage_days:Number($('storageDays').value),firmness_metric:$('firmnessMetric').value};
    try {
      const response=await fetch('/predict',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':document.querySelector('meta[name="csrf-token"]').content},body:JSON.stringify(payload)});
      const data=await response.json();if(!response.ok)throw Error(data.message||'预测失败，请刷新后重试');
      if(requestGeneration!==generation)return;
      latest=data;render(data);
    } catch(error) {if(requestGeneration===generation){$('saveStatus').textContent='计算失败';$('error').textContent=error.message;$('error').hidden=false;}}
    finally {button.disabled=false;button.textContent='计算小番茄预测';}
  });
  function render(d) {
    $('emptyState').hidden=true;$('result').hidden=false;$('saveStatus').textContent='已计算 · 未保存历史';
    $('totalDays').textContent=fmt(d.estimated_shelf_life_days);$('remainingDays').textContent=fmt(d.estimated_remaining_days);
    $('firmnessValue').textContent=fmt(d.firmness.mean);$('firmnessUnit').textContent=d.firmness.unit;
    $('decision').textContent=d.decision;
    $('shelfStatus').textContent=`货架期依据：${labels[d.status]}；${d.confidence_label}。`;
    $('firmnessStatus').textContent=`硬度：${labels[d.firmness.status]}。${d.firmness.method}；目标时点实测 n=${d.firmness.observed_n}。`;
    $('scenarioRange').textContent=d.firmness.scenario_range?`情景敏感性范围：${fmt(d.firmness.scenario_range.min)}–${fmt(d.firmness.scenario_range.max)}（非95%置信区间）。${d.firmness.caveat}`:'未提供统计置信区间；不得将估计值当成实测重复。';
    $('firmnessSources').textContent='硬度实测来源：'+(d.firmness.sources.map(s=>`${s.temperature}℃ / ${s.day}天 / 均值${fmt(s.mean)} / n=${s.n}`).join('；')||'无支持来源');
    $('thresholdSources').textContent=d.shelf_life_sources.map(s=>s.days===null?`${s.temperature}℃：截至${s.last_observation.day}天未达到阈值，不作外推。`:`${s.temperature}℃：${s.bracket[0].day}–${s.bracket[1].day}天之间首次跨越${fmt(d.failure_threshold*100)}%，插值得${fmt(s.days)}天。`).join(' ');
    $('warnings').replaceChildren(...d.warnings.map(text=>{const li=document.createElement('li');li.textContent=text;return li;}));
    $('ratioRows').replaceChildren(...d.ratio_series.flatMap(s=>s.points.map(p=>{const tr=document.createElement('tr');[s.temperature,p.day,fmt(p.ratio*100)].forEach(v=>{const td=document.createElement('td');td.textContent=v;tr.append(td);});return tr;})));
    $('modelVersion').textContent=`模型版本：${d.model_version} · 结果不写入樱桃历史记录`;
    draw(d);
  }
  function draw(d) {
    const canvas=$('ratioChart'),ctx=canvas.getContext('2d'),w=canvas.clientWidth,h=240,scale=window.devicePixelRatio||1;
    canvas.width=w*scale;canvas.height=h*scale;ctx.scale(scale,scale);ctx.clearRect(0,0,w,h);
    const left=42,right=w-18,top=22,bottom=205,all=d.ratio_series.flatMap(s=>s.points);
    const maxDay=Math.max(1,...all.map(p=>p.day)),maxRatio=Math.max(.12,d.failure_threshold*1.15,...all.map(p=>p.ratio*1.15));
    const x=v=>left+v/maxDay*(right-left),y=v=>bottom-v/maxRatio*(bottom-top);
    ctx.font='11px sans-serif';ctx.strokeStyle='#e5e8e6';ctx.fillStyle='#666';
    for(let i=0;i<=4;i++){const v=maxRatio*i/4;ctx.beginPath();ctx.moveTo(left,y(v));ctx.lineTo(right,y(v));ctx.stroke();ctx.fillText(fmt(v*100)+'%',2,y(v)+4);}
    for(let i=0;i<=4;i++){const v=maxDay*i/4;ctx.fillText(fmt(v),x(v)-6,bottom+18);}ctx.fillText('天',right-4,bottom+32);
    ctx.setLineDash([5,4]);ctx.strokeStyle='#b07c2a';ctx.beginPath();ctx.moveTo(left,y(d.failure_threshold));ctx.lineTo(right,y(d.failure_threshold));ctx.stroke();ctx.setLineDash([]);
    const colors=['#176b5b','#496bb5'];d.ratio_series.forEach((s,i)=>{ctx.strokeStyle=colors[i];ctx.fillStyle=colors[i];ctx.beginPath();s.points.forEach((p,j)=>j?ctx.lineTo(x(p.day),y(p.ratio)):ctx.moveTo(x(p.day),y(p.ratio)));ctx.stroke();s.points.forEach(p=>{ctx.beginPath();ctx.arc(x(p.day),y(p.ratio),3,0,Math.PI*2);ctx.fill();});ctx.fillText(s.temperature+'℃ 实测',left+i*105,13);});
  }
  window.addEventListener('resize',()=>{if(latest)draw(latest);});
  $('downloadResult').addEventListener('click',()=>{if(!latest)return;const url=URL.createObjectURL(new Blob([JSON.stringify(latest,null,2)],{type:'application/json;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='小番茄预测_含来源与估计标记.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  sync();
})();
