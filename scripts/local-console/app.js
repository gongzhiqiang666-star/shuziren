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
  finally { document.querySelectorAll('button').forEach(b => b.disabled = false); renderRecordingButtons(); renderTTSButtons(); }
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
  consoleClosed = true; clearTimeout(taskTimer);
  recorder.discard();
  clearTimeout(ttsTimer);clearTTSPreview();$('tts-panel').hidden=true;
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
let parentScriptId = null;
let currentTask = null;
let taskTimer = null;
let consoleClosed = false;
function requireSavedProduct() {
  if (!currentProduct) throw new Error('请先保存或选择商品');
  if ($('product-title').value !== currentProduct.title || $('product-content').value !== currentProduct.content || $('product-index').value !== String(currentProduct.product_index))
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
  $('product-version').textContent = product ? '当前商品：' + product.title + ' · 版本 ' + product.version : '正在新增商品';
  $('script-text').value = ''; $('scripts-list').replaceChildren();
}
async function showScripts() {
  if (!currentProduct) return;
  const result = await request('/api/scripts?product_id=' + encodeURIComponent(currentProduct.id));
  currentScriptId=result.selected;
  $('scripts-list').replaceChildren(...result.scripts.map(script => {
    const item = document.createElement('li');
    const content = document.createElement('p');
    content.textContent = '版本 ' + script.product_version + (script.product_version === currentProduct.version ? ' · 当前' : ' · 历史') + (script.id === result.selected ? ' · 已选用' : '') + (script.parent_script_id ? ' · 修改稿' : '') + '：' + script.text;
    const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'secondary'; edit.textContent = '载入修改';
    edit.addEventListener('click', () => {
      $('script-text').value = script.text; parentScriptId = script.id;
      $('product-message').textContent = script.product_version === currentProduct.version ? '原稿已载入，保存时创建修改稿并保留原稿。' : '历史原稿已载入，请按当前商品事实修改后保存；原稿会保留。';
    });
    item.append(content,edit);
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
$('reload-products').addEventListener('click', () => productAction(async () => { await loadProducts(); await loadTask(); }));
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
  const saved=currentProduct && $('product-title').value===currentProduct.title && $('product-content').value===currentProduct.content && $('product-index').value===String(currentProduct.product_index);
  const matches=ttsState?.status==='succeeded' && saved && ttsState.product_id===currentProduct.id && ttsState.script_id===currentScriptId && ttsState.voice_id===$('voice-list').value && ttsState.speed===Number($('tts-speed').value);
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
  await request('/api/tts/generate',{product_id:currentProduct.id,script_id:currentScriptId,voice_id:$('voice-list').value,speed:Number($('tts-speed').value),language:'zh-CN',use_cache:$('tts-use-cache').checked});
  await loadTTS();
}));
$('tts-cancel').addEventListener('click',()=>ttsAction(async()=>{
  if(!ttsState) throw new Error('暂无合成任务');
  await request('/api/tts/cancel',{task_id:ttsState.id});clearTTSPreview();await loadTTS();
}));
$('tts-refresh').addEventListener('click',()=>ttsAction(loadTTS));
$('tts-preview').addEventListener('error',()=>{if($('tts-preview').getAttribute('src')) $('tts-error').textContent='音频已失效或无法加载，请刷新任务状态。';});
for(const id of ['product-title','product-content','product-index']) $(id).addEventListener('input',clearTTSPreview);
$('tts-speed').addEventListener('input',clearTTSPreview);
window.addEventListener('pagehide',()=>{clearTimeout(ttsTimer);clearTTSPreview();});
renderTTSButtons();
action(async () => { await load(); await productAction(async () => { await loadProducts(); await loadTask(); }); await voiceAction(loadVoices);await ttsAction(loadTTS); });
