const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../scripts/local-console/voice-recorder.js'),'utf8');
function setup(getUserMedia) {
  const records=[];const updates=[];const timers=[];
  class MediaRecorder {
    constructor(stream) {this.stream=stream;this.state='inactive';this.mimeType='audio/webm';records.push(this);}
    start() {this.state='recording';}
    stop() {this.state='inactive';}
  }
  const context={window:{MediaRecorder},MediaRecorder,navigator:{mediaDevices:{getUserMedia}},Blob,
    setTimeout:(callback,delay)=>{callback.delay=delay;timers.push(callback);return timers.length;},clearTimeout:()=>{}};
  vm.runInNewContext(source,context);
  const recorder=new context.window.VoiceRecorder((...args)=>updates.push(args));
  return {recorder,records,updates,timers};
}
function stream() {const track={stopped:0,stop(){this.stopped++;}};return {track,getTracks:()=>[track]};}
test('late permission resolution after discard releases tracks without recording',async()=>{
  let resolve;const media=new Promise(r=>resolve=r);const s=stream();const {recorder,records}=setup(()=>media);
  const pending=recorder.start();recorder.discard();resolve(s);await pending;
  assert.equal(s.track.stopped,1);assert.equal(records.length,0);assert.equal(recorder.state,'idle');
});
test('stop produces preview, auto-stop is bounded, discard removes preview',async()=>{
  const s=stream();const {recorder,records,timers}=setup(async()=>s);await recorder.start();
  records[0].ondataavailable({data:new Blob(['recorded-media'])});timers.find(t=>t.delay===30000)();
  records[0].onstop();assert.equal(recorder.state,'preview');assert.ok(recorder.blob.size>0);
  assert.ok(s.track.stopped>0);recorder.discard();assert.equal(recorder.blob,null);
});
test('old stop callback cannot stop new recording',async()=>{
  const first=stream(),second=stream();let calls=0;
  const {recorder,records}=setup(async()=>calls++ ? second:first);
  await recorder.start();recorder.discard();await recorder.start();records[0].onstop();
  assert.equal(recorder.state,'recording');assert.equal(second.track.stopped,0);recorder.discard();
});
test('permission denial is visible and creates no preview',async()=>{
  const {recorder,updates}=setup(async()=>{const e=new Error();e.name='NotAllowedError';throw e;});
  await recorder.start();assert.equal(recorder.state,'idle');assert.equal(recorder.blob,null);
  assert.match(updates.at(-1)[2],/未获得麦克风权限/);
});
test('permission timeout restores idle and late grant cannot start recording',async()=>{
  let resolve;const permission=new Promise(r=>resolve=r);const s=stream();
  const {recorder,records,updates,timers}=setup(()=>permission);
  const pending=recorder.start();timers.find(t=>t.delay===15000)();
  assert.equal(recorder.state,'idle');assert.match(updates.at(-1)[2],/已停止等待/);
  resolve(s);await pending;assert.equal(records.length,0);assert.equal(s.track.stopped,1);
});
