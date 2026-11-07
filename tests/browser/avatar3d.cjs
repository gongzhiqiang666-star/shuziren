/* Real-browser acceptance for /avatar3d. Does not start any service or need PG.
 * Start Vite first, then run with PLAYWRIGHT_MODULE / BROWSER_EXECUTABLE if needed.
 * AVATAR3D_BASE_URL defaults to http://127.0.0.1:5173 (loopback only).
 * AVATAR3D_SOFTWARE_GL=1 explicitly selects SwiftShader for headless CI.
 *
 * The generated PCM tone is a TEST FIXTURE, not Chinese speech or TTS evidence.
 * Real CC0 GLB + real local acoustic Worker + real native MediaRecorder are used.
 * Browser instrumentation only observes native constructors/events; it never
 * substitutes a model, classifier, audio stream, recorder or success response.
 */
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const crypto = require('node:crypto')
const { spawnSync } = require('node:child_process')

const root = path.resolve(__dirname, '../..')
const artifactDir = path.join(root, 'test-results/avatar3d')
const modelHash = '63c645a2a863b9972e9a9c2ed576a1de4c390b8475508e1473e69c87a3ee299c'
const visemes = new Set(['sil', 'PP', 'FF', 'TH', 'DD', 'kk', 'CH', 'SS', 'nn', 'RR', 'aa', 'E', 'ih', 'oh', 'ou'])
const started = Date.now()
const report = {
  result: 'running', started_at: new Date(started).toISOString(),
  scope: 'local_browser_pipeline_only',
  evidence: 'Real Chromium, pinned CC0 3D model, local acoustic worker and native recording; synthetic PCM tone only.',
  fixture_warning: '测试音仅证明音频、嘴形时间轴与录像链路；不是中文语音，不证明中文口型、真人感或 TTS 质量。',
  checks: [], page_errors: [], console_errors: [], request_failures: [], blocked_requests: [],
  not_tested: ['Chinese pronunciation and lip-sync quality', 'photorealism or customer acceptance',
    'target low-end PC performance', 'real TTS', 'microphone permission/capture',
    'OBS native capture', 'Taobao broadcast', 'eight-hour stability'],
}
fs.mkdirSync(artifactDir, { recursive: true })
// Only remove this script's stale failure image; a new failure saves a new one.
fs.rmSync(path.join(artifactDir, 'failure.png'), { force: true })
let browser, page, currentCheck, incomplete = false

function persist() {
  report.elapsed_ms = Date.now() - started
  fs.writeFileSync(path.join(artifactDir, 'result.json'), JSON.stringify(report, null, 2) + '\n')
}
async function check(name, run) {
  currentCheck = { name, status: 'running' }; report.checks.push(currentCheck); persist()
  const began = Date.now()
  try {
    const details = await run()
    Object.assign(currentCheck, { status: 'passed', elapsed_ms: Date.now() - began }, details)
    if (currentCheck.status === 'not_tested') incomplete = true
    console.log(`${currentCheck.status}: ${name}`)
  } catch (error) {
    Object.assign(currentCheck, { status: 'failed', elapsed_ms: Date.now() - began, error: error.message })
    throw error
  } finally { persist() }
}
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex')

function testTone() {
  const sampleRate = 48000, seconds = 12, frames = sampleRate * seconds
  const bytes = Buffer.alloc(44 + frames * 2)
  bytes.write('RIFF'); bytes.writeUInt32LE(bytes.length - 8, 4); bytes.write('WAVEfmt ', 8)
  bytes.writeUInt32LE(16, 16); bytes.writeUInt16LE(1, 20); bytes.writeUInt16LE(1, 22)
  bytes.writeUInt32LE(sampleRate, 24); bytes.writeUInt32LE(sampleRate * 2, 28)
  bytes.writeUInt16LE(2, 32); bytes.writeUInt16LE(16, 34); bytes.write('data', 36)
  bytes.writeUInt32LE(frames * 2, 40)
  for (let i = 0; i < frames; i++) {
    const time = i / sampleRate, phase = time % 1.2
    const frequency = [180, 330, 550][Math.floor(time / 1.2) % 3]
    // Bounded harmonic test tones with genuine silent gaps, never speech.
    const envelope = phase < 0.8 ? Math.min(1, phase / 0.03, (0.8 - phase) / 0.03) : 0
    const value = 0.15 * envelope * (Math.sin(2 * Math.PI * frequency * time)
      + 0.3 * Math.sin(2 * Math.PI * frequency * 2 * time))
    bytes.writeInt16LE(Math.round(32767 * value), 44 + i * 2)
  }
  return { bytes, duration: seconds, sample_rate: sampleRate, sha256: digest(bytes) }
}

async function settle() {
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
  await page.waitForTimeout(180)
}
async function capture(name, canvasOnly = true) {
  await settle()
  return (canvasOnly ? page.getByTestId('avatar-stage').locator('canvas') : page)
    .screenshot({ path: path.join(artifactDir, name), ...(canvasOnly ? {} : { fullPage: true }) })
}
async function pixelDifference(first, second) {
  // Compare actual Chromium PNG captures in a fresh 2D canvas, independent of
  // Three.js scene objects. No production rendering internals are overridden.
  return page.evaluate(async ({ first, second }) => {
    async function pixels(encoded) {
      const image = new Image(); image.src = 'data:image/png;base64,' + encoded; await image.decode()
      const canvas = document.createElement('canvas')
      canvas.width = Math.min(640, image.width); canvas.height = Math.round(image.height * canvas.width / image.width)
      const context = canvas.getContext('2d', { willReadFrequently: true })
      context.drawImage(image, 0, 0, canvas.width, canvas.height)
      return { width: canvas.width, height: canvas.height, data: context.getImageData(0, 0, canvas.width, canvas.height).data }
    }
    const a = await pixels(first), b = await pixels(second)
    if (a.width !== b.width || a.height !== b.height) throw new Error('Screenshot dimensions changed during pose comparison')
    let changed = 0, total = 0, maximum = 0
    const colors = new Set()
    for (let i = 0; i < a.data.length; i += 4) {
      const delta = Math.max(Math.abs(a.data[i] - b.data[i]), Math.abs(a.data[i + 1] - b.data[i + 1]), Math.abs(a.data[i + 2] - b.data[i + 2]))
      if (delta >= 8) changed++
      maximum = Math.max(maximum, delta)
      total += Math.abs(a.data[i] - b.data[i]) + Math.abs(a.data[i + 1] - b.data[i + 1]) + Math.abs(a.data[i + 2] - b.data[i + 2])
      colors.add((a.data[i] >> 4) * 256 + (a.data[i + 1] >> 4) * 16 + (a.data[i + 2] >> 4))
    }
    const count = a.width * a.height
    return { width: a.width, height: a.height, changed_pixels: changed, changed_ratio: changed / count,
      mean_channel_difference: total / (count * 3), maximum_channel_difference: maximum, quantized_colors: colors.size }
  }, { first: first.toString('base64'), second: second.toString('base64') })
}
async function saveDownload(button, name) {
  const pending = page.waitForEvent('download', { timeout: 15000 })
  await button.click()
  const download = await pending
  const failure = await download.failure(); assert.equal(failure, null, `Download failed: ${failure}`)
  const destination = path.join(artifactDir, name)
  await download.saveAs(destination)
  return destination
}
async function setTimeline(seconds) {
  await page.getByRole('slider', { name: '播放进度', exact: true }).evaluate((element, value) => {
    element.value = String(value); element.dispatchEvent(new Event('input', { bubbles: true }))
  }, seconds)
  await page.waitForFunction(value => Math.abs(document.querySelector('audio').currentTime - value) < 0.12, seconds)
}
function validateExport(track, fixture) {
  assert.equal(track.version, 1); assert.equal(track.source_audio_sha256, fixture.sha256)
  assert(Math.abs(track.duration - fixture.duration) <= 0.02, 'Export duration must match original audio')
  assert(Array.isArray(track.cues) && track.cues.length > 0 && track.cues.length <= 30000)
  let previous = 0
  for (const cue of track.cues) {
    assert(Number.isFinite(cue.start) && Number.isFinite(cue.end) && cue.start >= previous && cue.end > cue.start && cue.end <= track.duration)
    assert(visemes.has(cue.viseme), 'Worker exported an unknown viseme'); previous = cue.end
  }
}

;(async () => {
  const base = new URL(process.env.AVATAR3D_BASE_URL || 'http://127.0.0.1:5173')
  assert(['http:', 'https:'].includes(base.protocol) && ['localhost', '127.0.0.1', '[::1]'].includes(base.hostname)
    && !base.username && !base.password, 'AVATAR3D_BASE_URL must be a local loopback HTTP(S) URL without credentials')
  report.base_url = base.origin; report.software_gl_requested = process.env.AVATAR3D_SOFTWARE_GL === '1'
  const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
  const args = ['--no-sandbox', '--disable-dev-shm-usage', '--enable-unsafe-swiftshader', '--autoplay-policy=no-user-gesture-required']
  if (report.software_gl_requested) args.push('--use-gl=angle', '--use-angle=swiftshader')
  browser = await chromium.launch({ headless: true, executablePath: process.env.BROWSER_EXECUTABLE || undefined, args })
  report.browser_version = browser.version()
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, deviceScaleFactor: 1, acceptDownloads: true, serviceWorkers: 'block' })
  await context.route('**/*', route => {
    const url = new URL(route.request().url())
    if (['blob:', 'data:'].includes(url.protocol) || (url.origin === base.origin && !/^\/api(?:\/|$)/.test(url.pathname))) return route.continue()
    report.blocked_requests.push({ origin: url.origin, path: url.pathname, method: route.request().method() })
    return route.abort('blockedbyclient')
  })
  await context.addInitScript(() => {
    const observed = window.__avatar3dAcceptance = { workers: [], recorders: [], context_losses: 0 }
    document.addEventListener('webglcontextlost', () => observed.context_losses++, true)
    const NativeWorker = window.Worker
    window.Worker = new Proxy(NativeWorker, {
      construct(target, args, newTarget) {
        const worker = Reflect.construct(target, args, newTarget)
        const item = { url: new URL(String(args[0]), location.href).pathname, progress_events: 0, results: 0, errors: [] }
        observed.workers.push(item)
        worker.addEventListener('message', ({ data }) => {
          if (data?.type === 'progress') item.progress_events++
          if (data?.type === 'result') { item.results++; item.sha256 = data.track?.source_audio_sha256; item.cues = data.track?.cues?.length }
          if (data?.type === 'error') item.errors.push(String(data.message))
        })
        worker.addEventListener('error', event => item.errors.push(event.message || 'Worker error'))
        return worker
      },
    })
    if (window.MediaRecorder) {
      const NativeRecorder = window.MediaRecorder
      window.MediaRecorder = new Proxy(NativeRecorder, {
        construct(target, args, newTarget) {
          const recorder = Reflect.construct(target, args, newTarget), stream = args[0]
          const describe = track => ({ kind: track.kind, ready_state: track.readyState, enabled: track.enabled })
          const item = { mime_type: recorder.mimeType, video_tracks: stream.getVideoTracks().map(describe),
            audio_tracks: stream.getAudioTracks().map(describe), bytes: 0, chunks: 0, started: false, stopped: false, errors: [] }
          observed.recorders.push(item)
          recorder.addEventListener('start', () => { item.started = true })
          recorder.addEventListener('dataavailable', event => { item.bytes += event.data.size; item.chunks++ })
          recorder.addEventListener('stop', () => { item.stopped = true })
          recorder.addEventListener('error', event => item.errors.push(event.error?.message || 'MediaRecorder error'))
          return recorder
        },
      })
    }
  })
  page = await context.newPage(); page.setDefaultTimeout(20000)
  page.on('pageerror', error => report.page_errors.push(error.message))
  page.on('console', message => {
    if (message.type() === 'error' && !message.location().url?.endsWith('/favicon.ico')) report.console_errors.push(message.text())
  })
  page.on('requestfailed', request => report.request_failures.push({ path: new URL(request.url()).pathname, error: request.failure()?.errorText }))

  await check('prepared_real_cc0_asset', async () => {
    const response = await context.request.get(new URL('/avatar-assets/mpfb.glb', base).href, { timeout: 30000 })
    assert(response.ok(), 'CC0 example asset is missing. Prepare local assets with scripts/avatar3d_setup.py first.')
    const bytes = await response.body()
    assert.equal(bytes.subarray(0, 4).toString(), 'glTF', 'CC0 asset returned HTML/non-GLB. Prepare local assets first.')
    assert.equal(bytes.length, 36815920, 'CC0 model size differs from the pinned asset')
    assert.equal(digest(bytes), modelHash, 'CC0 model SHA-256 differs from the pinned asset')
    return { byte_length: bytes.length, sha256: modelHash, source: '/avatar-assets/mpfb.glb' }
  })

  let idleCapture, quietDifference
  await check('real_webgl_model_and_camera_rotation', async () => {
    await page.goto(new URL('/avatar3d', base).href, { waitUntil: 'domcontentloaded' })
    await page.waitForFunction(() => document.querySelector('.model-summary') || document.querySelector('.preview-panel [role=alert]'), null, { timeout: 90000 })
    assert.equal(await page.locator('.preview-panel [role=alert]').count(), 0, await page.locator('.preview-panel').innerText())
    await page.getByText('三维人物已载入', { exact: true }).waitFor()
    await page.getByLabel('自然眨眼与轻微动作', { exact: true }).uncheck()
    await page.getByRole('button', { name: '静止', exact: true }).click()
    const canvas = page.getByTestId('avatar-stage').locator('canvas')
    const webgl = await canvas.evaluate(element => {
      const gl = element.getContext('webgl2') || element.getContext('webgl')
      if (!gl) return null
      const debug = gl.getExtension('WEBGL_debug_renderer_info')
      return { width: element.width, height: element.height, version: gl.getParameter(gl.VERSION),
        renderer: debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER), context_lost: gl.isContextLost() }
    })
    assert(webgl && webgl.width > 300 && webgl.height > 300 && !webgl.context_lost, 'A live WebGL canvas is required')
    report.webgl = webgl
    if (/swiftshader|llvmpipe|software/i.test(webgl.renderer)) report.not_tested.push('GPU acceleration: this run uses a software WebGL renderer')
    idleCapture = await capture('model-front.png')
    const still = await capture('model-front-still.png')
    quietDifference = await pixelDifference(idleCapture, still)
    assert(quietDifference.quantized_colors > 32, 'Rendered canvas is blank or nearly uniform')
    assert(quietDifference.changed_ratio < 0.002, 'The idle-disabled camera must settle before visual comparisons')
    const box = await canvas.boundingBox(); assert(box)
    await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5)
    await page.mouse.down(); await page.mouse.move(box.x + box.width * 0.7, box.y + box.height * 0.48, { steps: 12 }); await page.mouse.up()
    await page.waitForTimeout(900)
    const rotated = await capture('model-rotated.png'), difference = await pixelDifference(idleCapture, rotated)
    assert(difference.changed_ratio > 0.01, 'Dragging did not produce a visible 3D camera change')
    await page.getByRole('button', { name: '重置视角', exact: true }).click(); await page.waitForTimeout(900)
    idleCapture = await capture('model-reset.png')
    assert.equal(report.page_errors.length, 0, report.page_errors.join('; '))
    assert.equal(report.console_errors.length, 0, report.console_errors.join('; '))
    return { webgl, idle_noise: quietDifference, rotation: difference, screenshots: ['model-front.png', 'model-rotated.png', 'model-reset.png'] }
  })

  await check('six_mouth_controls_change_real_rendered_pixels', async () => {
    const poses = [['PP', '闭唇'], ['FF', '唇齿'], ['aa', '张口'], ['E', '中开'], ['oh', '圆唇'], ['ou', '收圆']]
    const captures = {}, differences = {}
    for (const [id, label] of poses) {
      const button = page.getByRole('button', { name: label, exact: true })
      assert(await button.isEnabled(), `${id} mouth control is disabled`)
      await button.click(); assert((await button.getAttribute('class') || '').includes('active'), `${id} was not selected`)
      captures[id] = await capture(`mouth-${id}.png`)
    }
    for (const [id, compared] of [['PP', 'aa'], ['FF', 'aa'], ['aa', 'idle'], ['E', 'aa'], ['oh', 'aa'], ['ou', 'oh']]) {
      const difference = await pixelDifference(captures[id], compared === 'idle' ? idleCapture : captures[compared])
      assert(difference.changed_pixels > Math.max(8, quietDifference.changed_pixels * 2)
        && difference.maximum_channel_difference >= 12, `${id} did not visibly differ from ${compared}`)
      differences[id] = { compared_with: compared, ...difference }
    }
    await page.getByRole('button', { name: '静止', exact: true }).click()
    return { checked_controls: poses.map(([id]) => id), comparisons: differences, claim: 'Distinct rendered mouth controls; anatomical/Chinese accuracy still needs human review.' }
  })

  const fixture = testTone(), wavPath = path.join(artifactDir, 'test-tone-only.wav')
  fs.writeFileSync(wavPath, fixture.bytes)
  report.test_audio = { file: 'test-tone-only.wav', duration: fixture.duration, sample_rate: fixture.sample_rate,
    byte_length: fixture.bytes.length, sha256: fixture.sha256, contains_speech: false, tts_used: false }
  let exportedTrack, exportedTrackPath
  await check('real_local_acoustic_worker_and_bound_track_export', async () => {
    await page.getByLabel('选择测试音频', { exact: true }).setInputFiles(wavPath)
    await page.waitForFunction(() => document.querySelector('.track-copy span')?.textContent.includes('自动口型')
      || document.querySelector('.lab-controls [role=alert]'), null, { timeout: 95000 })
    assert.equal(await page.locator('.lab-controls [role=alert]').count(), 0, await page.locator('.lab-controls').innerText())
    assert(await page.getByRole('button', { name: '播放音频与口型', exact: true }).isEnabled())
    const workers = await page.evaluate(() => window.__avatar3dAcceptance.workers)
    const actual = workers.find(worker => worker.url === '/avatar3d-worker.mjs')
    assert(actual && actual.results === 1 && actual.progress_events > 0 && actual.errors.length === 0, 'The native local acoustic worker must finish successfully')
    assert.equal(actual.sha256, fixture.sha256)
    exportedTrackPath = await saveDownload(page.getByRole('button', { name: '导出轨道', exact: true }), 'acoustic-track.json')
    assert(fs.statSync(exportedTrackPath).size <= 2 * 1024 * 1024)
    exportedTrack = JSON.parse(fs.readFileSync(exportedTrackPath, 'utf8')); validateExport(exportedTrack, fixture)
    return { worker: actual, cue_count: exportedTrack.cues.length, visemes: [...new Set(exportedTrack.cues.map(cue => cue.viseme))],
      audio_hash_matched: true, track: 'acoustic-track.json', chinese_quality: 'not_tested' }
  })

  await check('play_pause_seek_stop_and_replay_use_audio_timeline', async () => {
    const audio = page.locator('audio')
    await page.getByRole('button', { name: '播放音频与口型', exact: true }).click()
    await page.waitForFunction(() => !document.querySelector('audio').paused && document.querySelector('audio').currentTime > 0.15)
    await page.getByRole('button', { name: '暂停播放', exact: true }).click()
    const pausedAt = await audio.evaluate(element => element.currentTime); await page.waitForTimeout(300)
    const afterPause = await audio.evaluate(element => element.currentTime)
    assert(Math.abs(afterPause - pausedAt) < 0.025, 'Paused audio clock kept advancing')
    await setTimeline(4.5)
    await page.getByRole('button', { name: '播放音频与口型', exact: true }).click()
    await page.waitForFunction(() => document.querySelector('audio').currentTime > 4.65)
    await page.getByRole('button', { name: '暂停播放', exact: true }).click()
    await page.getByRole('button', { name: '停止', exact: true }).click()
    assert.equal(await audio.evaluate(element => element.currentTime), 0)
    await setTimeline(fixture.duration - 0.08)
    await page.getByRole('button', { name: '播放音频与口型', exact: true }).click()
    await page.waitForFunction(() => document.querySelector('audio').ended)
    await page.getByRole('button', { name: '播放音频与口型', exact: true }).click()
    await page.waitForFunction(() => { const audio = document.querySelector('audio'); return !audio.paused && audio.currentTime > 0.1 && audio.currentTime < 1 })
    const replayAt = await audio.evaluate(element => element.currentTime)
    await page.getByRole('button', { name: '暂停播放', exact: true }).click()
    return { paused_at: pausedAt, after_pause: afterPause, seek_seconds: 4.5, stop_resets_to_zero: true, replay_after_ended_at: replayAt }
  })

  await check('different_audio_sha_is_rejected_without_replacing_track', async () => {
    const invalidPath = path.join(artifactDir, 'wrong-audio-track.json')
    fs.writeFileSync(invalidPath, JSON.stringify({ ...exportedTrack, source_audio_sha256: '0'.repeat(64) }))
    await page.getByLabel('导入口型轨道', { exact: true }).setInputFiles(invalidPath)
    await page.getByRole('alert').filter({ hasText: '口型轨道不属于当前音频' }).waitFor()
    const unchangedPath = await saveDownload(page.getByRole('button', { name: '导出轨道', exact: true }), 'track-after-rejection.json')
    assert.deepEqual(JSON.parse(fs.readFileSync(unchangedPath, 'utf8')), exportedTrack, 'Rejected track replaced the valid track')
    await page.getByLabel('导入口型轨道', { exact: true }).setInputFiles(exportedTrackPath)
    await page.getByText('导入轨道 · 音频校验一致', { exact: false }).waitFor()
    assert.equal(await page.locator('.lab-controls [role=alert]').count(), 0)
    return { wrong_hash_rejected: true, valid_track_preserved: true, matching_track_imported: true }
  })

  await check('clean_output_mode_and_escape_restore_controls', async () => {
    await setTimeline(1)
    await page.getByRole('button', { name: '播放音频与口型', exact: true }).click()
    await page.getByRole('button', { name: '纯画面 / OBS', exact: true }).click()
    // In clean mode all normal-flow children are hidden; the visible preview
    // is fixed to the viewport, so the <main> itself legitimately has no area.
    await page.locator('.avatar-lab.clean-view').waitFor({ state: 'attached' })
    assert(await page.getByTestId('avatar-stage').locator('canvas').isVisible())
    assert.equal(await page.locator('.lab-header').isVisible(), false)
    await page.waitForFunction(() => document.querySelector('audio').currentTime > 1.2)
    const box = await page.getByTestId('avatar-stage').boundingBox()
    assert(box && Math.abs(box.width - 1440) < 2 && Math.abs(box.height - 1100) < 2)
    await capture('clean-output.png', false)
    await page.keyboard.press('Escape')
    await page.waitForFunction(() => !document.querySelector('.avatar-lab').classList.contains('clean-view'))
    assert(await page.locator('.lab-header').isVisible())
    assert(await page.locator('.play-button').isEnabled())
    const state = await page.locator('audio').evaluate(audio => ({ paused: audio.paused, ended: audio.ended, current_time: audio.currentTime }))
    assert(state.ended || !state.paused, 'Changing the display mode interrupted playback')
    if (!state.paused) await page.getByRole('button', { name: '暂停播放', exact: true }).click()
    return { fills_viewport: true, audio_continued: true, escape_restored_controls: true, screenshot: 'clean-output.png', obs: 'not_tested' }
  })

  await check('native_recording_contains_live_audio_and_video_and_exports', async () => {
    const support = await page.evaluate(() => ({ recorder: !!window.MediaRecorder,
      canvas_capture: !!document.querySelector('canvas')?.captureStream,
      codecs: window.MediaRecorder ? ['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/mp4', 'video/webm'].filter(type => MediaRecorder.isTypeSupported(type)) : [] }))
    if (!support.recorder || !support.canvas_capture || !support.codecs.length) {
      report.not_tested.push('Native audio/video recording: browser does not expose a supported codec/capture API')
      return { status: 'not_tested', reason: 'Native MediaRecorder/canvas capture or supported encoding is unavailable; no substitute used.', support }
    }
    await page.getByRole('button', { name: '录制人物与声音', exact: true }).click()
    await page.waitForFunction(() => window.__avatar3dAcceptance.recorders.some(recorder => recorder.started))
    await page.waitForFunction(() => document.querySelector('audio').currentTime > 1.5)
    await page.getByRole('button', { name: '结束并生成录像', exact: true }).click()
    const download = page.getByRole('link', { name: '下载本次录像', exact: true }); await download.waitFor()
    const native = await page.evaluate(() => window.__avatar3dAcceptance.recorders.at(-1))
    assert(native.started && native.stopped && native.bytes > 1000 && native.chunks > 0 && native.errors.length === 0)
    assert.equal(native.video_tracks.length, 1); assert.equal(native.audio_tracks.length, 1)
    for (const track of [...native.video_tracks, ...native.audio_tracks]) assert(track.ready_state === 'live' && track.enabled)
    const name = native.mime_type.includes('mp4') ? 'recorded-preview.mp4' : 'recorded-preview.webm'
    const videoPath = await saveDownload(download, name)
    assert.equal(fs.statSync(videoPath).size, native.bytes, 'Exported bytes differ from actual recorder chunks')
    const decoded = await download.evaluate(async link => {
      const video = document.createElement('video'); video.muted = true; video.preload = 'auto'
      try {
        await new Promise((resolve, reject) => {
          const timer = setTimeout(() => reject(new Error('Recorded video decode timeout')), 15000)
          video.onloadeddata = () => { clearTimeout(timer); resolve() }
          video.onerror = () => { clearTimeout(timer); reject(new Error('Recorded video cannot be decoded')) }
          video.src = link.href; video.load()
        })
        return { width: video.videoWidth, height: video.videoHeight, ready_state: video.readyState,
          duration: Number.isFinite(video.duration) ? video.duration : null }
      } finally { video.removeAttribute('src'); video.load() }
    })
    assert(decoded.width > 0 && decoded.height > 0 && decoded.ready_state >= 2, 'The exported recording is not decodable video')
    const probe = spawnSync(process.env.FFPROBE_BINARY || 'ffprobe', ['-v', 'error', '-show_packets', '-show_entries',
      'stream=codec_type,codec_name:format=duration,size:packet=codec_type,pts_time,duration_time', '-of', 'json', videoPath],
    { encoding: 'utf8', timeout: 15000, maxBuffer: 2 * 1024 * 1024 })
    let fileStreams = { status: 'not_tested', reason: 'ffprobe is not installed; native input tracks, output bytes and browser decode verified.' }
    if (!probe.error || probe.error.code !== 'ENOENT') {
      assert.equal(probe.status, 0, `ffprobe failed: ${probe.stderr || probe.error?.message}`)
      const inspected = JSON.parse(probe.stdout), streams = inspected.streams
      assert(streams.some(stream => stream.codec_type === 'video') && streams.some(stream => stream.codec_type === 'audio'), 'The recorded file is missing an audio or video stream')
      const spans = {}
      for (const kind of ['audio', 'video']) {
        const packets = inspected.packets.filter(packet => packet.codec_type === kind && Number.isFinite(Number(packet.pts_time)))
        assert(packets.length > 0, `Recorded ${kind} stream has no encoded packets`)
        const start = Math.min(...packets.map(packet => Number(packet.pts_time)))
        const end = Math.max(...packets.map(packet => Number(packet.pts_time) + (Number(packet.duration_time) || 0)))
        spans[kind] = { packets: packets.length, start_seconds: start, end_seconds: end, span_seconds: end - start }
      }
      const containerDuration = Number(inspected.format?.duration)
      fileStreams = { status: 'passed', streams, packet_timelines: spans,
        container_duration_seconds: Number.isFinite(containerDuration) ? containerDuration : null,
        duration_note: 'MediaRecorder WebM may omit container duration; packet timestamp spans and browser-decoded duration are reported separately.' }
    }
    return { support, native_recorder: native, file: name, bytes: native.bytes, browser_decode: decoded, encoded_file_streams: fileStreams }
  })

  await check('exported_report_and_browser_errors', async () => {
    await page.getByRole('button', { name: '停止', exact: true }).click()
    const exported = await saveDownload(page.getByRole('button', { name: '导出验证记录', exact: true }), 'ui-verification-report.json')
    const uiReport = JSON.parse(fs.readFileSync(exported, 'utf8'))
    assert(uiReport.model.hasUsableMouthRig && uiReport.model.meshCount > 0)
    assert(uiReport.rendering.drawCalls > 0 && uiReport.rendering.fps > 0)
    assert.equal(uiReport.audio.sha256, fixture.sha256)
    assert.equal(uiReport.lip_sync.binding, 'sha256-verified')
    assert.equal(uiReport.verification.human_quality_review, 'not_recorded')
    const observed = await page.evaluate(() => window.__avatar3dAcceptance)
    assert.equal(observed.context_losses, 0, 'WebGL context was lost')
    assert.equal(report.page_errors.length, 0, report.page_errors.join('; '))
    assert.equal(report.console_errors.length, 0, report.console_errors.join('; '))
    assert.equal(report.blocked_requests.length, 0, 'The local-only page tried to access an external service or backend API')
    await capture('avatar3d-desktop.png', false)
    return { ui_report: 'ui-verification-report.json', observed_fps: uiReport.rendering.fps,
      performance_claim: 'This browser/environment only; not a low-end hardware benchmark.',
      page_errors: 0, console_errors: 0, context_losses: 0, paid_services_called: false, backend_api_called: false }
  })
  report.result = incomplete ? 'incomplete' : 'passed'
  if (incomplete) process.exitCode = 2
})().catch(async error => {
  report.result = 'failed'; report.failure = { check: currentCheck?.name || 'browser_setup', message: error.message }
  process.exitCode = 1
  console.error(error.message)
  if (page && !page.isClosed()) {
    try { await page.screenshot({ path: path.join(artifactDir, 'failure.png'), fullPage: true, timeout: 10000 }) } catch {}
  }
}).finally(async () => {
  report.finished_at = new Date().toISOString(); persist()
  if (browser) await browser.close()
  console.log(JSON.stringify({ result: report.result, checks: report.checks.map(({ name, status }) => ({ name, status })),
    report: path.join(artifactDir, 'result.json'), fixture_warning: report.fixture_warning }, null, 2))
})
