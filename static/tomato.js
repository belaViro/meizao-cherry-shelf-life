 'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const form = $('tomatoForm'), temp = $('temperature'), button = $('submitButton');
  let generation = 0;
  const fmt = v => v == null ? '—' : Number(v).toLocaleString('zh-CN', {maximumFractionDigits:2});
  const range = v => v ? `${fmt(v.min)}–${fmt(v.max)}` : '—';
  function sync() {
    document.querySelectorAll('[data-temp]').forEach(b => b.setAttribute('aria-pressed', String(temp.value !== '' && Number(b.dataset.temp) === Number(temp.value))));
    $('inputFirmnessUnit').textContent = $('firmnessMetric').value === 'g_per_mm' ? 'g/mm' : '原始指标';
  }
  function invalidate() {
    generation++; $('result').hidden = true; $('emptyState').hidden = false;
    $('error').hidden = true; $('saveStatus').textContent = '等待计算'; sync();
  }
  form.addEventListener('input', invalidate);
  form.addEventListener('change', invalidate);
  $('firmnessMetric').addEventListener('change', () => { $('firmness').value = ''; invalidate(); });
  document.querySelectorAll('[data-temp]').forEach(b => b.addEventListener('click', () => {temp.value = b.dataset.temp; invalidate();}));
  form.addEventListener('submit', async event => {
    event.preventDefault(); if (!form.reportValidity()) return;
    const current = ++generation;
    button.disabled = true; button.textContent = '计算中…';
    $('result').hidden = true; $('emptyState').hidden = false;
    $('error').hidden = true; $('saveStatus').textContent = '计算中…';
    const payload = {product:'cherry_tomato', storage_temperature_c:Number(temp.value), firmness:Number($('firmness').value), firmness_metric:$('firmnessMetric').value};
    try {
      const response = await fetch('/predict', {method:'POST', headers:{'Content-Type':'application/json', 'X-CSRF-Token':document.querySelector('meta[name="csrf-token"]').content}, body:JSON.stringify(payload)});
      const data = await response.json();
      if (!response.ok) throw Error(data.message || '预测失败，请刷新后重试');
      if (current !== generation) return;
      render(data);
    } catch (error) {
      if (current === generation) { $('error').textContent = error.message; $('error').hidden = false; $('saveStatus').textContent = '计算失败'; }
    } finally { button.disabled = false; button.textContent = '计算小番茄预测'; }
  });
  function render(d) {
    $('emptyState').hidden = true; $('result').hidden = false; $('saveStatus').textContent = '已计算';
    $('remainingDays').textContent = fmt(d.estimated_remaining_days);
    $('remainingRange').textContent = range(d.remaining_days_range);
    $('estimateHint').textContent = d.status === 'ambiguous' ? '存在多解，请查看可能范围' : d.estimated_remaining_days == null ? '当前数据无法估计' : '从当前测量状态起计算';
    $('estimateStatus').textContent = ({matched:'已匹配', ambiguous:'多解', insufficient_data:'数据不足', firmness_out_of_support:'超出范围', reference_endpoint_unavailable:'终点缺失'})[d.status] || '无法估计';
    $('decision').textContent = d.decision;
    $('inputSummary').textContent = `本次输入：${fmt(d.storage_temperature_c)}℃；硬度 ${fmt(d.firmness)} ${d.firmness_unit}。`;
    $('stageSummary').textContent = '匹配阶段（从实验第0天计）：' + (d.candidate_stage_intervals.map(v => `${range(v)}天`).join('；') || '无支持解');
    $('supportSummary').textContent = `曲线支持的硬度范围：${range(d.supported_firmness_range)} ${d.firmness_unit}；不外推未记录阶段。`;
    $('referenceSummary').textContent = `参考终点总时长：${fmt(d.reference_total_days)}天；按原比例记录的${fmt(d.failure_threshold*100)}%演示阈值计算，实验判定口径尚未确认。剩余时间 = max(参考总时长 − 匹配阶段天数, 0)。`;
    $('firmnessSources').textContent = '实测组均值来源：' + d.firmness_sources.map(p => `${p.temperature}℃ / ${p.day}天 / ${fmt(p.mean)} / n=${p.n}`).join('；');
    $('warnings').replaceChildren(...d.warnings.map(text => {const li = document.createElement('li'); li.textContent = text; return li;}));
    $('modelVersion').textContent = `模型版本：${d.model_version} · 不写入樱桃历史记录`;
  }
  sync();
})();
