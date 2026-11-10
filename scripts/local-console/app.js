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
  $('live-status').textContent = '控制台已退出';
  $('message').textContent = '本地服务已收到退出请求，可以关闭本页。';
  $('settings').hidden = true; $('shutdown').hidden = true;
  $('products-panel').hidden = true;
}));
let currentProduct = null;
let savedProducts = [];
async function productAction(work) {
  $('product-error').textContent = ''; $('product-message').textContent = '';
  $('products-panel').querySelectorAll('button,select').forEach(b => b.disabled = true);
  try { await work(); } catch(error) { $('product-error').textContent = error.message || '商品服务连接失败'; }
  finally { $('products-panel').querySelectorAll('button,select').forEach(b => b.disabled = false); }
}
function showProduct(product) {
  currentProduct = product;
  $('product-index').value = product?.product_index ?? '';
  $('product-title').value = product?.title ?? '';
  $('product-content').value = product?.content ?? '';
  $('product-version').textContent = product ? '当前商品：' + product.title + ' · 版本 ' + product.version : '正在新增商品';
  $('script-text').value = ''; $('scripts-list').replaceChildren();
}
async function showScripts() {
  if (!currentProduct) return;
  const result = await request('/api/scripts?product_id=' + encodeURIComponent(currentProduct.id));
  $('scripts-list').replaceChildren(...result.scripts.map(script => {
    const item = document.createElement('li');
    item.textContent = '版本 ' + script.product_version + (script.product_version === currentProduct.version ? ' · 当前' : ' · 历史') + '：' + script.text;
    return item;
  }));
}
async function loadProducts() {
  const result = await request('/api/products'); savedProducts = result.products;
  const empty = document.createElement('option'); empty.value = ''; empty.textContent = '请选择商品';
  $('product-list').replaceChildren(empty, ...savedProducts.map(product => {
    const option = document.createElement('option'); option.value = product.id;
    option.textContent = product.product_index + ' · ' + product.title; return option;
  }));
  const selected = savedProducts.find(p => p.id === result.selected) || null;
  $('product-list').value = selected?.id || ''; showProduct(selected); await showScripts();
}
$('new-product').addEventListener('click', () => { $('product-list').value = ''; showProduct(null); });
$('reload-products').addEventListener('click', () => productAction(loadProducts));
$('product-list').addEventListener('change', () => productAction(async () => {
  const selected = savedProducts.find(p => p.id === $('product-list').value);
  if (!selected) { showProduct(null); return; }
  await request('/api/products/select', {product_id:selected.id}); showProduct(selected); await showScripts();
}));
$('product-form').addEventListener('submit', event => { event.preventDefault(); productAction(async () => {
  const value = {title:$('product-title').value, content:$('product-content').value, product_index:$('product-index').value};
  if (currentProduct) Object.assign(value, {product_id:currentProduct.id,version:currentProduct.version});
  const result = await request('/api/products', value);
  await request('/api/products/select', {product_id:result.product.id});
  await loadProducts(); $('product-message').textContent = '商品已保存';
}); });
$('script-form').addEventListener('submit', event => { event.preventDefault(); productAction(async () => {
  if (!currentProduct) throw new Error('请先保存或选择商品');
  if ($('product-title').value !== currentProduct.title || $('product-content').value !== currentProduct.content || $('product-index').value !== String(currentProduct.product_index))
    throw new Error('商品有未保存修改，请先保存商品');
  await request('/api/scripts', {snapshot:currentProduct,text:$('script-text').value});
  await showScripts(); $('script-text').value = ''; $('product-message').textContent = '话术已保存';
}); });
action(async () => { await load(); await productAction(loadProducts); });
