'use strict';
const $ = id => document.getElementById(id);
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
  finally { document.querySelectorAll('button').forEach(b => b.disabled = false); }
}
async function load() {
  clearChecks();
  const session = await request('/api/session'); token = session.token;
  const state = await request('/api/state');
  $('runtime-root').value = state.config.runtime_root; $('port').value = state.config.port;
  $('live-status').textContent = state.live_status;
  $('data-directory').textContent = '配置目录：' + state.data_directory;
}
$('settings').addEventListener('submit', event => {event.preventDefault(); action(async () => {
  const result = await request('/api/config', config()); $('message').textContent = result.message;
});});
$('preflight').addEventListener('click', () => action(async () => {
  const result = await request('/api/preflight', config());
  $('scope').textContent = result.ready ? '必需文件均存在。尚未验证完整性、GPU、模型或直播。' : '资源不完整，请检查下列路径。';
  $('checks').replaceChildren(...result.checks.map(check => {
    const item = document.createElement('li'); item.textContent = (check.present ? '✓ ' : '缺失：') + check.path; return item;
  }));
}));
$('reload').addEventListener('click', () => action(load));
action(load);
