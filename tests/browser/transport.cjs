/* Real-browser/real-PostgreSQL transport acceptance.
 * Synthetic canvas and tone are TEST FIXTURES ONLY. This proves WebRTC transport
 * and output ownership, never avatar fidelity, real TTS quality or Taobao airing.
 * Refuses to use DATABASE_URL: an explicit disposable BROWSER_DATABASE_URL is required.
 */
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const http = require('node:http')
const net = require('node:net')
const crypto = require('node:crypto')
const { spawn, execFileSync } = require('node:child_process')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')

const root = path.resolve(__dirname, '../..')
const database = process.env.BROWSER_DATABASE_URL
assert(database, 'Set BROWSER_DATABASE_URL to an isolated PostgreSQL test database')
const schema = 'browser_' + crypto.randomBytes(10).toString('hex')
const work = fs.mkdtempSync(path.join(os.tmpdir(), 'shuziren-browser-'))
const token = crypto.randomBytes(32).toString('hex')
const ttsKey = crypto.randomBytes(32).toString('hex')
const binary = process.env.BROWSER_APP_BINARY || path.join(root, 'build/shuziren')
const artifactDir = process.env.BROWSER_ARTIFACT_DIR || path.join(root, 'test-results/browser')
const psql = process.env.PSQL_BINARY || 'psql'
const pgURL = new URL(database)
assert(['postgres:', 'postgresql:'].includes(pgURL.protocol), 'Use a PostgreSQL URL for the isolated test database')
const pgEnv = {...process.env}
for (const key of Object.keys(pgEnv)) if (key.startsWith('PG')) delete pgEnv[key]
Object.assign(pgEnv, {PGHOST: pgURL.hostname, PGPORT: pgURL.port || '5432', PGUSER: decodeURIComponent(pgURL.username), PGPASSWORD: decodeURIComponent(pgURL.password), PGDATABASE: decodeURIComponent(pgURL.pathname.slice(1)), PGSSLMODE: pgURL.searchParams.get('sslmode') || 'prefer', PGCONNECT_TIMEOUT: '5'})
const sql = command => execFileSync(psql, ['-X', '-v', 'ON_ERROR_STOP=1', '-q', '-c', command], {env: pgEnv, stdio: ['ignore', 'pipe', 'pipe']})
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
async function until(fn, description, timeout = 35000) {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) { if (await fn()) return; await sleep(250) }
  throw new Error('Timed out: ' + description)
}
async function port() { const s = net.createServer(); await new Promise(r => s.listen(0, '127.0.0.1', r)); const n = s.address().port; await new Promise(r => s.close(r)); return n }
function tone() { const frames=24000, b=Buffer.alloc(44+frames*2); b.write('RIFF'); b.writeUInt32LE(b.length-8,4); b.write('WAVEfmt ',8); b.writeUInt32LE(16,16); b.writeUInt16LE(1,20); b.writeUInt16LE(1,22); b.writeUInt32LE(24000,24); b.writeUInt32LE(48000,28); b.writeUInt16LE(2,32); b.writeUInt16LE(16,34); b.write('data',36); b.writeUInt32LE(frames*2,40); for(let i=0;i<frames;i++)b.writeInt16LE(Math.round(2400*Math.sin(2*Math.PI*440*i/24000)),44+i*2);return b }

let browser, provider, upstream, child, childLog='', created=false
let offers=0, uploads=0, interrupts=0, ttsCalls=0
const pageErrors=[]
;(async()=>{
  sql(`CREATE SCHEMA "${schema}"`); created=true
  browser=await chromium.launch({headless:true, executablePath:process.env.BROWSER_EXECUTABLE || undefined, args:['--no-sandbox','--autoplay-policy=no-user-gesture-required']})
  provider=await browser.newPage()
  await provider.setContent('<canvas id="c" width="640" height="360"></canvas>')
  await provider.evaluate(()=>{
    const canvas=document.querySelector('canvas'),ctx=canvas.getContext('2d');let n=0
    setInterval(()=>{ctx.fillStyle='#163427';ctx.fillRect(0,0,640,360);ctx.fillStyle='#eaff85';ctx.fillRect((n++*7)%600,140,40,80);ctx.fillStyle='white';ctx.font='20px sans-serif';ctx.fillText('SYNTHETIC TRANSPORT TEST',30,70);ctx.fillText('No avatar / no model quality claim',30,300)},40)
    window.fixtureVideo=canvas.captureStream(25);window.fixtureAudio=new AudioContext();window.fixtureDestination=window.fixtureAudio.createMediaStreamDestination();window.fixturePeers=new Map()
    // An actual silent media track until /humanaudio delivers the test tone.
    const oscillator=window.fixtureAudio.createOscillator(),gain=window.fixtureAudio.createGain();gain.gain.value=0;oscillator.connect(gain).connect(window.fixtureDestination);oscillator.start();window.fixtureAudio.resume()
  })
  upstream=http.createServer(async(req,res)=>{
    try {
      const chunks=[];for await(const b of req)chunks.push(b);const body=Buffer.concat(chunks)
      const send=(value,status=200)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(value))}
      if(req.url==='/healthz')return send({status:'ready',model_loaded:true,engine:'cosyvoice3',reason:'ready',engine_id:'a'.repeat(64)})
      if(req.url==='/synthesize'){assert.equal(req.headers.authorization,'Bearer '+ttsKey);ttsCalls++;res.writeHead(200,{'Content-Type':'audio/wav'});return res.end(tone())}
      if(req.url==='/offer'){
        offers++;const offer=JSON.parse(body);const sessionid=crypto.randomUUID()
        const answer=await provider.evaluate(async({offer,sessionid})=>{
          const pc=new RTCPeerConnection({iceServers:[]});window.fixturePeers.set(sessionid,pc)
          await pc.setRemoteDescription(offer)
          pc.addTrack(window.fixtureVideo.getVideoTracks()[0],window.fixtureVideo)
          pc.addTrack(window.fixtureDestination.stream.getAudioTracks()[0],window.fixtureDestination.stream)
          await pc.setLocalDescription(await pc.createAnswer())
          if(pc.iceGatheringState!=='complete')await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(new Error('fixture ICE timeout')),10000);pc.addEventListener('icegatheringstatechange',()=>{if(pc.iceGatheringState==='complete'){clearTimeout(timeout);resolve()} })})
          return {sdp:pc.localDescription.sdp,type:'answer',sessionid}
        },{offer,sessionid})
        return send(answer)
      }
      if(req.url==='/humanaudio'){
        uploads++;const response=new Response(body,{headers:{'Content-Type':req.headers['content-type']}});const form=await response.formData();assert(form.get('sessionid'));const wav=Buffer.from(await form.get('file').arrayBuffer());assert.equal(wav.subarray(0,4).toString(),'RIFF')
        await provider.evaluate(async(encoded)=>{const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));const buffer=await window.fixtureAudio.decodeAudioData(bytes.buffer);const source=window.fixtureAudio.createBufferSource();source.buffer=buffer;source.connect(window.fixtureDestination);source.start()},wav.toString('base64'))
        return send({code:0})
      }
      if(req.url==='/interrupt_talk'){interrupts++;return send({code:0})}
      return send({error:'test_fixture_unknown_route'},404)
    }catch(e){res.writeHead(500);res.end('test fixture failed');pageErrors.push('fixture: '+e.message)}
  })
  await new Promise(r=>upstream.listen(0,'127.0.0.1',r));const mediaURL='http://127.0.0.1:'+upstream.address().port
  const appPort=await port(),base='http://127.0.0.1:'+appPort
  const dsn=new URL(database);dsn.searchParams.set('search_path',schema)
  const env={...process.env};for(const name of Object.keys(env))if(/^(DEEPSEEK_|TAOBAO_|BGE_|TTS_|LIVETALKING_)/.test(name))delete env[name]
  Object.assign(env,{APP_ADDR:'127.0.0.1:'+appPort,APP_TOKEN:token,DATABASE_URL:dsn.href,WEB_DIST:path.join(root,'web/dist'),AUDIO_DIR:path.join(work,'audio'),TTS_BASE_URL:mediaURL,TTS_API_KEY:ttsKey,LIVETALKING_BASE_URL:mediaURL})
  child=spawn(binary,[],{env,stdio:['ignore','pipe','pipe']});child.stdout.on('data',b=>childLog+=b);child.stderr.on('data',b=>childLog+=b)
  await until(async()=>{try{return (await fetch(base+'/healthz')).ok}catch{return false}},'app startup')
  async function call(method,route,body,expected=200,auth=token){const response=await fetch(base+'/api/v1'+route,{method,headers:{'Authorization':'Bearer '+auth,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const result=await response.json();assert.equal(response.status,expected,method+' '+route.split('?')[0]+': '+JSON.stringify(result));return result.data}
  const shop=await call('POST','/shops',{name:'浏览器隔离测试店'}),product=await call('POST','/products',{shop_id:shop.id,title:'测试保温杯',sku:'TRANSPORT-TEST',description:'测试数据',specs:'500毫升',price_cents:9900,stock:10,active:true}),session=await call('POST','/sessions',{shop_id:shop.id,title:'真实WebRTC测试场次'})
  const operator=await browser.newPage();operator.on('pageerror',e=>pageErrors.push(e.message));await operator.goto(base);await operator.getByLabel('工作台口令').fill(token);await operator.getByRole('button',{name:'进入工作台',exact:true}).click();await operator.getByRole('button',{name:'活动管理',exact:true}).waitFor()
  for(const label of ['活动管理','品牌人格','知识与记忆','资产与音色','用量与成本','联调与淘宝','画质核验','直播工作台']){await operator.getByRole('button',{name:label,exact:true}).click();await sleep(300);assert.equal(await operator.locator('.main-shell').count(),1)}
  const issued=await call('POST',`/sessions/${session.id}/output/issue`,{shop_id:shop.id})
  await call('GET','/shops',undefined,401,issued.token)
  const output=await browser.newPage({viewport:{width:1280,height:720}});output.on('pageerror',e=>pageErrors.push(e.message))
  const outputRequests=[];output.on('request',request=>{if(request.url().startsWith(base)){outputRequests.push(new URL(request.url()).pathname);assert.notEqual(request.headers()['authorization'],'Bearer '+token,'management token leaked to output page')}})
  await output.goto(base+issued.output_path)
  const outputStatus=()=>call('GET',`/sessions/${session.id}/output?shop_id=${shop.id}`)
  await until(async()=>(await outputStatus()).online,'real audio/video connected')
  fs.mkdirSync(artifactDir,{recursive:true})
  await operator.screenshot({path:path.join(artifactDir,'workbench.png'),fullPage:true})
  await output.screenshot({path:path.join(artifactDir,'synthetic-output.png')})
  const framesBefore=await output.locator('video').evaluate(v=>v.getVideoPlaybackQuality().totalVideoFrames)
  await operator.close()
  await sleep(3500)
  assert.equal((await outputStatus()).online,true,'operator closure interrupted output')
  assert((await output.locator('video').evaluate(v=>v.getVideoPlaybackQuality().totalVideoFrames))>framesBefore,'video frames did not advance')
  const competitor=await browser.newPage();await competitor.goto(base+issued.output_path);await competitor.locator('.output-notice p').filter({hasText:'已有另一个输出页面占用'}).waitFor();assert.equal(offers,1,'second receiver replaced original');await competitor.close()
  const job=await call('POST','/jobs/manual',{shop_id:shop.id,session_id:session.id,product_id:product.id,text:'这是一条只用于传输测试的人工草稿。'})
  await call('POST',`/jobs/${job.id}/approve`,{shop_id:shop.id});await call('POST',`/jobs/${job.id}/synthesize`,{shop_id:shop.id})
  await until(async()=>(await call('GET',`/jobs?shop_id=${shop.id}`)).some(j=>j.id===job.id&&j.status==='ready'),'WAV synthesis completed')
  const sent=await call('POST',`/jobs/${job.id}/send`,{shop_id:shop.id});assert.equal(sent.status,'sent');assert.equal(uploads,1)
  await call('POST',`/jobs/${job.id}/send`,{shop_id:shop.id},409);assert.equal(uploads,1,'duplicate speech replayed')
  const takeover=await call('POST',`/sessions/${session.id}/takeover`,{shop_id:shop.id});assert.equal(takeover.session.status,'paused')
  await until(()=>output.locator('video').evaluate(v=>v.srcObject===null),'takeover clears media')
  assert.equal((await outputStatus()).online,false)
  await call('POST',`/sessions/${session.id}/resume`,{shop_id:shop.id});await until(async()=>(await outputStatus()).online,'explicit resume reconnects')
  assert.equal(offers,2)
  const revoked=await call('POST',`/sessions/${session.id}/output/revoke`,{shop_id:shop.id});assert.equal(revoked.output.enabled,false)
  await until(()=>output.locator('video').evaluate(v=>v.srcObject===null),'revocation clears media')
  assert(!outputRequests.some(p=>p.startsWith('/api/v1')),'receiver requested management API')
  assert.equal(pageErrors.length,0,'browser/fixture errors: '+pageErrors.join('; '))
  fs.mkdirSync(artifactDir,{recursive:true})
  const report={result:'passed',evidence:'real Chromium + real PostgreSQL + real WebRTC with synthetic test-only media',operator_closed_output_continued:true,second_receiver_did_not_replace:true,manual_review_to_wav_to_media:true,takeover_resume_revoke:true,offers,uploads,interrupts,tts_fixture_calls:ttsCalls,page_errors:pageErrors.length,not_tested:['real CosyVoice','MuseTalk/avatar quality','OBS native capture','Taobao broadcast']}
  fs.writeFileSync(path.join(artifactDir,'transport-result.json'),JSON.stringify(report,null,2))
  console.log(JSON.stringify(report,null,2))
})().catch(e=>{console.error(e.message);if(childLog)console.error(childLog.replaceAll(token,'[redacted]').replaceAll(ttsKey,'[redacted]').slice(-3000));process.exitCode=1}).finally(async()=>{
  if(browser)await browser.close()
  if(child&&child.exitCode===null){child.kill('SIGTERM');await Promise.race([new Promise(r=>child.once('exit',r)),sleep(12000)]);if(child.exitCode===null){child.kill('SIGKILL');await sleep(500)}}
  if(upstream)await new Promise(r=>upstream.close(r))
  if(created)try{sql(`DROP SCHEMA "${schema}" CASCADE`)}catch{console.error('Unable to remove isolated browser test schema');process.exitCode=1}
  fs.rmSync(work,{recursive:true,force:true})
})
