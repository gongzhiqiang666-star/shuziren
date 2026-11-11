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
}
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
async function loadProducts() {
  const result = await request('/api/products'); savedProducts = result.products;
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
  $('live-rotation-events').textContent = '查看本场口播记录';
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
  $('live-control').disabled = consoleClosed || liveBusy || liveSession.status !== 'running';
  $('live-control').textContent = liveSession.manual ? '恢复自动调度' : '手动接管';
  $('live-speak').disabled = $('live-control').disabled || !liveSession.manual;
  $('live-rotation-start').disabled = $('live-control').disabled || !$('live-products').selectedOptions.length;
  $('live-rotation-start').textContent = liveSession.rotation_error ? '重试商品轮播' : '开始商品轮播';
  $('live-rotation-stop').disabled = $('live-control').disabled || !liveSession.rotation_products?.length;
  $('live-rotation-events').disabled = consoleClosed || liveBusy || !liveSession.id;
  $('live-event-product').disabled = $('live-rotation-events').disabled;
  $('live-event-task').disabled = $('live-rotation-events').disabled;
  $('live-enqueue').disabled = $('live-control').disabled || !!liveSession.manual;
  $('live-insert').disabled = $('live-enqueue').disabled;
  $('live-audio').disabled = active || liveBusy;
  $('live-assistant-voice').disabled = consoleClosed || active || liveBusy;
}
async function loadLive() {
  clearTimeout(liveTimer);
  if (consoleClosed) return;
  const previousSession = liveSession.id;
  liveSession = (await request('/api/live/state')).session;
  if (previousSession !== liveSession.id) resetRotationEvents();
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
  $('live-detail').textContent = liveSession.frames ? `已提交 ${liveSession.frames} 帧，待播 ${liveSession.pending ?? 0} 条` : '';
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
$('live-products').addEventListener('change', () => { rotationSelectionEdited = true; renderShiftFields(); renderLiveButtons(); });
$('live-shifts-enabled').addEventListener('change', renderShiftFields);
$('live-rotation-start').addEventListener('click', () => liveAction(() => {
  const product_ids = Array.from($('live-products').selectedOptions, option => option.value);
  const payload = {session_id:liveSession.id, product_ids};
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
$('live-rotation-events').addEventListener('click', () => liveAction(async () => {
  const sessionId = liveSession.id;
  const query = new URLSearchParams({session_id:sessionId, after:String(rotationEventCursor)});
  if ($('live-event-product').value) query.set('product_id', $('live-event-product').value);
  const taskId = $('live-event-task').value.trim();
  if (taskId) query.set('task_id', taskId);
  const result = await request('/api/live/rotation/events?' + query);
  if (liveSession.id !== sessionId) return;
  $('live-rotation-events-list').append(...result.events.map(event => {
    const item = document.createElement('li');
    const product = savedProducts.find(product => product.id === event.product_id);
    const completed = new Date(event.completed_at).toLocaleString();
    item.textContent = `${completed} · ${product?.title || event.product_id} · 商品版本 ${event.product_version} · 第 ${event.segment_index + 1} 段 · 话术 ${event.script_id} · 任务 ${event.task_id}`;
    return item;
  }));
  rotationEventCursor = result.next_cursor;
  $('live-rotation-events-status').textContent = result.events.length
    ? `已读取 ${result.events.length} 条记录`
    : (rotationEventCursor ? '暂无更多记录' : '本场暂无口播完成记录');
  if (rotationEventCursor) $('live-rotation-events').textContent = '读取后续口播记录';
}));
$('live-devices').addEventListener('click', () => liveAction(async () => {
  const {devices} = await request('/api/live/devices');
  const selected = $('live-audio').value;
  $('live-audio').replaceChildren(new Option('请选择设备',''), ...devices.map(device => new Option(`${device.name} · ${device.host}`,device.id)));
  $('live-audio').value = devices.some(device => String(device.id) === selected) ? selected : '';
}));
$('live-start').addEventListener('click', () => liveAction(() => request('/api/live/start',{
  audio_device:Number($('live-audio').value), rotation_language:$('tts-language').value,
  assistant_voice_id:$('live-assistant-voice').value || null
})));
$('live-stop').addEventListener('click', () => liveAction(() => request('/api/live/stop',{session_id:liveSession.id})));
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
action(async () => { await load(); await productAction(async () => { await loadProducts(); await loadTask(); }); await voiceAction(loadVoices);await ttsAction(loadTTS);await avatarAction(loadAvatars);await avatarVideoAction(loadAvatarVideo);await renderAction(loadRender);await loadLive();await loadTaobao(); });
