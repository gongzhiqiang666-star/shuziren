import type { PreparedAudio } from './audio'

export class AudioAnalyzer {
  private worker: Worker | null = null
  private cancelPending: (() => void) | null = null

  cancel() {
    this.cancelPending?.(); this.cancelPending = null
    this.worker?.terminate(); this.worker = null
  }

  analyze(audio: PreparedAudio, progress: (value: number) => void): Promise<unknown> {
    this.cancel()
    return new Promise((resolve, reject) => {
      const worker = new Worker('/avatar3d-worker.mjs', { type: 'module' })
      this.worker = worker
      const timer = window.setTimeout(() => fail(new Error('音频分析超过 90 秒，请缩短音频后重试。')), 90_000)
      const finish = () => { window.clearTimeout(timer); worker.terminate(); if (this.worker === worker) { this.worker = null; this.cancelPending = null } }
      const fail = (error: Error) => { finish(); reject(error) }
      this.cancelPending = () => fail(new DOMException('分析已取消', 'AbortError'))
      worker.onerror = () => fail(new Error('本地口型分析器无法运行，请检查资源是否完整，并使用较新的桌面浏览器。'))
      worker.onmessage = event => {
        const value = event.data as { type?: string; progress?: number; track?: unknown; message?: string }
        if (value.type === 'progress' && typeof value.progress === 'number') progress(Math.min(100, Math.max(0, value.progress)))
        else if (value.type === 'result') { finish(); resolve(value.track) }
        else if (value.type === 'error') fail(new Error(value.message || '音频分析失败。'))
      }
      const samples = audio.mono.slice()
      worker.postMessage({ samples, sampleRate: audio.sampleRate, duration: audio.duration, sha256: audio.sha256 }, [samples.buffer])
    })
  }
}
