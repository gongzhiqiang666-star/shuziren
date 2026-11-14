/* Optional real microphone acceptance. Records only in the loopback page and
 * never uploads. Run only with AVATAR3D_ALLOW_REAL_MIC=1 after user approval. */
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

assert.equal(process.env.AVATAR3D_ALLOW_REAL_MIC, '1', 'Set AVATAR3D_ALLOW_REAL_MIC=1 only after explicit local microphone approval')
const root = path.resolve(__dirname, '../..')
const artifactDir = path.join(root, 'test-results/avatar3d-microphone')
fs.mkdirSync(artifactDir, { recursive: true })
const report = { result: 'running', started_at: new Date().toISOString(), scope: 'local physical microphone UI only',
  privacy: 'Audio stays in the local browser; no upload or backend API request.', page_errors: [], console_errors: [], blocked_requests: [] }
let browser

;(async () => {
  const base = new URL(process.env.AVATAR3D_BASE_URL || 'http://127.0.0.1:5173')
  assert(['localhost', '127.0.0.1', '[::1]'].includes(base.hostname) && ['http:', 'https:'].includes(base.protocol))
  const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
  browser = await chromium.launch({ headless: true, executablePath: process.env.BROWSER_EXECUTABLE || undefined,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--use-fake-ui-for-media-stream', '--autoplay-policy=no-user-gesture-required'] })
  const context = await browser.newContext({ viewport: { width: 1280, height: 960 } })
  await context.grantPermissions(['microphone'], { origin: base.origin })
  await context.route('**/*', route => {
    const url = new URL(route.request().url())
    if (['blob:', 'data:'].includes(url.protocol) || (url.origin === base.origin && !/^\/api(?:\/|$)/.test(url.pathname))) return route.continue()
    report.blocked_requests.push({ origin: url.origin, path: url.pathname }); return route.abort('blockedbyclient')
  })
  await context.addInitScript(() => {
    window.__microphoneAcceptance = { requests: 0, tracks: [], max_rms: 0, sample_windows: 0 }
    const native = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices)
    navigator.mediaDevices.getUserMedia = async constraints => {
      const stream = await native(constraints); const observed = window.__microphoneAcceptance
      observed.requests++
      observed.tracks.push(...stream.getAudioTracks().map(track => ({ label: track.label, settings: track.getSettings(),
        enabled: track.enabled, muted: track.muted, ready_state: track.readyState })))
      const context = new AudioContext(), source = context.createMediaStreamSource(stream), analyser = context.createAnalyser()
      analyser.fftSize = 2048; source.connect(analyser); const values = new Float32Array(analyser.fftSize)
      const timer = setInterval(() => {
        analyser.getFloatTimeDomainData(values)
        const rms = Math.sqrt(values.reduce((sum, value) => sum + value * value, 0) / values.length)
        observed.max_rms = Math.max(observed.max_rms, rms); observed.sample_windows++
        if (stream.getAudioTracks().every(track => track.readyState === 'ended')) { clearInterval(timer); context.close() }
      }, 50)
      return stream
    }
  })
  const page = await context.newPage(); page.setDefaultTimeout(95000)
  page.on('pageerror', error => report.page_errors.push(error.message))
  page.on('console', message => { if (message.type() === 'error') report.console_errors.push(message.text()) })
  await page.goto(new URL('/avatar3d', base).href, { waitUntil: 'domcontentloaded' })
  await page.getByText('三维人物已载入', { exact: true }).waitFor()
  await page.getByRole('button', { name: '录一段声音', exact: true }).click()
  await page.getByRole('button', { name: '结束录音', exact: true }).waitFor()
  await page.waitForTimeout(4000)
  await page.getByRole('button', { name: '结束录音', exact: true }).click()
  await page.waitForFunction(() => document.querySelector('.track-copy span')?.textContent.includes('自动口型')
    || document.querySelector('.lab-controls [role=alert]'), null, { timeout: 95000 })
  assert.equal(await page.locator('.lab-controls [role=alert]').count(), 0, await page.locator('.lab-controls').innerText())
  const observed = await page.evaluate(() => window.__microphoneAcceptance)
  report.microphone = observed
  assert.equal(observed.requests, 1); assert.equal(observed.tracks.length, 1)
  assert(observed.tracks[0].label, 'Browser did not expose a microphone device label after permission')
  assert(observed.sample_windows >= 20, 'Microphone stream did not stay active long enough')
  assert(observed.max_rms > 0.00001, 'Microphone stream contained no measurable signal')
  assert(await page.getByRole('button', { name: '播放音频与口型', exact: true }).isEnabled())
  report.result = 'passed'; report.finished_at = new Date().toISOString()
  report.ui = { recorded_seconds: 4, local_analysis_completed: true, play_enabled: true }
  assert.deepEqual(report.blocked_requests, []); assert.deepEqual(report.page_errors, []); assert.deepEqual(report.console_errors, [])
  await page.screenshot({ path: path.join(artifactDir, 'microphone-complete.png'), fullPage: true })
})().catch(error => { report.result = 'failed'; report.error = error.stack || error.message; process.exitCode = 1 })
  .finally(async () => {
    report.finished_at ||= new Date().toISOString()
    fs.writeFileSync(path.join(artifactDir, 'result.json'), JSON.stringify(report, null, 2) + '\n')
    if (browser) await browser.close()
    console.log(JSON.stringify(report, null, 2))
  })
