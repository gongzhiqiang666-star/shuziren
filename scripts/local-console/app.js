'use strict';
const $ = id => document.getElementById(id);
const productFactsText = product => product?.extra?.product_facts === undefined ? '' : JSON.stringify(product.extra.product_facts, null, 2);
let token = '';
function clearChecks() { $('checks').replaceChildren(); $('scope').textContent = '尚未检查当前资源。'; }
$('runtime-root').addEventListener('input', clearChecks);
function config() { return {version: 1, runtime_root: $('runtime-root').value, port: Number($('port').value)}; }
async function request(path, value) {
  const response = await fetch(path, value === undefined ? {cache:'no-store'} : {
    method:'POST', headers:{'Content-Type':'application/json','X-Console-Token':token}, body:JSON.stringify(value)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '请求失败');
  return result;
}
async function action(work) {
  $('error').textContent = ''; $('message').textContent = '';
  document.querySelectorAll('button').forEach(b => b.disabled = true);
  try { await work(); } catch(error) { $('error').textContent = error.message || '无法连接本地服务'; }
  finally { document.querySelectorAll('button').forEach(b => b.disabled = false); renderRecordingButtons(); renderTTSButtons(); renderAvatarVideoButtons(); renderVideoButtons(); renderLiveButtons(); renderTaobao(); }
}
async function load() {
  clearChecks();
  const session = await request('/api/session'); token = session.token;
  const engineName = {indextts: 'IndexTTS', zipvoice: 'ZipVoice', omnivoice: 'OmniVoice'}[session.tts_engine];
  $('tts-language-field').hidden = session.tts_engine !== 'omnivoice';
  if ($('tts-language-field').hidden) $('tts-language').value = 'zh-CN';
  $('tts-engine').textContent = engineName ? '当前语音引擎：' + engineName : '';
  let state;
  try { state = await request('/api/state'); }
  catch(error) { $('live-status').textContent = '状态读取失败'; throw error; }
  $('runtime-root').value = state.config.runtime_root; $('port').value = state.config.port;
  $('live-status').textContent = state.live_status;
  $('data-directory').textContent = '配置目录：' + state.data_directory;
}
$('settings').addEventListener('submit', event => {event.preventDefault(); action(async () => {
  const result = await request('/api/config', config()); await load(); $('message').textContent = result.message;
});});
$('preflight').addEventListener('click', () => action(async () => {
  const result = await request('/api/preflight', config());
  $('scope').textContent = result.ready ? '必需文件均存在。尚未验证完整性、GPU、模型或直播。' : '资源不完整，请检查下列路径。';
  $('checks').replaceChildren(...result.checks.map(check => {
    const item = document.createElement('li'); item.textContent = (check.present ? '✓ ' : '缺失：') + check.path; return item;
  }));
}));
$('reload').addEventListener('click', () => action(load));
$('shutdown').addEventListener('click', () => action(async () => {
  await request('/api/shutdown', {confirm:true});
  consoleClosed = true; clearTimeout(taskTimer);
  recorder.discard();
  clearTimeout(ttsTimer);clearTTSPreview();$('tts-panel').hidden=true;
  clearTimeout(renderTimer);clearRenderPreview();$('render-panel').hidden=true;
  clearTimeout(avatarVideoTimer);$('avatar-preview').removeAttribute('src');$('avatar-panel').hidden=true;
  $('live-status').textContent = '控制台已退出';
  $('message').textContent = '本地服务已收到退出请求，可以关闭本页。';
  $('settings').hidden = true; $('shutdown').hidden = true;
  $('products-panel').hidden = true;
  $('voice-preview').pause(); $('voice-preview').removeAttribute('src'); $('voice-preview').load(); $('voice-panel').hidden=true;
}));
let currentProduct = null;
let savedProducts = [];
let currentScriptId=null;
let ttsTimer=null,ttsState=null,ttsPreviewTask=null;
let renderState=null,renderTimer=null,renderPreviewTask=null,renderBusy=false,renderStarting=false,renderCancelRequested=false,renderGeneration=0;
let parentScriptId = null;
let currentTask = null;
let taskTimer = null;
let consoleClosed = false;
function requireSavedProduct() {
  if (!currentProduct) throw new Error('请先保存或选择商品');
  if ($('product-title').value !== currentProduct.title || $('product-content').value !== currentProduct.content || $('product-index').value !== String(currentProduct.product_index) || $('product-facts').value !== productFactsText(currentProduct))
    throw new Error('商品有未保存修改，请先保存商品');
}
async function loadTask() {
  clearTimeout(taskTimer);
  if (consoleClosed) return;
  const result = await request('/api/llm/state');
  $('llm-configured').textContent = result.configured ? '已配置专用生成服务。生成结果请人工核对后使用。' : '未配置专用生成服务，请在本机设置控制台LLM环境变量后重启。';
  currentTask = result.task;
  const labels = {running:'正在生成',succeeded:'已保存生成话术',failed:'生成失败',cancelled:'已取消',interrupted:'上次生成已中断'};
  $('llm-task').textContent = currentTask ? (labels[currentTask.status] || currentTask.status) + ' · ' + (currentTask.product_title || '商品') + ' · 版本 ' + currentTask.product_version + (currentTask.error ? '：' + currentTask.error : '') : '暂无生成任务';
  if (currentTask?.status === 'succeeded' && currentProduct?.id === currentTask.product_id) await showScripts();
  if (currentTask?.status === 'running') taskTimer = setTimeout(() => loadTask().catch(error => { $('product-error').textContent = error.message; }), 750);
}
async function productAction(work) {
  $('product-error').textContent = ''; $('product-message').textContent = '';
  $('products-panel').querySelectorAll('button,select').forEach(b => b.disabled = true);
  try { await work(); } catch(error) { $('product-error').textContent = error.message || '商品服务连接失败'; }
  finally { $('products-panel').querySelectorAll('button,select').forEach(b => b.disabled = false); }
}
function showProduct(product) {
  clearTTSPreview();currentScriptId=null;
  currentProduct = product;
  parentScriptId = null;
  $('product-index').value = product?.product_index ?? '';
  $('product-title').value = product?.title ?? '';
  $('product-content').value = product?.content ?? '';
  $('product-facts').value = productFactsText(product);
  $('product-version').textContent = product ? '当前商品：' + product.title + ' · 版本 ' + product.version : '正在新增商品';
  $('script-text').value = ''; $('scripts-list').replaceChildren();
  $('business-metrics').hidden = !product;
  $('business-metrics-form').reset();
  $('business-import-form').reset();
  $('settlement-review-form').reset();
  $('promotion-form').reset();
  $('promotion-status').textContent = '';
  $('promotion-records').replaceChildren();
  $('promotion-plans').replaceChildren();
  $('after-sales-form').reset();
  $('after-sales-import-form').reset();
  $('after-sales-compare').reset();
  $('after-sales-comparison').textContent = '';
  $('after-sales-status').textContent = '';
  $('after-sales-reports').replaceChildren();
  $('metrics-status').textContent = '';
  $('metrics-error').textContent = '';
  $('metrics-records').replaceChildren();
  clearBusinessSummary();
}
const metricsRoute = '/api/products/business-metrics';
const summaryFields = {source:'metrics-source', scope:'metrics-scope', period_start:'metrics-start', period_end:'metrics-end'};
let summaryVersion = 0;
function clearBusinessSummary() {
  summaryVersion++;
  $('metrics-summary').textContent = '';
  $('settlement-review-result').textContent = '';
}
for (const id of Object.values(summaryFields)) {
  $(id).addEventListener('input', clearBusinessSummary);
}
const settlementForm = $('settlement-review-form');
const promotionForm = $('promotion-form');
async function loadPromotionPlans(product) {
  const {plans} = await request('/api/promotion/plans?' + new URLSearchParams({product_id:product.id}));
  if (currentProduct !== product) return;
  $('promotion-plans').replaceChildren(...plans.map(plan => {
    const row = document.createElement('li');
    row.textContent = `本机方案 ${plan.bill.campaign} / ${plan.bill.asset} · ${plan.bill.period_start} 至 ${plan.bill.period_end} · 原账单 ${plan.bill.spend_minor} 分 · 上限 ${plan.budget_minor} 分 · ${plan.rationale}`;
    const status = document.createElement('span');
    status.setAttribute('role', 'status');
    const labels = {draft:'待审核', approved:'本机已审核', paused:'本机已暂停', stale:'账单已变更，待重审'};
    const approve = document.createElement('button');
    approve.type = 'button';
    approve.textContent = '审核本机方案';
    const pause = document.createElement('button');
    pause.type = 'button';
    pause.textContent = '暂停本机方案';
    const showStatus = value => {
      status.textContent = plan.requires_new_plan ? '本机已暂停，账单已变更，请重新保存方案' : labels[value];
      approve.disabled = value === 'approved' || value === 'stale' || Boolean(plan.requires_new_plan);
      pause.disabled = value !== 'approved' && value !== 'stale';
    };
    showStatus(plan.status);
    const update = async action => {
      if (currentProduct !== product || consoleClosed) return;
      approve.disabled = pause.disabled = true;
      try {
        const {plan: updated} = await request('/api/promotion/plans/action', {plan_id:plan.id, action});
        if (updated.status === 'paused' && plan.status === 'stale') plan.requires_new_plan = true;
        plan.status = updated.status;
        showStatus(plan.status);
      } catch (error) {
        showStatus(plan.status);
        status.textContent = error.message;
      }
    };
    approve.addEventListener('click', () => update('approved'));
    pause.addEventListener('click', () => update('paused'));
    const history = document.createElement('details');
    const title = document.createElement('summary');
    title.textContent = '审核与暂停记录';
    const entries = document.createElement('ul');
    history.append(title, entries);
    history.addEventListener('toggle', async () => {
      if (!history.open || consoleClosed) return;
      try {
        const {actions} = await request('/api/promotion/plans/actions?' + new URLSearchParams({plan_id:plan.id}));
        entries.replaceChildren(...actions.map(action => {
          const entry = document.createElement('li');
          entry.textContent = `${new Date(action.occurred_at).toLocaleString()} · ${labels[action.action]}`;
          return entry;
        }));
        if (!actions.length) entries.textContent = '暂无操作记录';
      } catch (error) {
        entries.textContent = error.message;
      }
    });
    row.append(' ', status, ' ', approve, ' ', pause, history);
    return row;
  }));
}
async function promotionSpendAction(save) {
  const product = currentProduct;
  const buttons = Array.from(promotionForm.querySelectorAll('button'));
  if (!product || consoleClosed || buttons.some(button => button.disabled)) return;
  const status = $('promotion-status');
  const route = '/api/promotion/spend';
  buttons.forEach(button => { button.disabled = true; });
  status.textContent = '';
  try {
    let result;
    if (save) {
      const {spend_minor, attribution, ...fields} = Object.fromEntries(new FormData(promotionForm));
      const spend = Number(spend_minor);
      if (!Number.isSafeInteger(spend)) throw new Error('支出必须是可准确表示的整数分');
      const payload = {...fields, product_id:product.id, spend_minor:spend};
      if (attribution.trim()) payload.attribution = attribution;
      for (const key of ['source', 'period_start', 'period_end']) {
        const input = $(summaryFields[key]);
        if (!input.reportValidity()) return;
        payload[key] = input.value;
      }
      result = await request(route, payload);
    } else {
      result = await request(route + '?' + new URLSearchParams({product_id:product.id}));
    }
    if (currentProduct !== product) return;
    $('promotion-records').replaceChildren(...result.records.map(record => {
      const row = document.createElement('li');
      row.textContent = `${record.source} · ${record.period_start} 至 ${record.period_end} · 活动 ${record.campaign} · 素材 ${record.asset} · 支出 ${record.spend_minor} 分 · 归因口径 ${record.attribution ?? '未知'}`;
      const form = document.createElement('form');
      const budget = document.createElement('input');
      budget.type = 'number';
      budget.required = true;
      budget.min = '0';
      budget.max = String(Number.MAX_SAFE_INTEGER);
      budget.step = '1';
      const label = document.createElement('label');
      label.append('预算上限（人民币分）', budget);
      const button = document.createElement('button');
      button.type = 'submit';
      button.textContent = '预览预算';
      const previewStatus = document.createElement('p');
      previewStatus.setAttribute('role', 'status');
      const rationale = document.createElement('textarea');
      rationale.maxLength = 2000;
      const reason = document.createElement('label');
      reason.append('调整理由', rationale);
      const savePlan = document.createElement('button');
      savePlan.type = 'button';
      savePlan.textContent = '保存本机投放方案';
      form.append(label, button, reason, savePlan, previewStatus);
      row.append(form);
      const billIdentity = {product_id:record.product_id, source:record.source, period_start:record.period_start,
        period_end:record.period_end, campaign:record.campaign, asset:record.asset};
      const comparison = document.createElement('form');
      for (const [name, caption] of [['trial_start', '试验开始'], ['trial_end', '试验结束']]) {
        const input = document.createElement('input');
        input.type = 'date';
        input.name = name;
        input.required = true;
        const label = document.createElement('label');
        label.append(caption, input);
        comparison.append(label);
      }
      const compare = document.createElement('button');
      compare.type = 'submit';
      compare.textContent = '以本条账单为基线对照';
      const compareStatus = document.createElement('p');
      compareStatus.setAttribute('role', 'status');
      comparison.append(compare, compareStatus);
      row.append(comparison);
      comparison.addEventListener('submit', async event => {
        event.preventDefault();
        if (compare.disabled || currentProduct !== product || consoleClosed) return;
        const query = new URLSearchParams(new FormData(comparison));
        query.set('product_id', record.product_id);
        query.set('source', record.source);
        query.set('campaign', record.campaign);
        query.set('asset', record.asset);
        query.set('baseline_start', record.period_start);
        query.set('baseline_end', record.period_end);
        compare.disabled = true;
        try {
          const {comparison: result} = await request('/api/promotion/compare?' + query);
          compareStatus.textContent = `基线 ${result.baseline.spend_minor} 分 · 试验 ${result.trial.spend_minor} 分 · 差值 ${result.spend_difference_minor} 分 · 增量效果不确定（待补归因订单、退款和净结果）`;
        } catch (error) {
          compareStatus.textContent = error.message;
        } finally {
          compare.disabled = false;
        }
      });
      savePlan.addEventListener('click', async () => {
        if (savePlan.disabled || currentProduct !== product || consoleClosed || !budget.reportValidity()) return;
        savePlan.disabled = true;
        try {
          await request('/api/promotion/plans', {...billIdentity, budget_minor:budget.valueAsNumber, rationale:rationale.value});
          previewStatus.textContent = '本机投放方案已保存';
          await loadPromotionPlans(product);
        } catch (error) {
          previewStatus.textContent = error.message;
        } finally {
          savePlan.disabled = false;
        }
      });
      form.addEventListener('submit', async event => {
        event.preventDefault();
        if (button.disabled || currentProduct !== product || consoleClosed) return;
        button.disabled = true;
        try {
          const {preview} = await request('/api/promotion/budget-preview', {
            ...billIdentity, budget_minor:budget.valueAsNumber,
          });
          const labels = {over_budget:'已超预算', at_limit:'已达上限', below_limit:'低于上限'};
          previewStatus.textContent = `${labels[preview.status]} · 账单支出 ${preview.bill.spend_minor} 分 · 预算余额 ${preview.remaining_minor} 分`;
        } catch (error) {
          previewStatus.textContent = error.message;
        } finally {
          button.disabled = false;
        }
      });
      return row;
    }));
    status.textContent = save ? '投放费用已保存' : result.records.length ? '' : '暂无投放费用';
    await loadPromotionPlans(product);
  } catch (error) {
    if (currentProduct === product) status.textContent = error.message;
  } finally {
    buttons.forEach(button => { button.disabled = false; });
  }
}
promotionForm.addEventListener('submit', event => { event.preventDefault(); promotionSpendAction(true); });
$('promotion-read').addEventListener('click', () => promotionSpendAction(false));
const afterSalesForm = $('after-sales-form');
const afterSalesImportForm = $('after-sales-import-form');
const afterSalesCategories = {quality:'质量', size:'尺码', expectation:'预期不符', fulfillment:'履约', other:'其他'};
const afterSalesCompare = $('after-sales-compare');
let afterSalesComparisonVersion = 0;
function clearAfterSalesComparison() {
  afterSalesComparisonVersion++;
  $('after-sales-comparison').textContent = '';
}
afterSalesCompare.addEventListener('input', clearAfterSalesComparison);
$(summaryFields.source).addEventListener('input', clearAfterSalesComparison);
afterSalesCompare.addEventListener('submit', async event => {
  event.preventDefault();
  const product = currentProduct;
  const source = $(summaryFields.source);
  const button = afterSalesCompare.querySelector('button');
  if (!product || button.disabled || consoleClosed || !source.reportValidity()) return;
  const query = new URLSearchParams(new FormData(afterSalesCompare));
  query.set('product_id', product.id);
  query.set('source', source.value);
  const result = $('after-sales-comparison');
  const version = afterSalesComparisonVersion;
  button.disabled = true;
  result.textContent = '正在对照售后窗口';
  try {
    const {comparison} = await request('/api/products/after-sales/compare?' + query);
    if (currentProduct !== product || version !== afterSalesComparisonVersion) return;
    const lines = Object.entries(afterSalesCategories).map(([key, label]) =>
      `${label} ${comparison.baseline.counts[key] ?? '未知'} → ${comparison.trial.counts[key] ?? '未知'}（差值 ${comparison.differences[key] ?? '未知'}）`);
    result.textContent = [...lines, '效果结论：不确定'].join(' · ');
  } catch (error) {
    if (currentProduct === product && version === afterSalesComparisonVersion) result.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
async function afterSalesAction(action) {
  const product = currentProduct;
  if (!product || consoleClosed) return;
  const buttons = [...afterSalesForm.querySelectorAll('button'), ...afterSalesImportForm.querySelectorAll('button')];
  if (buttons.some(button => button.disabled)) return;
  const status = $('after-sales-status');
  const route = '/api/products/after-sales';
  const categories = afterSalesCategories;
  buttons.forEach(button => { button.disabled = true; });
  status.textContent = '';
  try {
    let result;
    if (action === 'import') {
      const file = $('after-sales-csv').files[0];
      if (!file) return;
      if (file.size >= 1048576) throw new Error('CSV 文件必须小于 1 MiB');
      let csv;
      try { csv = new TextDecoder('utf-8', {fatal:true}).decode(await file.arrayBuffer()); }
      catch { throw new Error('请使用可读取的 UTF-8 编码 CSV 文件'); }
      result = await request(route + '/import', {product_id:product.id, csv});
    } else if (action === 'save') {
      const payload = {product_id:product.id, counts:{}};
      for (const key of ['source', 'period_start', 'period_end']) {
        const input = $(summaryFields[key]);
        if (!input.reportValidity()) return;
        payload[key] = input.value;
      }
      for (const [key, value] of new FormData(afterSalesForm)) {
        if (value !== '') {
          const count = Number(value);
          if (!Number.isSafeInteger(count)) throw new Error('数量必须是可准确表示的整数');
          payload.counts[key] = count;
        }
      }
      result = await request(route, payload);
    } else {
      result = await request(route + '?' + new URLSearchParams({product_id:product.id}));
    }
    if (currentProduct !== product) return;
    $('after-sales-reports').replaceChildren(...result.reports.map(report => {
      const row = document.createElement('li');
      const counts = Object.entries(categories).map(([key, label]) => `${label} ${report.counts[key] ?? '未知'}`);
      row.textContent = [report.source, `${report.period_start} 至 ${report.period_end}`, ...counts].join(' · ');
      for (const followup of report.followups ?? []) {
        const suggestion = document.createElement('p');
        suggestion.textContent = `${categories[followup.category]} ${followup.count} · ${followup.recommendation}`;
        row.append(suggestion);
        const form = document.createElement('form');
        const owner = document.createElement('input');
        owner.required = true;
        owner.maxLength = 120;
        owner.value = followup.task?.owner ?? '';
        const goal = document.createElement('textarea');
        goal.required = true;
        goal.maxLength = 2000;
        goal.value = followup.task?.goal ?? followup.recommendation;
        const ownerLabel = document.createElement('label');
        ownerLabel.append('负责人', owner);
        const goalLabel = document.createElement('label');
        goalLabel.append('改进目标', goal);
        const save = document.createElement('button');
        save.type = 'submit';
        save.textContent = '保存售后改进任务';
        const revoke = document.createElement('button');
        revoke.type = 'button';
        revoke.textContent = '撤销纳入准备包';
        revoke.hidden = !followup.task || followup.task.revoked;
        const identity = {product_id:product.id, source:report.source, period_start:report.period_start,
          period_end:report.period_end, category:followup.category};
        const feedback = document.createElement('p');
        feedback.setAttribute('role', 'status');
        if (followup.task && followup.task.evidence_count !== followup.count) {
          feedback.textContent = '报表数量已更正，请核对目标后重新保存';
        }
        if (followup.task && followup.task.product_version !== product.version) {
          feedback.textContent = followup.task.product_version == null
            ? '原任务未记录商品版本，请按当前资料核对后重新保存'
            : '商品资料已更新，请按当前版本核对后重新保存';
        }
        if (followup.task?.revoked) feedback.textContent = '已撤销，可重新保存以纳入准备包';
        form.append(ownerLabel, goalLabel, save, revoke, feedback);
        revoke.addEventListener('click', async () => {
          if (save.disabled || currentProduct !== product || consoleClosed) return;
          save.disabled = revoke.disabled = true;
          try {
            await request(route + '/task/revoke', identity);
            revoke.hidden = true;
            feedback.textContent = '已撤销，可重新保存以纳入准备包';
          } catch (error) {
            feedback.textContent = error.message;
          } finally {
            save.disabled = revoke.disabled = false;
          }
        });
        form.addEventListener('submit', async event => {
          event.preventDefault();
          if (save.disabled || currentProduct !== product || consoleClosed) return;
          save.disabled = true;
          try {
            await request(route + '/task', {
              ...identity, owner:owner.value, goal:goal.value, product_version:product.version,
              expected_count:followup.count,
            });
            revoke.hidden = false;
            feedback.textContent = '已保存，将纳入该商品的直播准备包';
          } catch (error) {
            feedback.textContent = error.message;
          } finally {
            save.disabled = false;
          }
        });
        row.append(form);
      }
      return row;
    }));
    status.textContent = action === 'import' ? `已导入 ${result.imported} 行售后汇总`
      : action === 'save' ? '售后汇总已保存' : result.reports.length ? '' : '暂无售后汇总';
  } catch (error) {
    if (currentProduct === product) status.textContent = error.message;
  } finally {
    buttons.forEach(button => { button.disabled = false; });
  }
}
afterSalesForm.addEventListener('submit', event => { event.preventDefault(); afterSalesAction('save'); });
afterSalesImportForm.addEventListener('submit', event => { event.preventDefault(); afterSalesAction('import'); });
$('after-sales-read').addEventListener('click', () => afterSalesAction('read'));
settlementForm.addEventListener('input', clearBusinessSummary);
settlementForm.addEventListener('submit', async event => {
  event.preventDefault();
  if (!currentProduct) return;
  const button = settlementForm.querySelector('button');
  if (button.disabled) return;
  clearBusinessSummary();
  const output = $('settlement-review-result');
  const payload = {product_id:currentProduct.id, currency:'CNY'};
  for (const [field, id] of Object.entries(summaryFields)) {
    const input = $(id);
    if (!input.reportValidity()) return;
    payload[field] = input.value;
  }
  for (const [field, value] of new FormData(settlementForm)) {
    payload[field] = field === 'basis' ? value : value === '' ? null : Number(value);
    if (field !== 'basis' && payload[field] !== null && !Number.isSafeInteger(payload[field])) {
      output.textContent = field.endsWith('_minor') ? '金额必须是可准确表示的整数分' : '数量必须是可准确表示的整数';
      return;
    }
  }
  const version = summaryVersion;
  button.disabled = true;
  try {
    const {review} = await request('/api/products/settlement-review', payload);
    if (version !== summaryVersion) return;
    const basis = review.basis === 'settled' ? '已结算（按录入）' : '估算';
    const net = review.net_minor == null ? '未知' : `${review.net_minor} 分`;
    const onTimeRate = review.on_time_fulfillment_rate == null ? '未知'
      : new Intl.NumberFormat('zh-CN', {style:'percent', maximumFractionDigits:2}).format(review.on_time_fulfillment_rate);
    const turnover = review.inventory_turnover == null ? '未知'
      : `${new Intl.NumberFormat('zh-CN', {maximumFractionDigits:3}).format(review.inventory_turnover)} 次`;
    output.textContent = `${basis} · 净收益 ${net} · 订单 ${review.orders ?? '未知'} · 退款 ${review.refunds ?? '未知'} · 履约类售后 ${review.fulfillment_after_sales ?? '未知'} · 准时履约率 ${onTimeRate} · 按件库存周转 ${turnover}`;
  } catch (error) {
    if (version === summaryVersion) output.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
$('metrics-query').addEventListener('click', async () => {
  if (!currentProduct) return;
  clearBusinessSummary();
  const output = $('metrics-summary');
  const params = new URLSearchParams({product_id:currentProduct.id});
  for (const [field, id] of Object.entries(summaryFields)) {
    const input = $(id);
    if (!input.reportValidity()) return;
    params.set(field, input.value);
  }
  const version = summaryVersion;
  output.textContent = '正在查询经营汇总';
  try {
    const {summary} = await request(metricsRoute + '/summary?' + params);
    if (version !== summaryVersion) return;
    output.textContent = `点击 ${summary.clicks ?? '未知'} · 订单 ${summary.orders ?? '未知'} · 退款 ${summary.refunds ?? '未知'} · 期末库存 ${summary.closing_stock ?? '未知'}`;
  } catch (error) {
    if (version === summaryVersion) output.textContent = error.message;
  }
});
function showBusinessMetrics(records) {
  clearBusinessSummary();
  $('metrics-records').replaceChildren(...records.map(record => {
    const item = document.createElement('li');
    item.textContent = `${record.period_start} 至 ${record.period_end} · ${record.source} · ${record.scope} · 点击 ${record.clicks ?? '未知'} · 订单 ${record.orders ?? '未知'} · 退款 ${record.refunds ?? '未知'} · 库存 ${record.stock ?? '未知'}`;
    return item;
  }));
}
async function loadBusinessMetrics() {
  const product = currentProduct;
  if (!product) return;
  try {
    const result = await request(metricsRoute + '?product_id=' + encodeURIComponent(product.id));
    if (currentProduct === product) showBusinessMetrics(result.records);
  } catch (error) {
    if (currentProduct === product) $('metrics-error').textContent = error.message;
  }
}
$('business-metrics-form').addEventListener('submit', async event => {
  event.preventDefault();
  const product = currentProduct;
  if (!product) return;
  const button = event.currentTarget.querySelector('button[type="submit"]');
  if (button.disabled) return;
  button.disabled = true;
  $('metrics-error').textContent = '';
  $('metrics-status').textContent = '';
  try {
    const payload = {product_id:product.id, source:$('metrics-source').value,
      period_start:$('metrics-start').value, period_end:$('metrics-end').value, scope:$('metrics-scope').value};
    for (const field of ['clicks','orders','refunds','stock']) {
      const input = $('metrics-' + field);
      payload[field] = input.value === '' ? null : input.valueAsNumber;
      if (payload[field] !== null && !Number.isSafeInteger(payload[field])) throw new Error('指标必须是可准确表示的整数');
    }
    const result = await request(metricsRoute, payload);
    if (currentProduct === product) {
      showBusinessMetrics(result.records);
      $('metrics-status').textContent = '经营数据已保存';
    }
  } catch (error) {
    if (currentProduct === product) $('metrics-error').textContent = error.message;
  } finally { button.disabled = false; }
});
$('business-import-form').addEventListener('submit', async event => {
  event.preventDefault();
  const product = currentProduct;
  const file = $('metrics-csv').files[0];
  if (!product || !file) return;
  const button = event.currentTarget.querySelector('button[type="submit"]');
  if (button.disabled) return;
  button.disabled = true;
  $('metrics-error').textContent = '';
  $('metrics-status').textContent = '';
  try {
    if (file.size >= 1048576) throw new Error('CSV 文件必须小于 1 MiB');
    const bytes = await file.arrayBuffer();
    let csv;
    try { csv = new TextDecoder('utf-8', {fatal:true}).decode(bytes); }
    catch { throw new Error('请使用 UTF-8 编码的 CSV 文件'); }
    const result = await request(metricsRoute + '/import', {product_id:product.id, csv});
    if (currentProduct === product) {
      showBusinessMetrics(result.records);
      $('metrics-status').textContent = `已导入 ${result.imported} 行经营数据`;
    }
  } catch (error) {
    if (currentProduct === product) $('metrics-error').textContent = error.message;
  } finally { button.disabled = false; }
});
async function showScripts() {
  if (!currentProduct) return;
  const result = await request('/api/scripts?product_id=' + encodeURIComponent(currentProduct.id));
  currentScriptId=result.selected;
  $('scripts-list').replaceChildren(...result.scripts.map(script => {
    const item = document.createElement('li');
    const content = document.createElement('p');
    content.textContent = '版本 ' + script.product_version + (script.product_version === currentProduct.version ? ' · 当前' : ' · 历史') + (script.id === result.selected ? ' · 已选用' : '') + (script.parent_script_id ? ' · 修改稿' : '') + '：' + script.text;
    item.append(content);
    if (script.segments) {
      const roles = script.segments.map(segment => segment.type === 'pause'
        ? '停顿 ' + segment.duration + ' 秒'
        : (segment.type === 'assistant' ? '助播' : '主播') + '：' + segment.content);
      const preview = document.createElement('p');
      preview.textContent = roles.join(' ｜ ');
      item.append(preview);
    }
    const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'secondary'; edit.textContent = '载入修改';
    edit.addEventListener('click', () => {
      $('script-text').value = script.text; parentScriptId = script.id;
      $('product-message').textContent = script.product_version === currentProduct.version ? '原稿已载入，保存时创建修改稿并保留原稿。' : '历史原稿已载入，请按当前商品事实修改后保存；原稿会保留。';
    });
    item.append(edit);
    if (script.product_version === currentProduct.version) {
      const select = document.createElement('button'); select.type='button'; select.className='secondary'; select.textContent='设为当前话术';
      select.addEventListener('click', () => productAction(async () => {
        requireSavedProduct();
        await request('/api/scripts/select',{product_id:currentProduct.id,script_id:script.id});
        clearTTSPreview();
        await showScripts(); $('product-message').textContent='当前话术已保存；尚未启动播放。';
      }));
      item.append(select);
    }
    return item;
  }));
}
const preparationRoute = '/api/live/preparation';
const sourcingForm = $('sourcing-form');
const sourcingFields = {access:'获取条件', demand:'需求', competition:'竞争', terms:'采购条件',
  minimum_order:'起订量', lead_time:'交期', logistics:'物流', quality_evidence:'质量证据'};
let sourcingCandidates = [];
const sourcingComparison = $('sourcing-comparison');
$('sourcing-compare').addEventListener('click', () => {
  const selected = new Set(Array.from($('sourcing-candidates').querySelectorAll('input:checked'), item => item.value));
  const candidates = sourcingCandidates.filter(item => selected.has(item.id));
  if (candidates.length < 2 || candidates.length > 5) {
    sourcingComparison.textContent = '请选择 2 至 5 条候选记录';
    return;
  }
  const table = document.createElement('table');
  const head = table.createTHead().insertRow();
  for (const label of ['对照项', ...candidates.map(item => `${item.name} · ${item.supplier}`)]) {
    const cell = document.createElement('th');
    cell.scope = 'col';
    cell.textContent = label;
    head.append(cell);
  }
  const body = table.createTBody();
  const fields = {source:'资料来源', observed_on:'资料日期', ...sourcingFields};
  for (const [key, label] of Object.entries(fields)) {
    const row = body.insertRow();
    const heading = document.createElement('th');
    heading.scope = 'row';
    heading.textContent = label;
    row.append(heading);
    for (const candidate of candidates) {
      row.insertCell().textContent = candidate[key] ?? candidate.details[key] ?? '未知';
    }
  }
  const note = document.createElement('p');
  note.textContent = '质量证据为登记资料，样品和实际交付待核对。';
  sourcingComparison.replaceChildren(table, note);
});
for (const [key, name] of Object.entries(sourcingFields)) {
  const label = document.createElement('label');
  const input = document.createElement('input');
  input.name = key;
  input.maxLength = 2000;
  label.append(name, input);
  $('sourcing-details').append(label);
}
async function sourcingAction(save) {
  const buttons = Array.from(sourcingForm.querySelectorAll('button'));
  if (consoleClosed || buttons.some(button => button.disabled)) return;
  const route = '/api/sourcing/candidates';
  const status = $('sourcing-status');
  buttons.forEach(button => { button.disabled = true; });
  try {
    if (save) {
      const fields = Object.fromEntries(new FormData(sourcingForm));
      const {name, supplier, source, observed_on, ...optional} = fields;
      const details = Object.fromEntries(Object.entries(optional).filter(([, value]) => value.trim()));
      await request(route, {name, supplier, source, observed_on, details});
      sourcingForm.reset();
    }
    const {candidates} = await request(route);
    sourcingCandidates = candidates;
    sourcingComparison.replaceChildren();
    $('sourcing-candidates').replaceChildren(...candidates.map(candidate => {
      const row = document.createElement('li');
      const title = document.createElement('label');
      const select = document.createElement('input');
      select.type = 'checkbox';
      select.value = candidate.id;
      select.addEventListener('change', () => sourcingComparison.replaceChildren());
      title.append(select, ` ${candidate.name} · ${candidate.supplier} · ${candidate.source} · ${candidate.observed_on}`);
      const facts = document.createElement('ul');
      for (const [key, label] of Object.entries(sourcingFields)) {
        const fact = document.createElement('li');
        fact.textContent = `${label}：${candidate.details[key] ?? '未知'}`;
        facts.append(fact);
      }
      row.append(title, facts, sourcingTrialEditor(candidate), sourcingDecisionEditor(candidate));
      return row;
    }));
    status.textContent = save ? '采购候选已保存' : candidates.length ? '' : '暂无采购候选';
  } catch (error) {
    status.textContent = error.message;
  } finally {
    buttons.forEach(button => { button.disabled = false; });
  }
}
const sourcingTrialMetrics = {orders:'同批试卖订单', refunds:'同批退款订单', fulfilled_on_time:'按时履约订单',
  gross_profit_minor:'同批试卖毛利（人民币分）'};
function sourcingTrialEditor(candidate) {
  const route = '/api/sourcing/trial';
  const panel = document.createElement('details');
  const summary = document.createElement('summary');
  summary.textContent = '样品核验与试卖';
  const form = document.createElement('form');
  const sample = document.createElement('textarea');
  const trial = document.createElement('textarea');
  const cost = document.createElement('input');
  cost.type = 'number';
  cost.min = '0';
  cost.step = '1';
  cost.max = String(Number.MAX_SAFE_INTEGER);
  const verdict = document.createElement('select');
  verdict.append(new Option('待核验', 'pending'), new Option('商家核验通过', 'pass'), new Option('商家核验未通过', 'fail'));
  for (const [caption, input] of [['样品核验依据', sample], ['试卖记录或待办', trial],
    ['样品成本（人民币分，可留空）', cost], ['样品核验结果', verdict]]) {
    const label = document.createElement('label');
    label.append(caption, input);
    form.append(label);
  }
  sample.required = trial.required = true;
  sample.maxLength = trial.maxLength = 2000;
  const metrics = {};
  for (const [key, caption] of Object.entries(sourcingTrialMetrics)) {
    const input = document.createElement('input');
    input.type = 'number';
    input.min = key === 'gross_profit_minor' ? String(-Number.MAX_SAFE_INTEGER) : '0';
    input.max = String(Number.MAX_SAFE_INTEGER);
    input.step = '1';
    metrics[key] = input;
    const label = document.createElement('label');
    label.append(caption + '（可留空）', input);
    form.append(label);
  }
  const button = document.createElement('button');
  button.type = 'submit';
  button.textContent = '保存样品与试卖记录';
  button.disabled = true;
  const status = document.createElement('p');
  status.setAttribute('role', 'status');
  form.append(button, status);
  panel.append(summary, form);
  let loading = false;
  panel.addEventListener('toggle', async () => {
    if (!panel.open || !button.disabled || loading || consoleClosed) return;
    loading = true;
    try {
      const query = new URLSearchParams({candidate_id:candidate.id});
      const {trial: saved} = await request(route + '?' + query);
      sample.value = saved?.sample_evidence ?? '';
      trial.value = saved?.trial_evidence ?? '';
      cost.value = saved?.cost_minor ?? '';
      verdict.value = saved?.verdict ?? 'pending';
      for (const [key, input] of Object.entries(metrics)) input.value = saved?.metrics?.[key] ?? '';
      status.textContent = '';
      button.disabled = false;
    } catch (error) {
      status.textContent = error.message;
    } finally {
      loading = false;
    }
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (button.disabled || consoleClosed) return;
    button.disabled = true;
    try {
      const counts = Object.fromEntries(Object.entries(metrics).filter(([, input]) => input.value !== '')
        .map(([key, input]) => [key, input.valueAsNumber]));
      await request(route, {candidate_id:candidate.id, sample_evidence:sample.value, trial_evidence:trial.value,
        cost_minor:cost.value === '' ? null : cost.valueAsNumber, verdict:verdict.value, metrics:counts});
      status.textContent = '样品与试卖记录已保存';
    } catch (error) {
      status.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
  return panel;
}
function sourcingDecisionEditor(candidate) {
  const route = '/api/sourcing/decision';
  const panel = document.createElement('details');
  const summary = document.createElement('summary');
  summary.textContent = '采购辅助结论';
  const form = document.createElement('form');
  const decision = document.createElement('select');
  decision.append(new Option('继续试验', 'continue'), new Option('采用', 'adopt'), new Option('放弃', 'drop'));
  const rationale = document.createElement('textarea');
  const constraints = document.createElement('textarea');
  rationale.required = constraints.required = true;
  rationale.maxLength = constraints.maxLength = 2000;
  for (const [caption, input] of [['商家结论', decision], ['结论依据', rationale], ['资金及库存约束', constraints]]) {
    const label = document.createElement('label');
    label.append(caption, input);
    form.append(label);
  }
  const button = document.createElement('button');
  button.type = 'submit';
  button.textContent = '保存采购结论';
  button.disabled = true;
  const status = document.createElement('p');
  status.setAttribute('role', 'status');
  const evidence = document.createElement('p');
  const currentEvidence = document.createElement('p');
  form.append(button, status, evidence, currentEvidence);
  panel.append(summary, form);
  function showEvidence(record) {
    const snapshot = record?.trial;
    const terms = record?.candidate;
    evidence.textContent = terms
      ? `保存结论时的采购资料：${terms.supplier} · ${terms.source} · ${terms.observed_on}`
      : record ? '历史结论未记录采购资料快照' : '';
    if (terms) {
      for (const [key, label] of Object.entries(sourcingFields)) {
        if (terms.details?.[key]) evidence.append(` · ${label} ${terms.details[key]}`);
      }
    }
    if (snapshot) evidence.append(
      ` · 样品依据：${snapshot.sample_evidence} · 试卖：${snapshot.trial_evidence} · 样品成本：${snapshot.cost_minor ?? '未知'}${snapshot.cost_minor == null ? '' : ' 分'}`);
    if (snapshot) {
      const metrics = Object.entries(sourcingTrialMetrics).map(([key, label]) =>
        `${label} ${snapshot.metrics?.[key] ?? '未知'}`);
      evidence.append(' · ' + metrics.join(' · '));
    }
  }
  let reviewedTrial = null;
  let loaded = false;
  let loading = false;
  panel.addEventListener('toggle', async () => {
    if (!panel.open || loaded || loading || consoleClosed) return;
    loading = true;
    try {
      const query = new URLSearchParams({candidate_id:candidate.id});
      const [{decision: record}, {trial}] = await Promise.all([
        request(route + '?' + query), request('/api/sourcing/trial?' + query),
      ]);
      reviewedTrial = trial;
      decision.value = record?.decision ?? 'continue';
      rationale.value = record?.rationale ?? '';
      constraints.value = record?.constraints ?? '';
      showEvidence(record);
      const original = record?.trial;
      const fields = ['sample_evidence', 'trial_evidence', 'cost_minor', 'verdict'];
      const changed = record && (
        fields.some(key => original?.[key] !== trial?.[key]) ||
        Object.keys(sourcingTrialMetrics).some(key => original?.metrics?.[key] !== trial?.metrics?.[key])
      );
      currentEvidence.textContent = trial ? [
        `样品核验状态：${{pending:'待核验', pass:'商家核验通过', fail:'商家核验未通过'}[trial.verdict] ?? '未知'}`,
        `当前样品依据：${trial.sample_evidence}`,
        `当前试卖依据：${trial.trial_evidence}`,
        `样品成本：${trial.cost_minor == null ? '未知' : trial.cost_minor + ' 分'}`,
        ...Object.entries(sourcingTrialMetrics).map(([key, label]) => `${label} ${trial.metrics?.[key] ?? '未知'}`),
      ].join(' · ') : '尚无试样或试卖记录';
      status.textContent = changed ? '试样或试卖记录已更新，请核对后再保存采购结论' : '';
      loaded = true;
      button.disabled = false;
    } catch (error) {
      status.textContent = error.message;
    } finally {
      loading = false;
    }
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (button.disabled || consoleClosed) return;
    button.disabled = true;
    try {
      const {decision: record} = await request(route, {candidate_id:candidate.id, decision:decision.value,
        rationale:rationale.value, constraints:constraints.value, expected_trial:reviewedTrial});
      showEvidence(record);
      status.textContent = '采购辅助结论已保存';
    } catch (error) {
      loaded = false;
      status.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
  return panel;
}
sourcingForm.addEventListener('submit', event => { event.preventDefault(); sourcingAction(true); });
$('sourcing-read').addEventListener('click', () => sourcingAction(false));
$('selection-evidence-form').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button');
  if (button.disabled || consoleClosed) return;
  const status = $('selection-evidence-status');
  const output = $('selection-evidence-results');
  output.replaceChildren();
  const params = new URLSearchParams();
  for (const [key, value] of new FormData(form)) {
    if (value.trim()) params.set(key, value.trim());
  }
  if (params.size !== 0 && params.size !== 4) {
    status.textContent = '对照经营数据时，请填齐来源、口径和日期区间';
    return;
  }
  button.disabled = true;
  status.textContent = '正在查询选品依据';
  try {
    const {products, business_metrics_scope: scope} = await request('/api/products/selection-evidence?' + params);
    output.replaceChildren(...products.map(product => {
      const block = document.createElement('section');
      const title = document.createElement('h4');
      title.textContent = `${product.title} · 版本 ${product.product_version}`;
      const facts = document.createElement('ul');
      for (const [name, fact] of Object.entries(product.conditions)) {
        const item = document.createElement('li');
        item.textContent = fact ? `${name}：${fact.value}（来源：${fact.source}）` : `${name}：未知`;
        facts.append(item);
      }
      block.append(title, facts);
      const suggestion = document.createElement('p');
      const roles = {hold:'暂缓', trial:'试播', support:'辅助', primary:'主推'};
      suggestion.textContent = `建议${roles[product.recommendation.role]} · ${product.recommendation.reason}`;
      block.append(suggestion);
      if (product.stock_review) {
        const stockReview = document.createElement('p');
        stockReview.textContent = product.stock_review;
        block.append(stockReview);
      }
      if (product.recommendation.role !== 'hold') {
        const add = document.createElement('button');
        add.type = 'button';
        add.className = 'secondary';
        add.textContent = '加入直播准备草稿';
        add.addEventListener('click', async () => {
          if (add.disabled || consoleClosed) return;
          add.disabled = true;
          try {
            const {products: latest} = await request('/api/products/selection-evidence');
            if (consoleClosed || !add.isConnected) return;
            const current = latest.find(item => item.product_id === product.product_id);
            const checkbox = Array.from($('preparation-products').querySelectorAll('input'))
              .find(input => input.value === product.product_id);
            if (current?.product_version !== product.product_version || !checkbox || preparationSave.disabled) {
              status.textContent = '商品列表或准备草稿已变化，请重新读取后再加入';
              return;
            }
            if (current.recommendation.role === 'hold') {
              status.textContent = `建议暂缓 · ${current.recommendation.reason}`;
              return;
            }
            checkbox.checked = true;
            status.textContent = `${product.title} 已勾选，请核对并保存准备草稿`;
          } catch (error) {
            status.textContent = error.message;
          } finally {
            add.disabled = false;
          }
        });
        block.append(add);
      }
      if (scope) {
        const metrics = document.createElement('p');
        const counts = product.business_metrics;
        metrics.textContent = counts
          ? `点击 ${counts.clicks ?? '未知'} · 订单 ${counts.orders ?? '未知'} · 退款 ${counts.refunds ?? '未知'} · 期末库存 ${counts.closing_stock ?? '未知'}`
          : product.business_metrics_gap;
        block.append(metrics);
        if (product.refund_review) {
          const review = document.createElement('p');
          review.textContent = product.refund_review;
          block.append(review);
        }
      }
      return block;
    }));
    status.textContent = products.length ? (scope
      ? `${scope.source} · ${scope.scope} · ${scope.period_start} 至 ${scope.period_end}` : '') : '暂无商品';
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
const preparationFields = ['goal', 'audience', 'promotion', 'stock', 'shipping', 'constraints'];
const preparationForm = $('preparation-form');
const preparationSave = preparationForm.querySelector('button[type="submit"]');
const preparationPreview = $('preparation-preview');
const preparationReviewSave = $('preparation-review-save');
let preparationRevision;
let preparedRotation = null;
$('preparation-apply').addEventListener('click', async event => {
  const button = event.currentTarget;
  button.disabled = true;
  $('preparation-error').textContent = '';
  try {
    const {revision, items} = await request(preparationRoute + '/rotation', {revision:preparationRevision});
    const missing = items.filter(item => !item.script_id);
    if (missing.length) throw new Error('请先选用话术：' + missing.map(item => item.title).join('、'));
    preparedRotation = {revision, items:items.map(({product_id, product_version, script_id}) =>
      ({product_id, product_version, script_id}))};
    const ids = new Set(items.map(item => item.product_id));
    for (const option of $('live-products').options) option.selected = ids.has(option.value);
    rotationSelectionEdited = true;
    renderShiftFields();
    renderLiveButtons();
    $('preparation-status').textContent = '已载入轮播顺序：' + items.map(item => item.title).join(' → ');
  } catch (error) {
    $('preparation-error').textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
preparationReviewSave.addEventListener('click', async () => {
  preparationReviewSave.disabled = true;
  $('preparation-error').textContent = '';
  try {
    await request(preparationRoute + '/review', {revision:preparationRevision, review:$('preparation-package').value});
    $('preparation-status').textContent = '审阅稿已保存';
  } catch (error) {
    $('preparation-error').textContent = error.message;
  } finally {
    preparationReviewSave.disabled = false;
  }
});
let savedPreparationHasProducts = false;
const captureBaseline = $('preparation-capture-baseline');
async function showLineupBaseline(capture) {
  const button = capture ? captureBaseline : $('preparation-baseline');
  if (button.disabled || consoleClosed) return;
  button.disabled = true;
  const status = $('preparation-baseline-status');
  try {
    const {baseline} = await request(preparationRoute + '/baseline', capture ? {} : undefined);
    status.textContent = baseline
      ? `人工基线 · ${new Date(baseline.captured_at).toLocaleString()} · ${baseline.lineup.map(item => `${item.title}（版本 ${item.version}）`).join(' → ')}`
      : '暂无人工排品基线';
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = capture && !savedPreparationHasProducts;
  }
}
$('preparation-baseline').addEventListener('click', () => showLineupBaseline(false));
captureBaseline.addEventListener('click', () => showLineupBaseline(true));
function updatePreparationPreview(draft) {
  savedPreparationHasProducts = draft.product_ids.length > 0;
  preparationPreview.disabled = !savedPreparationHasProducts;
  captureBaseline.disabled = !savedPreparationHasProducts;
}
preparationPreview.addEventListener('click', async () => {
  preparationPreview.disabled = true;
  preparationSave.disabled = true;
  $('preparation-error').textContent = '';
  try {
    const {items, segments, missing, revision, review, improvements, after_sales_tasks} =
      await request(preparationRoute + '/package');
    const lines = ['开场', segments.opening];
    for (const [index, item] of items.entries()) {
      if (index) lines.push('', '转场', segments.transition);
      lines.push('', `${index + 1}. ${item.title}（版本 ${item.product_version}）`);
      lines.push(item.script_id ? `选用话术：${item.script_id}` : '待补：为该商品选用话术');
      if (item.recommendation?.role === 'hold') lines.push(`建议暂缓 · ${item.recommendation.reason}`);
      if (item.stock_review) lines.push(item.stock_review);
      for (const point of item.selling_points) lines.push(`${point.name}：${point.value}（来源：${point.source}）`);
      for (const entry of item.faq) lines.push(`问：${entry.question} 答：${entry.answer}（来源：${entry.source}）`);
      for (const condition of item.missing) lines.push(`待补：${condition}`);
      for (const asset of item.assets) lines.push(`素材：${asset}`);
    }
    lines.push('', '收尾', segments.closing);
    if (missing.length) lines.push('', '场次待补条件', ...missing);
    if (improvements.length) {
      lines.push('', '已采用的改进任务', ...improvements.map(task =>
        `${task.owner} · ${task.goal}（场次 ${task.session_id}，${task.reply_task_id ? '答复 ' + task.reply_task_id : '故障 ' + task.fault_id}）`));
    }
    if (after_sales_tasks.length) {
      lines.push('', '售后改进任务', ...after_sales_tasks.map(task => {
        const title = items.find(item => item.product_id === task.product_id)?.title ?? task.product_id;
        return `${title} · ${task.owner} · ${task.goal}（${task.source}，${task.period_start} 至 ${task.period_end}，记录 ${task.evidence_count} 条）`;
      }));
    }
    preparationRevision = revision;
    $('preparation-package').value = review ?? lines.join('\n');
    $('preparation-package-panel').hidden = false;
  } catch (error) {
    $('preparation-error').textContent = error.message;
  } finally {
    preparationPreview.disabled = !savedPreparationHasProducts;
    preparationSave.disabled = false;
  }
});
function preparationProductIds() {
  return Array.from($('preparation-products').querySelectorAll('input:checked'), input => input.value);
}
$('product-guide-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button');
  if (button.disabled || consoleClosed) return;
  const status = $('product-guide-status');
  const results = $('product-guide-results');
  results.replaceChildren();
  const ids = preparationProductIds();
  const criteria = new Map();
  for (const line of $('product-guide-facts').value.split(/\r?\n/).map(line => line.trim()).filter(Boolean)) {
    const separator = line.indexOf('=');
    const name = (separator < 0 ? line : line.slice(0, separator)).trim();
    const expected = separator < 0 ? null : line.slice(separator + 1).trim();
    if (!name || expected === '' || criteria.has(name)) {
      status.textContent = '请填写有效且不重复的条件，例如「材质=陶瓷」';
      return;
    }
    criteria.set(name, expected);
  }
  const names = [...criteria.keys()];
  if (!ids.length || ids.length > 10 || !names.length || names.length > 12) {
    status.textContent = '请选择 1 至 10 件商品，并填写 1 至 12 项事实';
    return;
  }
  const query = new URLSearchParams();
  for (const id of ids) query.append('product_id', id);
  for (const name of names) query.append('fact', name);
  button.disabled = true;
  status.textContent = '正在核对商品';
  try {
    const {products} = await request('/api/products/guide?' + query);
    let unknown = false;
    for (const product of products) {
      const title = document.createElement('h4');
      title.textContent = `${product.title} · 版本 ${product.product_version}`;
      const facts = document.createElement('ul');
      for (const name of names) {
        const fact = product.facts[name];
        const expected = criteria.get(name);
        const item = document.createElement('li');
        const actual = typeof fact?.value === 'string' ? fact.value.trim()
          : typeof fact?.value === 'number' ? String(fact.value) : null;
        const matches = expected == null ? '' : actual == null ? ' · 条件待人工核对'
          : actual === expected ? ' · 符合所填条件' : ` · 与所填条件「${expected}」不同`;
        item.textContent = fact ? `${name}：${fact.value}（来源：${fact.source}）${matches}` : `${name}：待人工核对`;
        unknown ||= !fact;
        facts.append(item);
      }
      results.append(title, facts);
    }
    status.textContent = unknown ? '部分商品事实需人工核对' : '';
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
function showPreparationProducts(ids) {
  const byId = new Map(savedProducts.map(product => [product.id, product]));
  const ordered = [...ids.map(id => byId.get(id)).filter(Boolean),
    ...savedProducts.filter(product => !ids.includes(product.id))];
  const list = $('preparation-products');
  list.replaceChildren(...ordered.map(product => {
    const row = document.createElement('div');
    const label = document.createElement('label');
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = product.id;
    input.checked = ids.includes(product.id);
    label.append(input, ' ', product.title);
    row.append(label);
    for (const direction of ['上移', '下移']) {
      const move = document.createElement('button');
      move.type = 'button';
      move.className = 'secondary';
      move.textContent = direction;
      move.setAttribute('aria-label', direction + product.title);
      move.addEventListener('click', () => {
        const neighbor = direction === '上移' ? row.previousElementSibling : row.nextElementSibling;
        if (!neighbor) return;
        if (direction === '上移') list.insertBefore(row, neighbor);
        else list.insertBefore(neighbor, row);
        move.focus();
      });
      row.append(move);
    }
    return row;
  }));
}
function showPreparationMissing(missing) {
  $('preparation-missing').replaceChildren(...missing.map(condition => {
    const item = document.createElement('li');
    item.textContent = condition;
    return item;
  }));
}
async function loadPreparation() {
  try {
    const {draft, missing} = await request(preparationRoute);
    showPreparationProducts(draft.product_ids);
    for (const field of preparationFields) $('preparation-' + field).value = draft[field];
    showPreparationMissing(missing);
    updatePreparationPreview(draft);
    preparationSave.disabled = false;
  } catch (error) {
    $('preparation-error').textContent = error.message;
  }
}
preparationForm.addEventListener('submit', async event => {
  event.preventDefault();
  if (preparationSave.disabled) return;
  preparationSave.disabled = true;
  preparationPreview.disabled = true;
  $('preparation-error').textContent = '';
  $('preparation-status').textContent = '';
  try {
    const draft = {product_ids:preparationProductIds()};
    for (const field of preparationFields) draft[field] = $('preparation-' + field).value;
    const {draft: savedDraft, missing} = await request(preparationRoute, draft);
    showPreparationMissing(missing);
    updatePreparationPreview(savedDraft);
    $('preparation-package-panel').hidden = true;
    $('preparation-package').value = '';
    $('preparation-status').textContent = missing.length ? '草稿已保存，以下条件待补' : '草稿已保存，条件已填齐';
  } catch (error) {
    $('preparation-error').textContent = error.message;
  } finally {
    preparationSave.disabled = false;
    preparationPreview.disabled = !savedPreparationHasProducts;
  }
});
async function loadProducts() {
  const result = await request('/api/products'); savedProducts = result.products;
  showPreparationProducts(preparationProductIds());
  const selectedRotation = new Set(Array.from($('live-products').selectedOptions, option => option.value));
  $('live-products').replaceChildren(...savedProducts.map(product =>
    new Option(`${product.product_index} · ${product.title}`, product.id, false, selectedRotation.has(product.id))));
  const eventProduct = $('live-event-product');
  const eventProductId = eventProduct.value;
  eventProduct.replaceChildren(new Option('全部商品', ''), ...savedProducts.map(product =>
    new Option(`${product.product_index} · ${product.title}`, product.id)));
  eventProduct.value = savedProducts.some(product => product.id === eventProductId) ? eventProductId : '';
  if (eventProduct.value !== eventProductId) resetRotationEvents();
  renderShiftFields();
  const empty = document.createElement('option'); empty.value = ''; empty.textContent = '请选择商品';
  $('product-list').replaceChildren(empty, ...savedProducts.map(product => {
    const option = document.createElement('option'); option.value = product.id;
    option.textContent = product.product_index + ' · ' + product.title; return option;
  }));
  const selected = savedProducts.find(p => p.id === result.selected) || null;
  $('product-list').value = selected?.id || ''; showProduct(selected); await Promise.all([showScripts(), loadBusinessMetrics()]);
}
$('new-product').addEventListener('click', () => { $('product-list').value = ''; showProduct(null); });
$('reload-products').addEventListener('click', () => productAction(async () => { await loadProducts(); await loadTask(); }));
$('product-list').addEventListener('change', () => productAction(async () => {
  const selected = savedProducts.find(p => p.id === $('product-list').value);
  if (!selected) { showProduct(null); return; }
  await request('/api/products/select', {product_id:selected.id}); showProduct(selected); await Promise.all([showScripts(), loadBusinessMetrics()]);
}));
$('product-form').addEventListener('submit', event => { event.preventDefault(); productAction(async () => {
  const value = {title:$('product-title').value, content:$('product-content').value, product_index:$('product-index').value};
  if (currentProduct) Object.assign(value, {product_id:currentProduct.id,version:currentProduct.version});
  const facts = $('product-facts').value.trim();
  if (facts !== productFactsText(currentProduct).trim()) {
    try { value.product_facts = facts ? JSON.parse(facts) : {}; }
    catch { throw new Error('商品事实必须是有效的 JSON 对象'); }
    if (!value.product_facts || typeof value.product_facts !== 'object' || Array.isArray(value.product_facts))
      throw new Error('商品事实必须是有效的 JSON 对象');
  }
  const result = await request('/api/products', value);
  await request('/api/products/select', {product_id:result.product.id});
  await loadProducts(); $('product-message').textContent = '商品已保存';
}); });
$('script-form').addEventListener('submit', event => { event.preventDefault(); productAction(async () => {
  requireSavedProduct();
  await request('/api/scripts', {snapshot:currentProduct,text:$('script-text').value,parent_script_id:parentScriptId});
  parentScriptId = null; await showScripts(); $('script-text').value = ''; $('product-message').textContent = '话术已保存';
}); });
$('generate-script').addEventListener('click', () => productAction(async () => {
  requireSavedProduct();
  await request('/api/llm/generate', {product_id:currentProduct.id,version:currentProduct.version,instructions:$('llm-instructions').value});
  await loadTask();
}));
$('cancel-generation').addEventListener('click', () => productAction(async () => {
  if (!currentTask) throw new Error('暂无生成任务');
  await request('/api/llm/cancel', {task_id:currentTask.id}); await loadTask();
}));
let voiceRecords=[];
function showVoice(id) {
  clearTTSPreview();
  const voice=voiceRecords.find(v => v.id===id);
  $('voice-preview').pause();
  if (voice) {
    $('voice-info').textContent=voice.name+' · '+voice.duration.toFixed(2)+'秒 · 参考文本：'+voice.transcript;
    $('voice-preview').src='/api/voices/audio?id='+encodeURIComponent(voice.id);
  } else { $('voice-info').textContent='尚未选择音色'; $('voice-preview').removeAttribute('src'); }
  $('voice-preview').load();
}
async function voiceAction(work) {
  $('voice-error').textContent=''; $('voice-message').textContent='';
  $('voice-panel').querySelectorAll('button,select').forEach(x => x.disabled=true);
  try { await work(); } catch(error) { showVoice(null); $('voice-error').textContent=error.message || '音色服务无法连接'; }
  finally { $('voice-panel').querySelectorAll('button,select').forEach(x => x.disabled=false); renderRecordingButtons(); }
}
async function loadVoices() {
  const result=await request('/api/voices'); voiceRecords=result.voices;
  const empty=document.createElement('option');empty.value='';empty.textContent='请选择音色';
  $('voice-list').replaceChildren(empty,...voiceRecords.map(voice => {
    const option=document.createElement('option');option.value=voice.id;option.textContent=voice.name;return option;
  }));
  $('voice-list').value=result.selected || ''; showVoice(result.selected);
  const assistant = $('live-assistant-voice');
  const selectedAssistant = assistant.value;
  assistant.replaceChildren(new Option('沿用主播音色', ''), ...voiceRecords.map(voice => new Option(voice.name, voice.id)));
  assistant.value = voiceRecords.some(voice => voice.id === selectedAssistant) ? selectedAssistant : '';
  renderShiftFields();
}
$('voice-form').addEventListener('submit',event => { event.preventDefault(); voiceAction(async () => {
  const result=await request('/api/voices/import',{source:$('voice-source').value,transcript:$('voice-transcript').value,name:$('voice-name').value});
  await request('/api/voices/select',{voice_id:result.voice.id});await loadVoices();$('voice-message').textContent='音色已导入并选中。';
}); });
$('voice-list').addEventListener('change',() => voiceAction(async () => {
  const id=$('voice-list').value;if (!id) {showVoice(null);return;}
  await request('/api/voices/select',{voice_id:id});showVoice(id);
}));
$('reload-voices').addEventListener('click',() => voiceAction(loadVoices));
$('voice-preview').addEventListener('error',() => {if ($('voice-preview').getAttribute('src')) $('voice-error').textContent='参考音无法加载，请重读音色并检查文件完整性。';});
let recordingUrl=null;
function renderRecordingButtons() {
  $('record-start').disabled=['requesting','recording','stopping'].includes(recorder.state);
  $('record-stop').disabled=recorder.state!=='recording';
  $('record-save').disabled=recorder.state!=='preview';
}
const recorder=new window.VoiceRecorder((state,blob,error)=>{
  $('record-preview').pause();
  if(recordingUrl) URL.revokeObjectURL(recordingUrl);recordingUrl=null;
  $('record-preview').removeAttribute('src');
  if(blob) {recordingUrl=URL.createObjectURL(blob);$('record-preview').src=recordingUrl;}
  $('record-preview').load();
  const labels={idle:'尚未录音',requesting:'正在请求麦克风权限',recording:'正在录音，30秒后自动停止',stopping:'正在结束录音',preview:'录音完成，请试听并核对对应文本后保存'};
  $('record-status').textContent=labels[state] || state;
  if(error) $('voice-error').textContent=error;
  renderRecordingButtons();
});
$('record-start').addEventListener('click',()=>{$('voice-error').textContent='';recorder.start();});
$('record-stop').addEventListener('click',()=>recorder.stop());
$('record-discard').addEventListener('click',()=>recorder.discard());
$('record-save').addEventListener('click',()=>voiceAction(async()=>{
  if(recorder.state!=='preview' || !recorder.blob) throw new Error('请先完成录音');
  const blob=recorder.blob;
  const encoded=await new Promise((resolve,reject)=>{
    const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('录音读取失败'));reader.readAsDataURL(blob);
  });
  const result=await request('/api/voices/recorded',{audio_base64:encoded,name:$('voice-name').value,transcript:$('voice-transcript').value});
  await request('/api/voices/select',{voice_id:result.voice.id});await loadVoices();recorder.discard();$('voice-message').textContent='录音已保存为音色。';
}));
window.addEventListener('pagehide',()=>recorder.discard());
renderRecordingButtons();
function clearTTSPreview() {
  clearRenderPreview();
  $('tts-preview').pause();$('tts-preview').removeAttribute('src');$('tts-preview').load();ttsPreviewTask=null;
}
function renderTTSButtons() {
  $('tts-generate').disabled=ttsState?.status==='running';
  $('tts-cancel').disabled=ttsState?.status!=='running';
}
async function loadTTS() {
  clearTimeout(ttsTimer);if(consoleClosed) return;
  const response=await request('/api/tts/state');if(consoleClosed) return;
  ttsState=response.task;
  const labels={running:'正在合成',succeeded:'语音已生成',cancelled:'已取消合成',interrupted:'上次合成已中断',failed:'语音不可用'};
  $('tts-status').textContent=ttsState ? (labels[ttsState.status] || ttsState.status)+' · '+(ttsState.product_title || '商品')+' · 版本 '+ttsState.product_version+(ttsState.result?.cache_hit ? ' · 已复用相同输入的语音' : '')+(ttsState.error ? '：'+ttsState.error : '') : '暂无合成任务';
  const saved=currentProduct && $('product-title').value===currentProduct.title && $('product-content').value===currentProduct.content && $('product-index').value===String(currentProduct.product_index) && $('product-facts').value===productFactsText(currentProduct);
  const matches=ttsState?.status==='succeeded' && saved && ttsState.product_id===currentProduct.id && ttsState.script_id===currentScriptId && ttsState.voice_id===$('voice-list').value && ttsState.speed===Number($('tts-speed').value) && (ttsState.language || 'zh-CN')===$('tts-language').value;
  if(matches) {
    if(ttsPreviewTask!==ttsState.id) {$('tts-preview').src='/api/tts/audio?task_id='+encodeURIComponent(ttsState.id);$('tts-preview').load();ttsPreviewTask=ttsState.id;}
  } else if(ttsPreviewTask) clearTTSPreview();
  renderTTSButtons();
  if(['running','succeeded'].includes(ttsState?.status)) ttsTimer=setTimeout(()=>loadTTS().catch(error=>{$('tts-error').textContent=error.message;clearTTSPreview();}),1000);
}
async function ttsAction(work) {
  $('tts-error').textContent='';$('tts-generate').disabled=true;$('tts-cancel').disabled=true;
  try {await work();} catch(error) {$('tts-error').textContent=error.message || '语音服务无法连接';clearTTSPreview();}
  finally {renderTTSButtons();}
}
$('tts-generate').addEventListener('click',()=>ttsAction(async()=>{
  requireSavedProduct();
  if(!currentScriptId) throw new Error('请先将一条当前版本的话术设为当前话术');
  if(!$('voice-list').value) throw new Error('请先选择参考音色');
  clearTTSPreview();
  await request('/api/tts/generate',{product_id:currentProduct.id,script_id:currentScriptId,voice_id:$('voice-list').value,speed:Number($('tts-speed').value),language:$('tts-language').value,use_cache:$('tts-use-cache').checked});
  await loadTTS();
}));
$('tts-cancel').addEventListener('click',()=>ttsAction(async()=>{
  if(!ttsState) throw new Error('暂无合成任务');
  await request('/api/tts/cancel',{task_id:ttsState.id});clearTTSPreview();await loadTTS();
}));
$('tts-refresh').addEventListener('click',()=>ttsAction(loadTTS));
$('tts-preview').addEventListener('error',()=>{if($('tts-preview').getAttribute('src')) $('tts-error').textContent='音频已失效或无法加载，请刷新任务状态。';});
for(const id of ['product-title','product-content','product-index','product-facts']) $(id).addEventListener('input',clearTTSPreview);
$('tts-speed').addEventListener('input',clearTTSPreview);
$('tts-language').addEventListener('change',clearTTSPreview);
window.addEventListener('pagehide',()=>{clearTimeout(ttsTimer);clearTTSPreview();});
renderTTSButtons();
let avatarRecords=[],avatarBusy=false;
function showAvatar(id) {
  clearRenderPreview();
  const avatar=avatarRecords.find(item=>item.id===id);
  $('avatar-preview').hidden=!avatar;
  $('avatar-preview').removeAttribute('src');
  $('avatar-info').textContent=avatar ? avatar.name+' · '+avatar.width+'×'+avatar.height+' · '+avatar.frames+'帧' : '尚未选择形象';
  if(avatar) $('avatar-preview').src='/api/avatars/sample?id='+encodeURIComponent(id);
}
async function loadAvatars() {
  if(consoleClosed) return;
  const result=await request('/api/avatars');if(consoleClosed) return;avatarRecords=result.avatars;
  const empty=document.createElement('option');empty.value='';empty.textContent='请选择形象';
  $('avatar-list').replaceChildren(empty,...avatarRecords.map(avatar=>{
    const option=document.createElement('option');option.value=avatar.id;option.textContent=avatar.name;return option;
  }));
  $('avatar-list').value=result.selected || '';showAvatar(result.selected);
}
async function avatarAction(work) {
  if(avatarBusy || consoleClosed) return;avatarBusy=true;
  $('avatar-error').textContent='';$('avatar-message').textContent='';$('avatar-import').disabled=true;
  try {await work();} catch(error) {$('avatar-error').textContent=error.message || '形象服务无法连接';}
  finally {avatarBusy=false;$('avatar-import').disabled=consoleClosed;}
}
$('avatar-form').addEventListener('submit',event=>{event.preventDefault();avatarAction(async()=>{
  $('avatar-message').textContent='正在导入并检查形象素材…';
  const result=await request('/api/avatars/import',{source:$('avatar-source').value,name:$('avatar-name').value});
  await request('/api/avatars/select',{avatar_id:result.avatar.id});await loadAvatars();$('avatar-message').textContent='形象已导入并选中。';
});});
$('reload-avatars').addEventListener('click',()=>avatarAction(loadAvatars));
$('avatar-list').addEventListener('change',()=>avatarAction(async()=>{
  const id=$('avatar-list').value;if(!id) {showAvatar(null);return;}
  showAvatar(null);
  await request('/api/avatars/select',{avatar_id:id});showAvatar(id);
}));
$('avatar-preview').addEventListener('error',()=>{
  if($('avatar-preview').getAttribute('src')) {$('avatar-preview').hidden=true;$('avatar-error').textContent='形象预览已失效，请重读形象检查素材完整性。';}
});

let avatarVideoState=null,avatarVideoTimer=null,avatarVideoShown=null,avatarVideoBusy=false;
function renderAvatarVideoButtons() {
  $('avatar-video-start').disabled=consoleClosed || avatarVideoBusy || avatarVideoState?.status==='running';
  $('avatar-video-cancel').disabled=consoleClosed || avatarVideoBusy || avatarVideoState?.status!=='running';
}
async function loadAvatarVideo() {
  clearTimeout(avatarVideoTimer);if(consoleClosed) return;
  const result=await request('/api/avatar-preparation/state');if(consoleClosed) return;
  avatarVideoState=result.task;
  const states={running:'正在制作',succeeded:'制作完成，请在形象列表选择使用',failed:'制作失败',cancelled:'已取消制作',interrupted:'上次制作已中断'};
  const phases={starting:'正在启动',normalizing:'正在整理视频',detecting_faces:'正在处理人脸',validating:'正在检查形象'};
  $('avatar-video-status').textContent=avatarVideoState ? (states[avatarVideoState.status] || avatarVideoState.status)+' · '+avatarVideoState.name+(avatarVideoState.status==='running' ? ' · '+(phases[avatarVideoState.phase] || '') : '')+(avatarVideoState.error ? '：'+avatarVideoState.error : '') : '暂无视频制作任务';
  if(avatarVideoState?.status==='succeeded' && avatarVideoShown!==avatarVideoState.id) {
    await loadAvatars();avatarVideoShown=avatarVideoState.id;
  }
  renderAvatarVideoButtons();
  if(avatarVideoState?.status==='running') avatarVideoTimer=setTimeout(()=>loadAvatarVideo().catch(error=>{$('avatar-video-error').textContent=error.message;}),1000);
}
async function avatarVideoAction(work) {
  if(avatarVideoBusy || consoleClosed) return;avatarVideoBusy=true;renderAvatarVideoButtons();$('avatar-video-error').textContent='';
  try {await work();} catch(error) {$('avatar-video-error').textContent=error.message || '形象制作服务无法连接';}
  finally {avatarVideoBusy=false;renderAvatarVideoButtons();}
}
$('avatar-video-form').addEventListener('submit',event=>{event.preventDefault();avatarVideoAction(async()=>{
  await request('/api/avatar-preparation/start',{source:$('avatar-video-source').value,name:$('avatar-video-name').value,resolution:$('avatar-resolution').value});
  await loadAvatarVideo();
});});
$('avatar-video-cancel').addEventListener('click',()=>avatarVideoAction(async()=>{
  if(!avatarVideoState) throw new Error('暂无制作任务');
  await request('/api/avatar-preparation/cancel',{task_id:avatarVideoState.id});await loadAvatarVideo();
}));
$('avatar-video-refresh').addEventListener('click',()=>avatarVideoAction(loadAvatarVideo));
window.addEventListener('pagehide',()=>clearTimeout(avatarVideoTimer));
renderAvatarVideoButtons();

function clearRenderPreview() {
  $('render-subtitle').hidden = true;
  $('render-preview').pause();$('render-preview').removeAttribute('src');$('render-preview').load();renderPreviewTask=null;
}
function renderVideoButtons() {
  $('render-profile').disabled=consoleClosed || renderBusy || renderState?.status==='running';
  $('render-generate').disabled=consoleClosed || renderBusy || renderState?.status==='running';
  $('render-cancel').disabled=consoleClosed || (!renderStarting && (renderBusy || renderState?.status!=='running'));
}
async function loadRender() {
  clearTimeout(renderTimer);if(consoleClosed) return;
  const generation=++renderGeneration;let response;
  try {response=await request('/api/render/state');}
  catch(error) {if(generation!==renderGeneration || consoleClosed) return;throw error;}
  if(consoleClosed || generation!==renderGeneration) return;
  renderState=response.task;
  const labels={running:'正在生成视频',succeeded:'视频已生成',cancelled:'视频生成已取消',interrupted:'上次视频生成已中断',failed:'视频不可用'};
  $('render-status').textContent=renderState ? (labels[renderState.status] || renderState.status)+' · '+renderState.product_title+' · '+renderState.avatar_name+' · '+(renderState.render_profile==='trt-nvenc' ? '加速预览' : '标准生成')+(renderState.error ? '：'+renderState.error : '') : '暂无视频生成任务';
  const saved=currentProduct && $('product-title').value===currentProduct.title && $('product-content').value===currentProduct.content && $('product-index').value===String(currentProduct.product_index) && $('product-facts').value===productFactsText(currentProduct);
  const matches=renderState?.status==='succeeded' && saved && renderState.product_id===currentProduct.id && renderState.script_id===currentScriptId && renderState.tts_task_id===ttsState?.id && renderState.tts_task_id===ttsPreviewTask && renderState.avatar_id===$('avatar-list').value;
  if(matches) {
    const samples = renderState.result?.input_audio_samples;
    $('render-subtitle').hidden = !Number.isSafeInteger(samples) || samples <= 0 || Boolean(ttsState.kind);
    if(renderPreviewTask!==renderState.id) {$('render-preview').src='/api/render/video?task_id='+encodeURIComponent(renderState.id);$('render-preview').load();renderPreviewTask=renderState.id;}
  } else if(renderPreviewTask) clearRenderPreview();
  renderVideoButtons();
  if(['running','succeeded'].includes(renderState?.status)) renderTimer=setTimeout(()=>loadRender().catch(error=>{$('render-error').textContent=error.message;clearRenderPreview();}),1000);
}
async function renderAction(work) {
  if(renderBusy || consoleClosed) return;renderBusy=true;renderVideoButtons();$('render-error').textContent='';
  try {await work();} catch(error) {$('render-error').textContent=error.message || '视频服务无法连接';clearRenderPreview();}
  finally {renderBusy=false;renderVideoButtons();}
}
$('render-generate').addEventListener('click',()=>renderAction(async()=>{
  requireSavedProduct();
  if(ttsState?.status!=='succeeded' || !ttsPreviewTask || ttsPreviewTask!==ttsState.id) throw new Error('请先完成当前话术和音色的语音合成');
  if(!$('avatar-list').value) throw new Error('请先选择数字人形象');
  clearTimeout(renderTimer);++renderGeneration;
  clearRenderPreview();renderStarting=true;renderCancelRequested=false;renderVideoButtons();
  $('render-status').textContent='正在检查语音与形象，可以取消…';
  try {
    const result=await request('/api/render/start',{tts_task_id:ttsState.id,avatar_id:$('avatar-list').value,render_profile:$('render-profile').value});renderState=result.task;
    if(renderCancelRequested) await request('/api/render/cancel',{task_id:renderState.id});
    await loadRender();
  } finally {renderStarting=false;renderCancelRequested=false;}
}));
$('render-cancel').addEventListener('click',()=>{
  if(renderStarting) {renderCancelRequested=true;$('render-status').textContent='正在取消，请稍候…';return;}
  renderAction(async()=>{
  if(!renderState) throw new Error('暂无视频任务');
  clearTimeout(renderTimer);++renderGeneration;
  await request('/api/render/cancel',{task_id:renderState.id});clearRenderPreview();await loadRender();
  });
});
$('render-refresh').addEventListener('click',()=>renderAction(loadRender));
$('render-subtitle').addEventListener('click', async () => {
  const taskId = renderPreviewTask;
  const button = $('render-subtitle');
  if (!taskId || button.disabled || consoleClosed) return;
  button.disabled = true;
  $('render-error').textContent = '';
  try {
    const response = await fetch('/api/render/subtitle?task_id=' + encodeURIComponent(taskId));
    if (!response.ok) {
      const {error} = await response.json();
      throw new Error(error || '成片字幕下载失败');
    }
    const subtitle = await response.blob();
    if (taskId !== renderPreviewTask || consoleClosed) return;
    const url = URL.createObjectURL(subtitle);
    const link = document.createElement('a');
    link.href = url;
    link.download = '数字人视频字幕.srt';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    if (taskId === renderPreviewTask && !consoleClosed) $('render-error').textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
$('render-preview').addEventListener('error',()=>{
  if($('render-preview').getAttribute('src')) {$('render-error').textContent='视频已失效或无法加载，请刷新视频状态。';clearRenderPreview();}
});
window.addEventListener('pagehide',()=>{clearTimeout(renderTimer);clearRenderPreview();});
renderVideoButtons();

let liveSession = {status:'idle'}, liveTimer, liveBusy = false;
let rotationSelectionEdited = false;
let rotationEventCursor = 0;
function resetRotationEvents() {
  rotationEventCursor = 0;
  $('live-rotation-events-list').replaceChildren();
  $('live-rotation-events-status').textContent = '';
  $('live-event-session').textContent = '';
  $('live-event-controls').replaceChildren();
  $('live-rotation-events').textContent = '查看口播记录';
}
const shiftDrafts = new Map();
function renderShiftFields() {
  const panel = $('live-shifts');
  panel.hidden = !$('live-shifts-enabled').checked;
  if (panel.hidden) return;
  const rows = Array.from($('live-products').selectedOptions, option => {
    const draft = shiftDrafts.get(option.value) || {seconds:'60', voice:''};
    shiftDrafts.set(option.value, draft);
    const row = document.createElement('fieldset');
    const name = document.createElement('legend'); name.textContent = option.textContent;
    const duration = document.createElement('input');
    duration.type = 'number'; duration.min = '1'; duration.max = '86400'; duration.value = draft.seconds;
    duration.addEventListener('input', () => { draft.seconds = duration.value; });
    const durationLabel = document.createElement('label'); durationLabel.append('班次时长（秒）', duration);
    const voice = document.createElement('select');
    voice.replaceChildren(new Option('沿用场次主播', ''), ...voiceRecords.map(item => new Option(item.name, item.id)));
    voice.value = draft.voice;
    draft.voice = voice.value;
    voice.addEventListener('change', () => { draft.voice = voice.value; });
    const voiceLabel = document.createElement('label'); voiceLabel.append('主播音色', voice);
    row.append(name, durationLabel, voiceLabel);
    return row;
  });
  panel.replaceChildren(...rows);
}
const liveLabels = {idle:'未启动', preparing:'准备中', running:'本机输出中', stopping:'停止中', stopped:'已停止', failed:'输出失败'};
function renderLiveButtons() {
  const active = ['preparing','running','stopping'].includes(liveSession.status);
  $('live-start').disabled = consoleClosed || liveBusy || active || !$('live-audio').value;
  $('live-stop').disabled = consoleClosed || liveBusy || !['preparing','running'].includes(liveSession.status);
  $('live-control').disabled = consoleClosed || liveBusy || liveSession.status !== 'running' || liveSession.mode === 'local_video';
  $('live-control').textContent = liveSession.manual ? '恢复自动调度' : '手动接管';
  $('live-speak').disabled = $('live-control').disabled || !liveSession.manual;
  $('live-rotation-start').disabled = $('live-control').disabled || !$('live-products').selectedOptions.length;
  $('live-rotation-start').textContent = liveSession.rotation_error ? '重试商品轮播' : '开始商品轮播';
  $('live-rotation-stop').disabled = $('live-control').disabled || !liveSession.rotation_products?.length;
  $('live-event-scene').disabled = consoleClosed || liveBusy;
  $('live-event-refresh').disabled = consoleClosed || liveBusy;
  $('live-rotation-events').disabled = consoleClosed || liveBusy || !($('live-event-scene').value || liveSession.id);
  $('live-report').disabled = $('live-rotation-events').disabled;
  $('live-event-product').disabled = $('live-rotation-events').disabled;
  $('live-event-task').disabled = $('live-rotation-events').disabled;
  $('live-enqueue').disabled = $('live-control').disabled || !!liveSession.manual;
  $('live-insert').disabled = liveSession.mode === 'local_video'
    ? consoleClosed || liveBusy || liveSession.status !== 'running' || !!liveSession.insert_pending || !!liveSession.seek_pending
    : $('live-enqueue').disabled;
  $('live-audio').disabled = active || liveBusy;
  $('live-video-path').disabled = consoleClosed || active || liveBusy;
  $('live-video-backend-panel').hidden = !$('live-video-path').value.trim();
  $('live-video-backend').disabled = consoleClosed || active || liveBusy;
  $('live-video-seek').hidden = liveSession.mode !== 'local_video' || liveSession.status !== 'running';
  $('live-video-jump').disabled = consoleClosed || liveBusy || !!liveSession.seek_pending || !!liveSession.insert_pending;
  $('live-assistant-voice').disabled = consoleClosed || active || liveBusy;
}
async function loadLive() {
  clearTimeout(liveTimer);
  if (consoleClosed) return;
  const previousSession = liveSession.id;
  const {session, advice, acknowledged} = await request('/api/live/state');
  liveSession = session;
  $('live-advice').hidden = !advice.length;
  const adviceList = $('live-advice-list');
  const adviceLines = advice.map(item => {
    const context = item.context;
    const details = [item.evidence];
    if (context?.occurred_at != null) details.push(new Date(context.occurred_at * 1000).toLocaleString());
    if (context?.next_frame != null) details.push(`待输出帧 ${context.next_frame}`);
    if (item.code === 'silent_speech' && context?.first_frame != null) {
      details.push(`静音起始帧 ${context.first_frame}`);
    }
    if (context?.task_id) details.push(`问答任务 ${context.task_id}`);
    if (context?.fact_expired_at != null) {
      details.push('商品事实到期 ' + new Date(context.fact_expired_at * 1000).toLocaleString());
    }
    if (context?.product_id) {
      const title = savedProducts.find(product => product.id === context.product_id)?.title ?? context.product_id;
      details.push(title);
      if (context.product_version != null) details.push(`商品版本 ${context.product_version}`);
      if (context.script_id) details.push(`话术 ${context.script_id}`);
    }
    return [...details, item.recommendation].join(' · ');
  });
  const adviceKey = JSON.stringify([session.id, advice, adviceLines, acknowledged]);
  if (adviceList.dataset.key !== adviceKey) {
    adviceList.dataset.key = adviceKey;
    adviceList.replaceChildren(...adviceLines.map((line, index) => {
    const row = document.createElement('li');
    const button = document.createElement('button');
    button.type = 'button';
    const currentAdvice = advice[index];
    let checked = acknowledged.some(item => JSON.stringify(item) === JSON.stringify(currentAdvice));
    const updateLabel = () => { button.textContent = checked ? '撤销核对' : '标记已核对'; };
    updateLabel();
    const status = document.createElement('span');
    status.setAttribute('role', 'status');
    button.addEventListener('click', async () => {
      if (button.disabled || consoleClosed) return;
      button.disabled = true;
      status.textContent = '';
      try {
        const action = checked ? 'revoke' : 'acknowledge';
        const result = await request('/api/live/advice/' + action, {session_id:session.id, advice:currentAdvice});
        checked = result.acknowledged;
        updateLabel();
        status.textContent = checked ? '已核对' : '已撤销';
      } catch (error) {
        status.textContent = error.message;
      } finally {
        button.disabled = false;
      }
    });
    row.append(line, ' ', button, ' ', status);
    return row;
    }));
  }
  if (previousSession !== liveSession.id && !$('live-event-scene').value) {
    resetRotationEvents();
    $('live-report-output').replaceChildren();
  }
  if (!rotationSelectionEdited) {
    const configured = new Set(liveSession.rotation_retry_products || liveSession.rotation_products || []);
    let selectionChanged = false;
    for (const option of $('live-products').options) {
      const selected = configured.has(option.value);
      selectionChanged ||= option.selected !== selected;
      option.selected = selected;
    }
    if (selectionChanged) renderShiftFields();
  }
  $('live-status').textContent = liveLabels[liveSession.status];
  $('live-detail').textContent = liveSession.insert_error || (liveSession.insert_pending ? '正在准备插播语音' :
    (liveSession.frames ? `已提交 ${liveSession.frames} 帧，待播 ${liveSession.pending ?? 0} 条` : ''));
  $('live-rotation-status').textContent = liveSession.rotation_error || (liveSession.rotation_products?.length ?
    `${liveSession.manual ? '轮播暂停' : '轮播中'} · ${liveSession.rotation_products.length} 个商品 · 已播 ${liveSession.rotation_completed} 条` +
      (liveSession.shift_index == null ? '' : ` · 第 ${liveSession.shift_index + 1} 班`) : '');
  if (liveSession.error) $('live-error').textContent = liveSession.error;
  renderLiveButtons();
  if (['preparing','running','stopping'].includes(liveSession.status)) {
    liveTimer = setTimeout(() => loadLive().catch(error => {$('live-error').textContent = error.message;}), 800);
  }
}
async function liveAction(work) {
  if (consoleClosed || liveBusy) return;
  liveBusy = true; renderLiveButtons(); $('live-error').textContent = '';
  try { await work(); await loadLive(); }
  catch (error) { $('live-error').textContent = error.message; }
  finally { liveBusy = false; renderLiveButtons(); }
}
$('live-audio').addEventListener('change', renderLiveButtons);
$('live-video-path').addEventListener('input', renderLiveButtons);
$('live-products').addEventListener('change', () => { preparedRotation = null; rotationSelectionEdited = true; renderShiftFields(); renderLiveButtons(); });
$('live-shifts-enabled').addEventListener('change', renderShiftFields);
$('live-rotation-start').addEventListener('click', () => liveAction(() => {
  const product_ids = preparedRotation ? preparedRotation.items.map(item => item.product_id)
    : Array.from($('live-products').selectedOptions, option => option.value);
  const payload = {session_id:liveSession.id, product_ids};
  if (preparedRotation) payload.preparation = preparedRotation;
  if ($('live-shifts-enabled').checked) {
    payload.shift_durations = product_ids.map(id => Number(shiftDrafts.get(id)?.seconds || 0));
    if (payload.shift_durations.some(seconds => !Number.isInteger(seconds) || seconds < 1 || seconds > 86400)) {
      throw new Error('班次时长须为 1 至 86400 秒的整数');
    }
    payload.shift_voice_ids = product_ids.map(id => shiftDrafts.get(id)?.voice || null);
  }
  return request('/api/live/rotation', payload);
}));
$('live-rotation-stop').addEventListener('click', () => liveAction(() => request('/api/live/rotation', {
  session_id:liveSession.id, product_ids:[]
})));
$('live-event-product').addEventListener('change', resetRotationEvents);
$('live-event-task').addEventListener('input', resetRotationEvents);
$('live-event-scene').addEventListener('change', () => {
  resetRotationEvents();
  $('live-report-output').replaceChildren();
  renderLiveButtons();
});
$('live-report').addEventListener('click', () => liveAction(async () => {
  const sessionId = $('live-event-scene').value || liveSession.id;
  const output = $('live-report-output');
  output.textContent = '正在读取场次报告';
  try {
    const query = new URLSearchParams({session_id:sessionId});
    const [{session, products, controls, rotation_faults, observed_product_switches, queued_replies, lineup_baseline,
      advice_acknowledgments, advice_actions, missing, preparation_applications, content_summary}, review, improvements] =
      await Promise.all([request('/api/live/report?' + query), request('/api/live/review?' + query),
        request('/api/live/improvements?' + query)]);
    if (($('live-event-scene').value || liveSession.id) !== sessionId) return;
    const formatTime = value => value == null ? '未记录' : new Date(value * 1000).toLocaleString();
    const labels = {product_exposure:'商品曝光', questions_and_answers:'问答', platform_product_switches:'平台切品',
      fault_events:'故障', attributed_sales:'成交归因'};
    const lines = [
      `场次 ${session.session_id} · ${liveLabels[session.status] ?? session.status} · 输出 ${session.frames} 帧`,
      `开始 ${formatTime(session.started_at)} · 结束 ${formatTime(session.ended_at)}`,
      ...products.map(item => {
        const title = savedProducts.find(product => product.id === item.product_id)?.title ?? item.product_id;
        return `${title} · 商品版本 ${item.product_version} · 话术 ${item.script_id} · 已播片段 ${item.completed_segments}`;
      }),
      ...controls.map(item => `${formatTime(item.occurred_at)} · ${item.manual ? '人工接管' : '恢复自动'} · 记录 ${item.revision}`),
      ...rotation_faults.map(item => `${formatTime(item.occurred_at)} · 轮播故障 ${item.event_id} · ${item.reason}`),
      ...observed_product_switches.map(item => `${item.completed_at} · 口播商品变化 ${item.previous_product_id} → ${item.product_id} · 任务 ${item.task_id}`),
    ];
    if (content_summary?.drafts) {
      const {drafts, tracked_drafts, revised_drafts, recorded_publications} = content_summary;
      lines.push(`短视频草稿 ${drafts} 条 · 已登记发布回执 ${recorded_publications} 条`);
      if (content_summary.withdrawn_drafts) {
        lines.push(`已停止复用的草稿 ${content_summary.withdrawn_drafts} 条`);
      }
      if (tracked_drafts) lines.push(`有改稿记录的草稿 ${revised_drafts}/${tracked_drafts}`);
      if (drafts > tracked_drafts) lines.push(`改稿次数未知 ${drafts - tracked_drafts} 条`);
      if (content_summary.timed_drafts) {
        lines.push(`人工登记平均制作耗时 ${content_summary.average_production_seconds.toFixed(1)} 秒（${content_summary.timed_drafts} 条）`);
      }
      if (content_summary.paired_drafts) {
        lines.push(`人工基线减去复用耗时，平均 ${content_summary.average_seconds_saved.toFixed(1)} 秒（${content_summary.paired_drafts} 条）`);
      }
    }
    for (const application of preparation_applications) {
      if (!application.improvements.length) continue;
      lines.push(`已载入准备包 ${application.revision}`);
      for (const task of application.improvements) {
        const source = task.reply_task_id ? `答复 ${task.reply_task_id}` : `故障 ${task.fault_id}`;
        lines.push(`${task.owner} · ${task.goal} · 原场次 ${task.session_id} · ${source}`);
      }
    }
    for (const reply of queued_replies) {
      const title = savedProducts.find(product => product.id === reply.product_id)?.title ?? reply.product_id;
      lines.push(
        `${formatTime(reply.queued_at)} · 问答已入队 · ${title} · 商品版本 ${reply.product_version} · 任务 ${reply.task_id}`,
        reply.played_at == null ? '播放完成时间未记录' : `本机播放完成 ${formatTime(reply.played_at)}`,
        `问：${reply.question}`, `答：${reply.answer}`,
      );
    }
    if (session.failure_reason) lines.push('场次失败原因：' + session.failure_reason);
    const actions = [...advice_actions];
    for (const entry of advice_acknowledgments) {
      if (!advice_actions.some(action => action.action === 'acknowledge' &&
          action.occurred_at === entry.acknowledged_at && JSON.stringify(action.advice) === JSON.stringify(entry.advice))) {
        actions.push({advice:entry.advice, action:'acknowledge', occurred_at:entry.acknowledged_at});
      }
      if (entry.revoked_at != null && !advice_actions.some(action => action.action === 'revoke' &&
          action.occurred_at === entry.revoked_at && JSON.stringify(action.advice) === JSON.stringify(entry.advice))) {
        actions.push({advice:entry.advice, action:'revoke', occurred_at:entry.revoked_at});
      }
    }
    actions.sort((first, second) => first.occurred_at - second.occurred_at);
    for (const entry of actions) {
      const action = entry.action === 'revoke' ? '已撤销核对' : '已核对运营提醒';
      lines.push(`${formatTime(entry.occurred_at)} · ${action} · ${entry.advice.evidence}`);
    }
    if (missing.length) lines.push('数据缺口：' + missing.map(key => labels[key] ?? key).join('、'));
    const faultIds = new Set(rotation_faults.map(fault => fault.event_id));
    for (const finding of review.findings) {
      if (faultIds.has(finding.evidence.event_id)) {
        lines.push(`轮播故障 ${finding.evidence.event_id} · 复测建议：${finding.recommendation}`);
      }
    }
    for (const group of review.repeated_questions) {
      const title = savedProducts.find(product => product.id === group.product_id)?.title ?? group.product_id;
      lines.push(`${title} · 重复问题 ${group.evidence.length} 次：${group.question}`,
        '对应问答任务：' + group.evidence.map(item => item.task_id).join('、'),
        '下场准备建议：' + group.recommendation);
    }
    if (review.replies_without_playback_record.length) {
      lines.push('待核对播放结果的问答');
      for (const reply of review.replies_without_playback_record) {
        lines.push(`${formatTime(reply.queued_at)} · ${reply.question} · 任务 ${reply.task_id}`);
      }
    }
    for (const reply of review.unqueued_replies) {
      const status = reply.status === 'cancelled' ? '回复取消' : '回复失败';
      lines.push(`${formatTime(reply.occurred_at)} · ${status} · 记录 ${reply.event_id} · ${reply.question} · ${reply.reason}`);
    }
    output.replaceChildren(...lines.map(line => {
      const paragraph = document.createElement('p');
      paragraph.textContent = line;
      return paragraph;
    }));
    if (queued_replies.length) {
      const reviewSummary = document.createElement('p');
      const updateSummary = () => {
        const correct = queued_replies.filter(reply => reply.verdict === 'correct').length;
        const incorrect = queued_replies.filter(reply => reply.verdict === 'incorrect').length;
        const uncertain = queued_replies.filter(reply => reply.verdict === 'uncertain').length;
        const timed = queued_replies.filter(reply => reply.review_seconds != null);
        const rate = correct + incorrect ? `${(100 * correct / (correct + incorrect)).toFixed(1)}%` : '未知';
        const seconds = timed.reduce((total, reply) => total + reply.review_seconds, 0);
        reviewSummary.textContent = `答复复核 ${correct + incorrect + uncertain}/${queued_replies.length} 条 · 正确率 ${rate}（已判定 ${correct + incorrect} 条）· 不确定 ${uncertain} 条 · 已记录用时 ${timed.length ? seconds + ' 秒' : '未知'}（${timed.length} 条）`;
      };
      updateSummary();
      output.append(reviewSummary);
      for (const reply of queued_replies) {
        const form = document.createElement('form');
        const verdict = document.createElement('select');
        verdict.required = true;
        verdict.append(new Option('请选择', ''), new Option('正确', 'correct'),
          new Option('错误', 'incorrect'), new Option('不确定', 'uncertain'));
        verdict.value = reply.verdict ?? '';
        const verdictLabel = document.createElement('label');
        verdictLabel.append(`复核答复：${reply.question} · 任务 ${reply.task_id}`, verdict);
        const time = document.createElement('input');
        time.type = 'number';
        time.min = '0';
        time.max = '86400';
        time.step = '1';
        time.value = reply.review_seconds ?? '';
        const timeLabel = document.createElement('label');
        timeLabel.append('人工核对用时（秒，可留空）', time);
        const button = document.createElement('button');
        button.type = 'submit';
        button.textContent = '保存答复复核';
        const feedback = document.createElement('p');
        feedback.setAttribute('role', 'status');
        form.append(verdictLabel, timeLabel, button, feedback);
        form.addEventListener('submit', async event => {
          event.preventDefault();
          if (button.disabled || consoleClosed) return;
          button.disabled = true;
          const payload = {session_id:sessionId, task_id:reply.task_id, verdict:verdict.value,
            review_seconds:time.value === '' ? null : time.valueAsNumber};
          try {
            await request('/api/live/reply-review', payload);
            reply.verdict = payload.verdict;
            reply.review_seconds = payload.review_seconds;
            updateSummary();
            feedback.textContent = '复核已保存';
          } catch (error) {
            feedback.textContent = error.message;
          } finally {
            button.disabled = false;
          }
        });
        output.append(form);
      }
    }
    const baselineStatus = document.createElement('p');
    const showBaseline = baseline => {
      baselineStatus.textContent = `人工排品基线 · ${formatTime(Date.parse(baseline.captured_at) / 1000)} · ` +
        baseline.lineup.map(item => `${item.title}（版本 ${item.version}）`).join(' → ');
    };
    if (lineup_baseline) {
      showBaseline(lineup_baseline);
      output.append(baselineStatus);
    } else if (session.started_at != null && session.ended_at != null) {
      const bind = document.createElement('button');
      bind.type = 'button';
      bind.textContent = '关联已保存的人工排品基线';
      baselineStatus.setAttribute('role', 'status');
      bind.addEventListener('click', async () => {
        if (bind.disabled || consoleClosed) return;
        bind.disabled = true;
        try {
          const {lineup_baseline: baseline} = await request(preparationRoute + '/trial', {session_id:sessionId});
          showBaseline(baseline);
          bind.remove();
        } catch (error) {
          baselineStatus.textContent = error.message;
          bind.disabled = false;
        }
      });
      output.append(bind, baselineStatus);
    }
    const evidence = new Map();
    for (const group of review.repeated_questions) {
      for (const reply of group.evidence) evidence.set(reply.task_id, group.question);
    }
    for (const reply of review.replies_without_playback_record) {
      evidence.set(reply.task_id, reply.question);
    }
    for (const task of improvements.tasks) {
      if (task.reply_task_id && !evidence.has(task.reply_task_id)) {
        evidence.set(task.reply_task_id, task.reason);
      }
    }
    const sources = [
      ...rotation_faults.map(fault => ['fault_id', fault.event_id, `故障 ${fault.event_id}`]),
      ...Array.from(evidence, ([id, question]) => ['reply_task_id', id, `答复 ${id} · ${question}`]),
    ];
    for (const [field, id, label] of sources) {
      const task = improvements.tasks.find(item => item[field] === id);
      const form = document.createElement('form');
      const heading = document.createElement('h4');
      heading.textContent = `${label}的改进任务`;
      const owner = document.createElement('input');
      owner.required = true;
      owner.maxLength = 120;
      owner.value = task?.owner ?? '';
      const goal = document.createElement('textarea');
      goal.required = true;
      goal.maxLength = 2000;
      goal.value = task?.goal ?? '';
      const ownerLabel = document.createElement('label');
      ownerLabel.append('负责人', owner);
      const goalLabel = document.createElement('label');
      goalLabel.append('改进目标', goal);
      const button = document.createElement('button');
      button.type = 'submit';
      button.textContent = '保存改进任务';
      const status = document.createElement('p');
      status.setAttribute('role', 'status');
      const adopted = document.createElement('input');
      adopted.type = 'checkbox';
      adopted.checked = task?.adopted ?? false;
      const adoptedLabel = document.createElement('label');
      adoptedLabel.append(adopted, ' 纳入直播准备包');
      form.append(heading, ownerLabel, goalLabel, adoptedLabel, button, status);
      form.addEventListener('submit', async event => {
        event.preventDefault();
        if (button.disabled || consoleClosed) return;
        button.disabled = true;
        status.textContent = '';
        try {
          await request('/api/live/improvements', {
            session_id:sessionId, [field]:id, owner:owner.value, goal:goal.value,
            adopted:adopted.checked,
          });
          status.textContent = '改进任务已保存';
        } catch (error) {
          status.textContent = error.message;
        } finally {
          button.disabled = false;
        }
      });
      output.append(form);
    }
  } catch (error) {
    output.replaceChildren();
    throw error;
  }
}));
$('live-event-refresh').addEventListener('click', () => liveAction(async () => {
  const select = $('live-event-scene');
  const selected = select.value;
  const {sessions} = await request('/api/live/history');
  for (const id of ['live-baseline', 'live-trial']) {
    const input = $(id);
    const previous = input.value;
    input.replaceChildren(new Option('请选择', ''), ...sessions.filter(session => session.ended_at != null)
      .map(session => new Option(`${new Date(session.requested_at * 1000).toLocaleString()} · ${session.session_id}`, session.session_id)));
    input.value = Array.from(input.options).some(option => option.value === previous) ? previous : '';
  }
  select.replaceChildren(new Option('当前场次', ''), ...sessions.map(session =>
    new Option(`${new Date(session.requested_at * 1000).toLocaleString()} · ${session.session_id}`, session.session_id)));
  select.value = sessions.some(session => session.session_id === selected) ? selected : '';
  if (select.value !== selected) resetRotationEvents();
}));
$('live-compare-form').addEventListener('change', () => $('live-comparison').replaceChildren());
$('live-compare-form').addEventListener('submit', event => {
  event.preventDefault();
  liveAction(async () => {
    const baseline = $('live-baseline').value;
    const trial = $('live-trial').value;
    const output = $('live-comparison');
    output.replaceChildren();
    if (baseline === trial) throw new Error('请选择两个不同场次');
    const comparison = await request('/api/live/compare?' + new URLSearchParams({baseline, trial}));
    if (baseline !== $('live-baseline').value || trial !== $('live-trial').value) return;
    const lines = ['baseline', 'trial'].flatMap(role => {
      const result = comparison[role];
      const label = role === 'baseline' ? '基线' : '试验';
      const duration = result.duration_seconds == null ? '未知' : `${result.duration_seconds.toFixed(1)} 秒`;
      const rate = result.completed_segments_per_minute == null ? '未知' : result.completed_segments_per_minute.toFixed(2);
      const summary = `${label} · 时长 ${duration} · 输出 ${result.session.frames} 帧 · 已播 ${result.completed_segments} 段（每分钟 ${rate}）· 轮播故障 ${result.rotation_faults} 次 · 本机已播问答 ${result.played_replies} 条`;
      const products = result.products.map(item => {
        const title = savedProducts.find(product => product.id === item.product_id)?.title ?? item.product_id;
        return `${label} · ${title} · 商品版本 ${item.product_version} · 话术 ${item.script_id} · 已播 ${item.completed_segments} 段`;
      });
      return [summary, ...products];
    });
    const gaps = {audience:'人群', traffic:'流量', promotion:'活动', refund_lag:'退款滞后'};
    lines.push('结论：不确定', '待补数据：' + comparison.missing.map(key => gaps[key] ?? key).join('、'));
    output.replaceChildren(...lines.map(line => {
      const item = document.createElement('p');
      item.textContent = line;
      return item;
    }));
  });
});
$('live-rotation-events').addEventListener('click', () => liveAction(async () => {
  const sessionId = $('live-event-scene').value || liveSession.id;
  const query = new URLSearchParams({session_id:sessionId, after:String(rotationEventCursor)});
  if ($('live-event-product').value) query.set('product_id', $('live-event-product').value);
  const taskId = $('live-event-task').value.trim();
  if (taskId) query.set('task_id', taskId);
  const [result, controls] = await Promise.all([
    request('/api/live/rotation/events?' + query),
    request('/api/live/control/events?' + new URLSearchParams({session_id:sessionId})),
  ]);
  if (($('live-event-scene').value || liveSession.id) !== sessionId) return;
  $('live-event-controls').replaceChildren(...controls.events.map(event => {
    const item = document.createElement('li');
    item.textContent = `${new Date(event.occurred_at * 1000).toLocaleString()} · ${event.manual ? '手动接管' : '恢复自动调度'}`;
    return item;
  }));
  const history = result.session;
  $('live-event-session').textContent = history?.ended_at
    ? `${liveLabels[history.status]} · ${history.frames} 帧 · ${new Date((history.started_at ?? history.requested_at) * 1000).toLocaleString()} 至 ${new Date(history.ended_at * 1000).toLocaleString()}`
    : history?.started_at
      ? `开播时间 ${new Date(history.started_at * 1000).toLocaleString()}`
      : '';
  $('live-rotation-events-list').append(...result.events.map(event => {
    const item = document.createElement('li');
    const product = savedProducts.find(product => product.id === event.product_id);
    const completed = new Date(event.completed_at).toLocaleString();
    const interval = Number.isInteger(event.sample_start) && Number.isInteger(event.sample_end)
      ? ` · 发送时间线 ${(event.sample_start / 24000).toFixed(2)}–${(event.sample_end / 24000).toFixed(2)} 秒`
      : '';
    item.textContent = `${completed} · ${product?.title || event.product_id} · 商品版本 ${event.product_version} · 第 ${event.segment_index + 1} 段${interval} · 话术 ${event.script_id} · 任务 ${event.task_id}`;
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = '查看口播来源';
    const sourceText = document.createElement('pre');
    sourceText.style.whiteSpace = 'pre-wrap';
    details.append(summary, sourceText);
    const draftButton = document.createElement('button');
    draftButton.type = 'button';
    draftButton.textContent = '生成短视频文案初稿';
    draftButton.hidden = true;
    const draftStatus = document.createElement('p');
    draftStatus.setAttribute('role', 'status');
    const draftLabel = document.createElement('label');
    draftLabel.hidden = true;
    const draftText = document.createElement('textarea');
    draftText.rows = 8;
    draftText.maxLength = 100000;
    draftLabel.append('短视频文案', draftText);
    const productionLabel = document.createElement('label');
    const productionSeconds = document.createElement('input');
    productionSeconds.type = 'number';
    productionSeconds.min = '0';
    productionSeconds.max = '2147483647';
    productionSeconds.step = '1';
    productionLabel.hidden = true;
    productionLabel.append('制作耗时（秒，选填）', productionSeconds);
    const baselineLabel = document.createElement('label');
    const baselineSeconds = productionSeconds.cloneNode();
    baselineLabel.hidden = true;
    baselineLabel.append('同一短视频的人工基线耗时（秒，选填）', baselineSeconds);
    const saveDraft = document.createElement('button');
    saveDraft.type = 'button';
    saveDraft.textContent = '保存文案';
    saveDraft.hidden = true;
    const withdrawDraft = document.createElement('button');
    withdrawDraft.type = 'button';
    withdrawDraft.textContent = '停止复用';
    withdrawDraft.hidden = true;
    details.append(draftButton, draftStatus, draftLabel, productionLabel, baselineLabel, saveDraft, withdrawDraft);
    const params = new URLSearchParams({session_id:sessionId, task_id:event.task_id});
    const scheduleForm = document.createElement('form');
    scheduleForm.hidden = true;
    const scheduleFields = {};
    for (const [key, label, limit] of [
      ['account', '目标发布账号', 120], ['audience', '发布范围', 120], ['publish_at', '发布时间（含时区）', 64],
    ]) {
      const input = document.createElement('input');
      input.required = true;
      input.maxLength = limit;
      if (key === 'publish_at') input.placeholder = '2027-01-01T09:00:00+08:00';
      const field = document.createElement('label');
      field.append(label, input);
      scheduleForm.append(field);
      scheduleFields[key] = input;
    }
    const scheduleSave = document.createElement('button');
    scheduleSave.type = 'submit';
    scheduleSave.textContent = '保存本机排期';
    const scheduleStatus = document.createElement('p');
    scheduleStatus.setAttribute('role', 'status');
    const revisionStatus = document.createElement('p');
    scheduleForm.append(scheduleSave, scheduleStatus, revisionStatus);
    function showRevisionCount(schedule) {
      revisionStatus.textContent = !schedule ? '' : schedule.revision_count == null
        ? '历史改稿次数未记录' : `已保存改稿 ${schedule.revision_count} 次`;
    }
    details.append(scheduleForm);
    const receiptForm = document.createElement('form');
    receiptForm.hidden = true;
    const receiptId = document.createElement('input');
    receiptId.required = true;
    receiptId.maxLength = 200;
    const receiptLabel = document.createElement('label');
    receiptLabel.append('人工发布后的平台作品编号', receiptId);
    const receiptSave = document.createElement('button');
    receiptSave.type = 'submit';
    receiptSave.textContent = '登记发布结果';
    const receiptStatus = document.createElement('p');
    receiptStatus.setAttribute('role', 'status');
    receiptForm.append(receiptLabel, receiptSave, receiptStatus);
    details.append(receiptForm);
    function showPublicationReceipt(schedule) {
      receiptForm.hidden = !schedule;
      receiptId.value = schedule?.publication_id ?? '';
      const recorded = Boolean(schedule?.publication_id);
      const blocked = schedule?.withdrawn ? '文案已停止复用，不能登记新的发布结果'
        : schedule && !schedule.draft_matches ? '文案已修改，重新保存排期后可登记发布结果' : '';
      receiptId.readOnly = recorded || Boolean(blocked);
      receiptSave.hidden = receiptId.readOnly;
      receiptStatus.textContent = recorded ? '平台作品编号已人工登记' : blocked;
      if (recorded) scheduleSave.disabled = true;
    }
    receiptForm.addEventListener('submit', async event => {
      event.preventDefault();
      if (receiptSave.disabled || receiptSave.hidden || consoleClosed) return;
      receiptSave.disabled = true;
      try {
        const {schedule} = await request('/api/live/content-receipt', {
          session_id:sessionId, task_id:params.get('task_id'), publication_id:receiptId.value,
        });
        showPublicationReceipt(schedule);
      } catch (error) {
        receiptStatus.textContent = error.message;
      } finally {
        receiptSave.disabled = false;
      }
    });
    async function loadSchedule() {
      scheduleForm.hidden = false;
      scheduleSave.disabled = true;
      try {
        const {schedule, facts_review} = await request('/api/live/content-schedule?' + params);
        showRevisionCount(schedule);
        for (const [key, input] of Object.entries(scheduleFields)) input.value = schedule?.[key] ?? '';
        scheduleStatus.textContent = schedule && !schedule.draft_matches ? '文案已修改，请重新核对并保存排期' : '';
        scheduleSave.disabled = facts_review !== 'version_current' || Boolean(schedule?.withdrawn);
        if (schedule?.withdrawn) scheduleStatus.textContent = '文案已停止复用，排期仅供查看';
        else if (scheduleSave.disabled) scheduleStatus.textContent = '商品事实已变化，排期仅供查看';
        showPublicationReceipt(schedule);
      } catch (error) {
        scheduleStatus.textContent = error.message;
      }
    }
    scheduleForm.addEventListener('submit', async event => {
      event.preventDefault();
      if (scheduleSave.disabled || consoleClosed) return;
      scheduleSave.disabled = true;
      try {
        const fields = Object.fromEntries(Object.entries(scheduleFields).map(([key, input]) => [key, input.value]));
        const {schedule} = await request('/api/live/content-schedule', {
          session_id:sessionId, task_id:params.get('task_id'), ...fields,
        });
        scheduleFields.publish_at.value = schedule.publish_at;
        showRevisionCount(schedule);
        scheduleStatus.textContent = '本机排期已保存，等待人工发布';
        showPublicationReceipt(schedule);
      } catch (error) {
        scheduleStatus.textContent = error.message;
      } finally {
        scheduleSave.disabled = receiptId.readOnly;
      }
    });
    saveDraft.addEventListener('click', async () => {
      if (saveDraft.disabled || consoleClosed) return;
      saveDraft.disabled = true;
      try {
        if (!productionSeconds.reportValidity() || !baselineSeconds.reportValidity()) return;
        const payload = {session_id:sessionId, task_id:event.task_id, body:draftText.value};
        for (const [field, input] of Object.entries({
          production_seconds: productionSeconds, baseline_seconds: baselineSeconds,
        })) {
          if (input.value !== input.defaultValue) payload[field] = input.value === '' ? null : input.valueAsNumber;
        }
        await request('/api/live/content-draft', payload);
        for (const [field, input] of Object.entries({
          production_seconds: productionSeconds, baseline_seconds: baselineSeconds,
        })) {
          if (Object.hasOwn(payload, field)) input.defaultValue = payload[field] ?? '';
        }
        draftStatus.textContent = '文案已保存';
        withdrawDraft.hidden = false;
        await loadSchedule();
      } catch (error) {
        draftStatus.textContent = error.message;
      } finally {
        saveDraft.disabled = false;
      }
    });
    let reuseNarration = null;
    withdrawDraft.addEventListener('click', async () => {
      if (withdrawDraft.disabled || consoleClosed) return;
      withdrawDraft.disabled = true;
      try {
        await request('/api/live/content-withdraw', {session_id:sessionId, task_id:event.task_id});
        draftText.readOnly = true;
        saveDraft.hidden = true;
        productionLabel.hidden = true;
        baselineLabel.hidden = true;
        withdrawDraft.hidden = true;
        if (reuseNarration) reuseNarration.hidden = true;
        await loadSchedule();
        scheduleSave.disabled = true;
        draftStatus.textContent = '文案已停止复用，仅供回查';
      } catch (error) {
        draftStatus.textContent = error.message;
      } finally {
        withdrawDraft.disabled = false;
      }
    });
    draftButton.addEventListener('click', async () => {
      if (draftButton.disabled || consoleClosed) return;
      draftButton.disabled = true;
      draftStatus.textContent = '正在生成文案初稿';
      try {
        const {draft} = await request('/api/live/content-draft?' + params);
        draftText.value = draft.saved_body ?? [`标题：${draft.title}`, `封面文字：${draft.cover_text}`,
          `语言：${draft.language ?? '未记录'}`, '', draft.narration].join('\n');
        draftLabel.hidden = false;
        draftText.readOnly = !draft.editable;
        saveDraft.hidden = !draft.editable;
        productionLabel.hidden = !draft.editable;
        baselineLabel.hidden = !draft.editable;
        productionSeconds.value = draft.production_seconds ?? '';
        baselineSeconds.value = draft.baseline_seconds ?? '';
        productionSeconds.defaultValue = productionSeconds.value;
        baselineSeconds.defaultValue = baselineSeconds.value;
        draftButton.hidden = true;
        withdrawDraft.hidden = draft.saved_body == null || Boolean(draft.withdrawn);
        draftStatus.textContent = draft.withdrawn ? '文案已停止复用，仅供回查'
          : draft.editable ? [
            draft.speaker_role === 'assistant' ? '原口播为助播' : '原口播为主播',
            draft.source.voice_id ? `原音色 ${draft.source.voice_id}` : '原音色未记录',
          ].join(' · ') : '原商品或话术事实已变化，历史文案仅供核对';
        if (draft.saved_body != null) await loadSchedule();
        if (draft.withdrawn) scheduleSave.disabled = true;
        if (draft.editable) {
          const reuse = document.createElement('button');
          reuseNarration = reuse;
          reuse.type = 'button';
          reuse.textContent = '将原口播载入话术编辑器';
          reuse.addEventListener('click', async () => {
            if (consoleClosed || reuse.disabled || reuse.hidden) return;
            reuse.disabled = true;
            try {
              const {draft: latest} = await request('/api/live/content-draft?' + params);
              if (consoleClosed || reuse.hidden) return;
              if (!latest.editable) {
                reuse.hidden = true;
                draftStatus.textContent = '此文案已停止复用或原商品事实已变化';
                return;
              }
              if (currentProduct?.id !== latest.source.product_id ||
                  currentProduct.version !== latest.source.product_version) {
                draftStatus.textContent = '请先在商品与话术中打开对应版本的商品';
                return;
              }
              const editor = $('script-text');
              if (editor.value.trim()) {
                draftStatus.textContent = '请先处理话术编辑器中尚未保存的内容';
                return;
              }
              editor.value = latest.narration;
              parentScriptId = latest.source.script_id;
              editor.focus();
            } catch (error) {
              draftStatus.textContent = error.message;
            } finally {
              reuse.disabled = false;
            }
          });
          draftLabel.before(reuse);
        }
        if (draft.subtitle_srt) {
          const subtitleLabel = document.createElement('label');
          const subtitle = document.createElement('textarea');
          subtitle.rows = 4;
          subtitle.readOnly = true;
          subtitle.value = draft.subtitle_srt;
          subtitleLabel.append('原口播片段字幕（SRT）', subtitle);
          const downloadSubtitle = document.createElement('button');
          downloadSubtitle.type = 'button';
          downloadSubtitle.textContent = '下载原口播字幕';
          downloadSubtitle.addEventListener('click', () => {
            const url = URL.createObjectURL(new Blob([draft.subtitle_srt], {type:'text/plain;charset=utf-8'}));
            const link = document.createElement('a');
            link.href = url;
            link.download = `口播-${event.task_id.replace(/[^a-zA-Z0-9_-]/g, '_')}.srt`;
            link.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          });
          details.append(subtitleLabel, downloadSubtitle);
        }
      } catch (error) {
        draftStatus.textContent = error.message;
      } finally {
        draftButton.disabled = false;
      }
    });
    item.append(details);
    let loaded = false;
    let loading = false;
    details.addEventListener('toggle', async () => {
      if (!details.open || loaded || loading || consoleClosed) return;
      loading = true;
      sourceText.textContent = '正在读取口播来源';
      try {
        const {source} = await request('/api/live/content-source?' + params);
        draftButton.hidden = !source.has_saved_draft &&
          (source.facts_review !== 'version_current' || source.segment == null);
        if (source.has_saved_draft) draftButton.textContent = '打开已保存的短视频文案';
        const snapshot = source.product_snapshot;
        const speech = source.speech_provenance;
        const speechDetails = [
          source.voice_id ? `原口播音色 ${source.voice_id}` : '原口播音色未记录',
          speech?.engine && `语音引擎 ${speech.engine}`,
          speech?.language && `合成语言 ${speech.language}`,
          speech?.voice_audio_sha256 && `参考音频 SHA-256 ${speech.voice_audio_sha256}`,
          speech?.voice_text_sha256 && `参考文本 SHA-256 ${speech.voice_text_sha256}`,
        ].filter(Boolean);
        const review = {source_missing:'缺少原始证据，复用前需核对', product_changed:'商品版本已更新，复用前需核对',
          facts_changed:'商品事实已变化，复用前需核对', version_current:'商品版本及话术事实仍有效'};
        sourceText.textContent = snapshot
          ? [`商品快照 · ${snapshot.title} · 版本 ${snapshot.version}`, review[source.facts_review], snapshot.content,
            ...speechDetails,
            '', '按原话术还原的片段', source.segment?.content ?? '片段文本无法还原',
            '', '原话术全文', source.script_text].join('\n')
          : '这条口播记录缺少原商品快照或话术。';
        loaded = true;
      } catch (error) {
        sourceText.textContent = error.message + '。关闭并重新展开可重试。';
      } finally {
        loading = false;
      }
    });
    return item;
  }));
  rotationEventCursor = result.next_cursor;
  $('live-rotation-events-status').textContent = result.events.length
    ? `已读取 ${result.events.length} 条记录`
    : (rotationEventCursor ? '暂无更多记录' : '该场次暂无口播完成记录');
  if (rotationEventCursor) $('live-rotation-events').textContent = '读取后续口播记录';
}));
$('live-devices').addEventListener('click', () => liveAction(async () => {
  const {devices} = await request('/api/live/devices');
  const selected = $('live-audio').value;
  $('live-audio').replaceChildren(new Option('请选择设备',''), ...devices.map(device => new Option(`${device.name} · ${device.host}`,device.id)));
  $('live-audio').value = devices.some(device => String(device.id) === selected) ? selected : '';
}));
$('live-start').addEventListener('click', () => liveAction(() => {
  const audio_device = Number($('live-audio').value);
  const video_path = $('live-video-path').value.trim();
  const payload = video_path ? {audio_device, video_path, video_backend:$('live-video-backend').value} : {
    audio_device, rotation_language:$('tts-language').value,
    assistant_voice_id:$('live-assistant-voice').value || null
  };
  return request('/api/live/start', payload);
}));
$('live-stop').addEventListener('click', () => liveAction(() => request('/api/live/stop',{session_id:liveSession.id})));
$('live-video-jump').addEventListener('click', () => {
  const position = $('live-video-position');
  if (!position.reportValidity() || !position.value) return;
  return liveAction(() => request('/api/live/video-seek',{
    session_id:liveSession.id, position_ms:Math.round(Number(position.value)*1000)
  }));
});
async function enqueueLive(path) {
  requireSavedProduct();
  if (ttsState?.status !== 'succeeded' || ttsState.id !== ttsPreviewTask) throw new Error('请先合成当前话术的语音');
  const value = {session_id:liveSession.id,task_id:ttsState.id};
  if (path === '/api/live/speak') value.revision = liveSession.control_revision;
  await request(path,value);
}
$('live-enqueue').addEventListener('click', () => liveAction(() => enqueueLive('/api/live/enqueue')));
$('live-insert').addEventListener('click', () => liveAction(() => enqueueLive('/api/live/insert')));
$('live-speak').addEventListener('click', () => liveAction(() => enqueueLive('/api/live/speak')));
$('live-control').addEventListener('click', () => liveAction(() => request('/api/live/control', {
  session_id:liveSession.id, manual:!liveSession.manual, revision:liveSession.control_revision
})));
window.addEventListener('pagehide', () => clearTimeout(liveTimer));
let taobaoState = {status:'idle'}, taobaoReply = {}, taobaoTimer, taobaoBusy = false;
function renderTaobao() {
  const active = ['login','connecting','capturing','reconnecting','stopping'].includes(taobaoState.status);
  const disabled = consoleClosed || taobaoBusy;
  $('taobao-login').disabled = disabled || active;
  $('taobao-start').disabled = disabled || active || !taobaoState.saved_login || !/^[0-9]{1,30}$/.test($('taobao-live-id').value);
  $('taobao-stop').disabled = disabled || !active || taobaoState.status === 'stopping';
  $('taobao-auto-reply').disabled = disabled || (!taobaoReply.automatic && taobaoState.status !== 'capturing');
  $('taobao-auto-reply').textContent = taobaoReply.automatic ? '关闭自动回复' : '开启自动回复';
  $('taobao-goods-refresh').disabled = disabled || taobaoState.status !== 'capturing';
  $('taobao-explain').disabled = $('taobao-goods-refresh').disabled || !$('taobao-goods').value;
}
async function loadTaobao() {
  clearTimeout(taobaoTimer);
  if (consoleClosed) return;
  const {capture, reply} = await request('/api/taobao/state');
  if (taobaoState.capture_id !== capture.capture_id || capture.status !== 'capturing') {
    $('taobao-goods').replaceChildren(new Option('请选择商品',''));
    $('taobao-goods-status').textContent = '';
  }
  taobaoState = capture;
  taobaoReply = reply;
  const labels = {idle:'等待登录或采集',login:'请在浏览器完成登录',signed_in:'登录状态已保存',connecting:'正在连接场次',capturing:`已采集 ${taobaoState.count} 条新评论`,reconnecting:`正在重连（第 ${capture.reconnects} 次）`,stopping:'正在停止',stopped:'已停止',failed:'操作失败',login_required:'请重新登录'};
  $('taobao-status').textContent = labels[taobaoState.status];
  $('taobao-error').textContent = taobaoState.error || reply.automatic_error || '';
  const replyLabels = {generating:'正在生成回复',synthesizing:'正在合成回复语音',queued:'回复已加入优先队列',cancelled:'回复已取消',failed:'回复失败'};
  $('taobao-reply').textContent = [replyLabels[reply.status], reply.text || reply.error].filter(Boolean).join(' · ');
  $('taobao-comments').replaceChildren(...taobaoState.comments.map(comment => {
    const item = document.createElement('li');
    item.textContent = `${comment.nickname} ${comment.time} · ${comment.content}`;
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = '生成并播报';
    button.disabled = taobaoState.status !== 'capturing' || ['generating','synthesizing'].includes(reply.status);
    button.addEventListener('click', () => taobaoAction('/api/taobao/reply', {capture_id:capture.capture_id,comment_id:comment.id}));
    item.append(' ', button);
    return item;
  }));
  renderTaobao();
  if (['login','connecting','capturing','reconnecting','stopping'].includes(taobaoState.status) || ['generating','synthesizing'].includes(reply.status) || reply.automatic) {
    taobaoTimer = setTimeout(() => loadTaobao().catch(error => {$('taobao-error').textContent = error.message;}), 1000);
  }
}
async function taobaoAction(path, value) {
  if (consoleClosed || taobaoBusy) return;
  taobaoBusy = true;
  renderTaobao();
  try { await request(path, value); await loadTaobao(); }
  catch (error) { $('taobao-error').textContent = error.message; }
  finally { taobaoBusy = false; renderTaobao(); }
}
$('taobao-live-id').addEventListener('input', renderTaobao);
$('taobao-login').addEventListener('click', () => taobaoAction('/api/taobao/login', {}));
$('taobao-start').addEventListener('click', () => taobaoAction('/api/taobao/start', {live_id:$('taobao-live-id').value}));
$('taobao-stop').addEventListener('click', () => taobaoAction('/api/taobao/stop', {}));
$('taobao-auto-reply').addEventListener('click', () => taobaoAction('/api/taobao/auto-reply', {enabled:!taobaoReply.automatic}));
$('taobao-goods').addEventListener('change', renderTaobao);
async function taobaoGoods(explain) {
  if (taobaoBusy || consoleClosed) return;
  taobaoBusy = true;
  renderTaobao();
  const captureId = taobaoState.capture_id;
  const goodsId = $('taobao-goods').value;
  try {
    const result = await request(explain ? '/api/taobao/explain' : '/api/taobao/goods',
      explain ? {capture_id:captureId, goods_id:goodsId} : {capture_id:captureId});
    await loadTaobao();
    if (taobaoState.capture_id !== captureId || taobaoState.status !== 'capturing') return;
    if (explain) $('taobao-goods-status').textContent = `已开始讲解商品 ${result.goods_id}`;
    else $('taobao-goods').replaceChildren(new Option('请选择商品',''),
      ...result.items.map(item => new Option(`${item.name} · ${item.id}`,item.id)));
  } catch (error) { $('taobao-goods-status').textContent = error.message; }
  finally { taobaoBusy = false; renderTaobao(); }
}
$('taobao-goods-refresh').addEventListener('click', () => taobaoGoods(false));
$('taobao-explain').addEventListener('click', () => taobaoGoods(true));
window.addEventListener('pagehide', () => clearTimeout(taobaoTimer));
action(async () => { await load(); await productAction(async () => { await loadProducts(); await loadTask(); }); await loadPreparation(); await voiceAction(loadVoices);await ttsAction(loadTTS);await avatarAction(loadAvatars);await avatarVideoAction(loadAvatarVideo);await renderAction(loadRender);await loadLive();await loadTaobao(); });
