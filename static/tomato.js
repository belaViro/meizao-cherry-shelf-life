 'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const form = $('tomatoForm'), temp = $('temperature'), button = $('submitButton');
  let generation = 0;
  const fmt = v => v == null ? '—' : Number(v).toLocaleString('zh-CN', {maximumFractionDigits:2});
  const range = v => v ? `${fmt(v.min)}–${fmt(v.max)}` : '—';
  function sync() {
    document.querySelectorAll('[data-temp]').forEach(b => b.setAttribute('aria-pressed', String(temp.value !== '' && Number(b.dataset.temp) === Number(temp.value))));
    const input = $('firmness'), raw = Number(input.value), mapped = $('mappedFirmness');
    const valid = input.value.trim() !== '' && Number.isInteger(raw) && raw >= Number(input.min) && raw <= Number(input.max);
    mapped.value = valid ? `FT11：${((raw - Number(mapped.dataset.intercept)) / Number(mapped.dataset.slope)).toFixed(1)} g·mm⁻²` : '—';
  }
  function invalidate() {
    generation++; $('result').hidden = true; $('emptyState').hidden = false;
    $('error').hidden = true; $('saveStatus').textContent = '等待计算'; sync();
  }
  form.addEventListener('input', invalidate);
  form.addEventListener('change', invalidate);
  document.querySelectorAll('[data-temp]').forEach(b => b.addEventListener('click', () => {temp.value = b.dataset.temp; invalidate();}));
  form.addEventListener('submit', async event => {
    event.preventDefault(); if (!form.reportValidity()) return;
    const current = ++generation;
    button.disabled = true; button.textContent = '计算中…';
    $('result').hidden = true; $('emptyState').hidden = false;
    $('error').hidden = true; $('saveStatus').textContent = '计算中…';
    const payload = {product:'cherry_tomato', storage_temperature_c:Number(temp.value), firmness:Number($('firmness').value), firmness_unit:'handheld'};
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
    $('estimateHint').textContent = d.status === 'ambiguous' ? '存在多解，请查看可能范围' : d.estimated_remaining_days == null ? '当前数据无法估计' : '从当前测量状态起计算（拟合估计）';
    $('estimateStatus').textContent = ({fitted_estimate:'拟合估计', fitted_extrapolation:'低可信外推', matched:'已匹配', ambiguous:'多解', insufficient_data:'数据不足', firmness_out_of_support:'超出范围', reference_endpoint_unavailable:'终点缺失'})[d.status] || '无法估计';
    $('decision').textContent = d.decision;
    $('mappedFirmness').value = `FT11：${Number(d.firmness_ft11).toFixed(1)} g·mm⁻²`;
    $('modelVersion').textContent = `模型版本：${d.model_version} · 不写入樱桃历史记录`;
  }
  sync();
})();
