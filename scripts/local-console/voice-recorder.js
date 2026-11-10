'use strict';
window.VoiceRecorder = class {
  constructor(onChange) { this.onChange=onChange; this.state='idle'; this.generation=0; this.blob=null; }
  release() { clearTimeout(this.timer); clearTimeout(this.permissionTimer); this.stream?.getTracks().forEach(track=>track.stop()); this.stream=null; }
  discard() {
    this.generation++; this.release();
    if (this.recorder && this.recorder.state!=='inactive') this.recorder.stop();
    this.recorder=null;this.blob=null;this.state='idle';this.onChange(this.state,null,'');
  }
  async start() {
    if (['requesting','recording','stopping'].includes(this.state)) return;
    this.discard(); const ticket=this.generation;
    this.state='requesting';this.onChange(this.state,null,'');
    this.permissionTimer=setTimeout(()=>{
      if(ticket!==this.generation || this.state!=='requesting') return;
      this.discard();this.onChange('idle',null,'15秒内未收到麦克风授权结果，已停止等待。确认权限后可重试，或导入音频文件。');
    },15000);
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw new Error('此浏览器不支持录音，请使用音频文件导入。');
      const stream=await navigator.mediaDevices.getUserMedia({audio:true});
      if (ticket!==this.generation) {stream.getTracks().forEach(track=>track.stop());return;}
      clearTimeout(this.permissionTimer);
      this.stream=stream;
      const recorder=new MediaRecorder(stream,{audioBitsPerSecond:64000});this.recorder=recorder;
      const chunks=[];
      recorder.ondataavailable=event=>{if (ticket===this.generation && event.data.size) chunks.push(event.data);};
      recorder.onerror=()=>{if(ticket===this.generation) {this.discard();this.onChange('idle',null,'录音失败，请检查麦克风后重试。');}};
      recorder.onstop=()=>{
        if(ticket!==this.generation) return;this.release();
        this.blob=new Blob(chunks,{type:recorder.mimeType || 'audio/webm'});
        if (!this.blob.size || this.blob.size>524288) {this.discard();this.onChange('idle',null,'录音为空或过大，请重录。');return;}
        this.state='preview';this.onChange(this.state,this.blob,'');
      };
      recorder.start(250);this.state='recording';this.onChange(this.state,null,'');
      this.timer=setTimeout(()=>this.stop(),30000);
    } catch(error) {
      if (ticket!==this.generation) return;
      this.release();this.state='idle';
      this.onChange(this.state,null,error.name==='NotAllowedError' ? '未获得麦克风权限，可重试或导入音频文件。' : '无法录音，请检查设备或使用音频文件导入。');
    }
  }
  stop() {
    if (this.state!=='recording') return;
    this.state='stopping';this.onChange(this.state,null,'');
    clearTimeout(this.timer);this.recorder.stop();this.release();
  }
};
