import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { spawn, execFileSync } from 'node:child_process'
import { once } from 'node:events'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { createServer as createSocket } from 'node:net'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { setTimeout as delay } from 'node:timers/promises'
import { chromium } from 'playwright'
import { createServer as createVite } from 'vite'

const root = fileURLToPath(new URL('../../', import.meta.url))
const directory = await mkdtemp(join(tmpdir(), 'ist402-live-'))
const reservation = createSocket().listen(0, '127.0.0.1')
await once(reservation, 'listening')
const port = reservation.address().port
await new Promise(resolve => reservation.close(resolve))
const api = 'http://127.0.0.1:' + port
const python = process.env.IST402_PYTHON ?? 'python'
const live = process.argv.includes('--live')
const pnl = process.argv.includes('--pnl')
if (pnl) {
  execFileSync(python, ['-B', '-m', 'scripts.pnl_fixture', join(directory, 'observations.sqlite3')], { cwd: root })
}
const indicators = process.argv.includes('--indicators')
if (indicators) {
  await writeFile(join(directory, 'indicator-fixture.csv'), [
    'timestamp,open,high,low,close,volume',
    '2026-11-09T14:30:00Z,10,12,9,11,100',
    '2026-11-09T14:31:00Z,11,15,10,14,110',
    '2026-11-09T14:32:00Z,12,13,11,12,120',
  ].join('\n'))
}
const history = process.argv.includes('--history')
const voice = process.argv.includes('--voice')
const speechFile = process.env.IST402_VOICE_TEST_WAV
const chartDecision = history || voice || process.argv.includes('--chart-decision')
const sma = chartDecision || process.argv.includes('--sma')
const automation = process.argv.includes('--automation')
const paper = process.argv.includes('--paper')
const replay = automation || paper || sma || process.argv.includes('--replay')
if (replay) {
  execFileSync(python, ['-B', '-c', `
from datetime import datetime
from pathlib import Path
import sys
from backend.observations import ObservationStore
store = ObservationStore(Path(sys.argv[1]))
fixture = [
    ("14:59:59", "14:59:59", 99, 1000),
    ("15:00:05", "15:00:05", 100, 1004),
    ("15:00:50", "15:00:50", 101, 1011),
    ("15:00:20", "15:01:03", 103, 1009),
]
if sys.argv[2] == "sma":
    fixture = [(f"15:{minute:02d}:00", f"15:{minute + 1:02d}:00", price, 1000 + minute)
               for minute, price in enumerate((13, 10, 7, 13, 19, 7, 1))]
    fixture.append(("15:07:05", "15:07:05", 100, 1008))
if sys.argv[2] == "paper":
    fixture = [(f"15:{minute:02d}:05", f"15:{minute:02d}:05", price, 1000 + minute)
               for minute, price in enumerate((99, 100, 110, 105))]
if sys.argv[2] == "automation":
    fixture = [
        ("15:00:00", "15:01:00", 13, 1000),
        ("15:01:00", "15:02:00", 10, 1001),
        ("15:02:00", "15:03:00", 7, 1002),
        ("15:03:00", "15:04:00", 13, 1003),
        ("15:04:00", "15:05:00", 19, 1004),
        ("15:05:05", "15:05:05", 100, 1005),
        ("15:05:50", "15:06:00", 7, 1006),
        ("15:06:00", "15:07:00", 1, 1007),
        ("15:07:05", "15:07:05", 110, 1008),
        ("15:07:50", "15:08:00", 5, 1009),
        ("15:08:05", "15:08:05", 105, 1010),
        ("15:08:50", "15:09:00", 9, 1011),
        ("15:09:50", "15:10:00", 6, 1012),
    ]
for source, receipt, price, total in fixture:
    stamp = datetime.fromisoformat("2026-11-09T" + source + "+00:00")
    received = datetime.fromisoformat("2026-11-09T" + receipt + "+00:00")
    store.record({"id": "AAPL", "time": int(stamp.timestamp() * 1000),
                  "price": price, "day_volume": total}, received)
`, join(directory, 'observations.sqlite3'), automation ? 'automation' : paper ? 'paper' : sma ? 'sma' : 'replay'], { cwd: root })
}
const args = (chartDecision || automation) && !live
  ? ['-B', '-m', 'scripts.chart_decision_test_app', String(port), directory, automation ? 'automation' : history ? 'history' : 'chart']
  : indicators
  ? ['-B', '-c',
    'from pathlib import Path; import sys, uvicorn; import backend.main as app; app.CANDLE_FILE = Path(sys.argv[1]); uvicorn.run(app.app, host="127.0.0.1", port=int(sys.argv[2]))',
    join(directory, 'indicator-fixture.csv'), String(port)]
  : live || replay || pnl
  ? ['-B', '-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', String(port)]
  : ['-B', '-m', 'scripts.live_test_feed', String(port), directory]
const spawnBackend = () => spawn(python, args, {
  env: { ...process.env, IST402_YAHOO_LIVE: replay || indicators || pnl ? '0' : '1', IST402_TEST_MARKET_DATA: '1', IST402_OBSERVATIONS_DB: join(directory, 'observations.sqlite3') },
  cwd: root, stdio: 'inherit', windowsHide: true,
})
let backend = spawnBackend()
let exited = once(backend, 'exit')
let vite, browser, page
async function waitForBackend() {
  for (let attempt = 0; ; attempt++) {
    try {
      if ((await fetch(api + '/api/health')).ok) break
    } catch {}
    if (attempt >= 60 || backend.exitCode !== null) throw new Error('FastAPI did not start')
    await delay(250)
  }
}

try {
  await waitForBackend()

  vite = await createVite({
    configFile: false,
    root: join(root, 'frontend'),
    server: { port: 0, proxy: { '/api': { target: api, ws: true } } },
  })
  await vite.listen()
  browser = await chromium.launch({
    channel: process.env.IST402_BROWSER_CHANNEL ?? (process.platform === 'win32' ? 'msedge' : undefined),
    args: voice ? [
      '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
      ...(speechFile ? ['--use-file-for-fake-audio-capture=' + speechFile + '%noloop'] : []),
    ] : [],
  })
  page = await browser.newPage({ permissions: voice ? ['microphone'] : [] })
  page.setDefaultTimeout(15000)
  const errors = []
  page.on('pageerror', error => { errors.push(error); console.error(error) })
  await page.goto(vite.resolvedUrls.local[0])
  if (automation) {
    const press = name => page.getByRole('button', { name, exact: true }).press('Enter')
    await press('Replay recorded session')
    await page.getByLabel('Recorded session').locator('option').first().waitFor({ state: 'attached' })
    await press('Start replay')
    await page.getByText(/Observation 1 of 13/).waitFor()
    async function step(number) {
      await press('Next observation')
      await page.getByText(new RegExp('Observation ' + number + ' of 13')).waitFor()
    }
    for (const number of [2, 3, 4]) await step(number)
    await page.getByLabel('Automation buy shares').fill('4')
    await page.getByLabel('Automation sell shares').fill('1')
    await press('Start paper automation')
    await page.getByText('Paper automation is running.').waitFor()
    const orderHistory = page.getByRole('table', { name: 'Paper order history' })
    const automationHistory = page.getByRole('table', { name: 'Paper automation history' })
    const pending = () => orderHistory.getByText('pending', { exact: true }).waitFor()
    const account = async (cash, shares) => {
      await page.waitForFunction(([cash, shares]) => {
        const rows = document.querySelectorAll('[aria-label="Paper balances"] dd')
        return rows[0]?.textContent === cash && rows[1]?.textContent === shares
      }, [cash, shares])
    }
    await account('$1,000.00', '0')
    const firstRequest = page.waitForRequest(request => request.method() === 'POST'
      && request.url().endsWith('/api/paper/automation/analyze'))
    await step(5)
    const approved = (await firstRequest).postDataJSON()
    await pending()
    await step(6)
    await account('$600.00', '4')
    const duplicate = await page.request.post(vite.resolvedUrls.local[0] + 'api/paper/automation/analyze',
      { data: approved })
    assert.equal(duplicate.ok(), true)
    await account('$600.00', '4')
    await step(7)
    await step(8)
    await pending()
    await step(9)
    await account('$710.00', '3')
    await step(10)
    await pending()
    await step(11)
    await account('$1,025.00', '0')
    await step(12)
    await automationHistory.getByText('unsupported_signal', { exact: true }).waitFor()
    await account('$1,025.00', '0')
    const apiUrl = vite.resolvedUrls.local[0] + 'api/paper/automation'
    const beforeStop = await (await page.request.get(apiUrl)).json()
    await press('Stop paper automation')
    await page.getByText('Paper automation is stopped.').waitFor()
    await step(13)
    const stopped = await (await page.request.get(apiUrl)).json()
    assert.equal(stopped.enabled, false)
    assert.equal(stopped.attempts.length, beforeStop.attempts.length)
    const result = JSON.parse(execFileSync(python, ['-B', '-c', `
import json, sqlite3, sys
with sqlite3.connect(sys.argv[1]) as db:
    fills = db.execute("SELECT CAST(price AS REAL), quantity FROM paper_fills ORDER BY order_id").fetchall()
    pnl = db.execute("SELECT CAST(realized AS REAL), CAST(unrealized AS REAL) FROM paper_pnl ORDER BY id DESC LIMIT 1").fetchone()
    print(json.dumps([fills,pnl]))
`, join(directory, 'observations.sqlite3')], { encoding: 'utf8' }))
    assert.deepEqual(result, [[[100, 4], [110, 1], [105, 3]], [25, 0]])
    const pnl = page.getByRole('table', { name: 'Profit and loss history' }).locator('tbody tr').last()
    await pnl.getByText('$1,025.00', { exact: true }).waitFor()
    assert.deepEqual((await pnl.locator('td').allTextContents()).slice(7), ['$25.00', '$0.00', '$25.00'])
    assert.deepEqual(errors, [])
    console.log('PASS: reviewed browser automation filled 100/110/105, deduped, vetoed, stopped, and matched SQLite')
  } else if (chartDecision) {
    await page.getByRole('button', { name: 'Replay recorded session' }).press('Enter')
    await page.getByLabel('Recorded session').locator('option').first().waitFor({ state: 'attached' })
    await page.getByRole('button', { name: 'Start replay' }).press('Enter')
    for (let step = 1; step <= 5; step++) {
      if (step > 1) await page.getByRole('button', { name: 'Next observation' }).press('Enter')
      await page.getByText(new RegExp('Observation ' + step + ' of 8')).waitFor()
    }
    await page.getByLabel('Inspect candle').selectOption({ label: '2026-11-09 15:04:00 UTC' })
    if (history) {
      for (const [index, choice] of ['long', 'short', 'wait'].entries()) {
        await page.getByRole('button', { name: 'Analyze chart direction' }).press('Enter')
        await page.getByText('Chart direction: ' + choice, { exact: true }).waitFor({ timeout: 30000 })
        const historical = await page.getByRole('img', { name: 'Historical five-minute price candles' }).getAttribute('src')
        const current = await page.getByRole('img', { name: 'Frozen price, volume, and indicator chart' }).getAttribute('src')
        const captured = JSON.parse(await readFile(join(directory, 'history-provider-' + index + '.json'), 'utf8'))
        assert.equal(captured.current, current)
        assert.equal(captured.history, historical)
        const digest = value => createHash('sha256').update(value).digest('hex')
        const compareSaved = 'import sqlite3,sys,hashlib,json; db=sqlite3.connect(sys.argv[1]); row=db.execute("select a.image_data, h.image_data, c.payload_json from chart_analyses a join chart_analysis_history_images h on h.analysis_id=a.id join chart_histories c on c.id=h.history_id order by a.rowid desc limit 1").fetchone(); print(json.dumps([hashlib.sha256(row[0].encode()).hexdigest(), hashlib.sha256(row[1].encode()).hexdigest(), json.loads(row[2])["source"]])); db.close()'
        const stored = JSON.parse(execFileSync(python, ['-B', '-c', compareSaved, join(directory, 'observations.sqlite3')], { encoding: 'utf8' }))
        assert.deepEqual(stored, [digest(current), digest(historical), 'Synthetic history fixture'])
        assert.equal(captured.context.coverage.change_percent, 12)
        assert.equal(captured.context.coverage.large_move, true)
        assert.equal('cash' in captured.context, false)
        assert.equal('candles' in captured.context, false)
        const coverage = await page.getByLabel('Evidence coverage').innerText()
        assert.match(coverage, /premarket/)
        assert.doesNotMatch(coverage, /\[object Object\]/)
      }
      const query = 'import sqlite3,sys,json; db=sqlite3.connect(sys.argv[1]); print(json.dumps([db.execute("select count(*) from "+t).fetchone()[0] for t in ["chart_analyses","chart_analysis_history_images","paper_orders","paper_fills"]])); db.close()'
      const counts = JSON.parse(execFileSync(python, ['-B', '-c', query, join(directory, 'observations.sqlite3')], { encoding: 'utf8' }))
      assert.deepEqual(counts, [3, 3, 0, 0])
      assert.deepEqual(errors, [])
      console.log('PASS: historical chart images, long/short/wait, coverage and SQLite without paper orders')
    } else {
    await page.getByRole('button', { name: 'Ask about chart' }).press('Enter')
    const preview = page.getByRole('img', { name: 'Frozen price, volume, and indicator chart' })
    await preview.waitFor()
    await page.getByText(/AAPL · 1m · Cutoff 2026-11-09T15:05:00Z/).waitFor()
    const decisionText = page.getByText(/^Decision [a-f0-9]+ · /)
    await decisionText.waitFor({ timeout: 20000 })
    const [, id] = (await decisionText.innerText()).split(' ')
    const response = await page.request.get(vite.resolvedUrls.local[0] + 'api/decisions/' + id)
    assert.equal(response.ok(), true)
    const decision = await response.json()
    const image = await preview.getAttribute('src')
    assert.equal(decision.image_data, image)
    assert.equal(decision.snapshot.timestamp, '2026-11-09T15:04:00Z')
    assert.equal(decision.snapshot.crossover, 'up')
    assert.equal(decision.snapshot.candles.at(-1).close, 19)
    const orderCount = execFileSync(python, ['-B', '-c',
      'import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); print(db.execute("select count(*) from paper_orders").fetchone()[0]); db.close()',
      join(directory, 'observations.sqlite3')], { encoding: 'utf8' }).trim()
    assert.equal(orderCount, '0')
    if (!live) {
      const captured = JSON.parse(await readFile(join(directory, 'provider-record.json'), 'utf8'))
      assert.equal(captured.image_data, image)
      assert.equal(captured.snapshot.market_data_label, 'Synthetic replay fixture')
      const stored = execFileSync(python, ['-B', '-c',
        'import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); print(db.execute("select image_data from decision_images where decision_id=?", (sys.argv[2],)).fetchone()[0]); db.close()',
        join(directory, 'observations.sqlite3'), id], { encoding: 'utf8' }).trim()
      assert.equal(stored, image)
      const decideUrl = vite.resolvedUrls.local[0] + 'api/decisions'
      const imageRequest = {
        snapshot_id: decision.snapshot_id, image_data: image,
        chart_start: decision.chart_start, chart_end: decision.chart_end,
      }
      for (const invalid of [
        { ...imageRequest, image_data: 'data:image/png;base64,ZmFrZQ==' },
        { ...imageRequest, chart_end: '2026-11-09T15:03:00Z' },
      ]) {
        const rejected = await page.request.post(decideUrl, { data: invalid })
        assert.equal(rejected.status(), 422)
      }
      assert.equal(captured.snapshot.id, decision.snapshot_id)
      assert.deepEqual(captured.questions, decision.questions)
      assert.deepEqual(decision.answers.map(answer => [answer.name, answer.choice]),
        [['action', 'buy'], ['crossover', 'up'], ['evidence', 'sufficient']])
      const displayed = page.locator('[aria-label="Chart questions and answers"] dd').allTextContents()
      assert.deepEqual(await displayed, ['buy', 'up', 'sufficient'])
      console.log('PASS: Edge captured a decodable frozen chart, saved matching answers, and left orders untouched')
    } else {
      console.log('LIVE chart:', decision.status, decision.explanation,
        decision.answers.map(answer => [answer.name, answer.choice]))
      if (!voice) assert.equal(decision.answers.length, 3, decision.explanation)
    }
    if (voice) {
      await page.getByLabel('Saved decision').selectOption(id)
      if (!live) {
        await page.evaluate(() => {
          const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices)
          navigator.mediaDevices.getUserMedia = async (...args) => {
            if (globalThis.ist402DenyMic) throw new DOMException('Denied', 'NotAllowedError')
            const media = await original(...args)
            globalThis.ist402VoiceTracks = media.getTracks()
            return media
          }
          globalThis.ist402DenyMic = true
        })
        await page.getByRole('button', { name: 'Start voice', exact: true }).press('Enter')
        await page.getByText('Microphone access was denied.').waitFor()
        await page.getByText('Microphone inactive', { exact: true }).waitFor()
        await page.evaluate(() => { globalThis.ist402DenyMic = false })
        await page.route('**/api/voice/sessions', async route => {
          const offer = route.request().postDataJSON()
          assert.equal(offer.decision_id, id)
          assert.match(offer.sdp, /m=audio/)
          await route.fulfill({ status: 502, json: { detail: 'Controlled voice exchange failure.' } })
        })
        await page.getByRole('button', { name: 'Start voice', exact: true }).press('Enter')
        await page.getByText('Controlled voice exchange failure.').waitFor({ timeout: 30000 })
        await page.getByText('Microphone inactive', { exact: true }).waitFor()
        assert.equal(await page.evaluate(() => globalThis.ist402VoiceTracks.every(track => track.readyState === 'ended')), true)
        console.log('PASS: Edge microphone denial and failed WebRTC exchange released the test audio track')
      } else {
        await page.getByRole('button', { name: 'Start voice', exact: true }).press('Enter')
        const status = await page.getByText(/OpenAI Live returned HTTP|Connected\. Ask about/).first()
        await status.waitFor({ timeout: 30000 })
        const detail = await status.innerText()
        console.log('LIVE voice session exchange:', detail)
        assert.match(detail, /Connected\. Ask about/, detail)
        if (speechFile) {
          const heard = page.getByLabel('What you said')
          const reply = page.getByLabel('Assistant reply')
          await heard.waitFor({ timeout: 30000 })
          await reply.waitFor({ timeout: 30000 })
          await page.waitForFunction(() =>
            /\b(buy|purchase)\b/i.test(document.querySelector('[aria-label="Assistant reply"]')?.textContent ?? ''))
          console.log('LIVE voice input:', await heard.innerText())
          console.log('LIVE voice reply:', await reply.innerText())
          await page.getByRole('button', { name: 'End voice', exact: true }).click()
          await page.getByText('Microphone inactive', { exact: true }).waitFor()
        }
      }
    }
    if (!live && !voice) {
      await writeFile(join(directory, 'provider-fail'), '')
      await page.getByRole('button', { name: 'Ask about chart' }).press('Enter')
      await page.getByText('Controlled provider failure.').waitFor()
      const unchanged = await (await page.request.get(vite.resolvedUrls.local[0] + 'api/paper')).json()
      assert.equal(unchanged.orders.length, 0)
      console.log('PASS: controlled provider failure surfaced without a paper order')
    }
    assert.deepEqual(errors, [])
    }
  } else if (pnl) {
    const ledger = [
      ['fill', 600, 4, 0, 0, 0],
      ['mark', 600, 4, 0, 40, 40],
      ['fill', 710, 3, 10, 30, 40],
      ['mark', 710, 3, 10, -15, -5],
      ['fill', 1025, 0, 25, 0, 25],
    ]
    const readLedger = () => JSON.parse(execFileSync(python, ['-B', '-c', `
import json, sqlite3, sys
db = sqlite3.connect(sys.argv[1])
rows = db.execute("""SELECT event_type, CAST(cash AS REAL), shares, CAST(realized AS REAL),
    CAST(unrealized AS REAL), CAST(total AS REAL) FROM paper_pnl ORDER BY id""").fetchall()
db.close()
print(json.dumps(rows))
`, join(directory, 'observations.sqlite3')], { encoding: 'utf8' }))
    const format = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
    const table = page.getByRole('table', { name: 'Profit and loss history' })
    async function compare() {
      assert.deepEqual(readLedger(), ledger)
      await table.locator('tbody tr').nth(4).waitFor()
      const rows = await table.locator('tbody tr').evaluateAll(nodes =>
        nodes.map(row => [...row.cells].map(cell => cell.innerText)))
      assert.deepEqual(rows.map(row => [row[0], ...row.slice(5)]), ledger.map(
        ([event, cash, shares, realized, unrealized, total]) =>
          [event, format.format(cash), String(shares), format.format(realized),
            format.format(unrealized), format.format(total)]))
      assert.deepEqual(rows.map(row => row[3]), ['$100.00', '$110.00', '$110.00', '$95.00', '$105.00'])
      assert.deepEqual(rows.map(row => row[4]), [
        'Paper fill', 'Completed candle close', 'Paper fill', 'Completed candle close', 'Paper fill',
      ])
    }
    await compare()
    backend.kill()
    await exited
    backend = spawnBackend()
    exited = once(backend, 'exit')
    await waitForBackend()
    await page.reload()
    await compare()
    assert.deepEqual(errors, [])
    console.log('PASS: all five P&L rows match Edge and SQLite before and after FastAPI restart')
  } else if (indicators) {
    await page.getByLabel('Indicator type').selectOption('range')
    for (const window of [2, 3]) {
      await page.getByLabel('Indicator name').fill('Range ' + window)
      await page.getByLabel('Indicator window').fill(String(window))
      await page.getByRole('button', { name: 'Add indicator' }).press('Enter')
      await page.getByText('Range ' + window, { exact: true }).waitFor()
    }
    const verify = async () => {
      await page.getByLabel('Inspect candle').selectOption({ label: '2026-11-09 14:32:00 UTC' })
      await page.waitForFunction(() => {
        const rows = [...document.querySelectorAll('[aria-label="Saved indicator values"] dt')]
        return rows.length === 2 && rows[0].textContent === 'Range 2'
          && rows[0].nextElementSibling.textContent === '5' && rows[1].textContent === 'Range 3'
          && rows[1].nextElementSibling.textContent === '6'
      })
    }
    await verify()
    await page.reload()
    await verify()
    await page.getByLabel('Indicator type').selectOption('range')
    await page.getByLabel('Indicator name').fill('Invalid range')
    await page.getByLabel('Indicator window').fill('0')
    await page.getByRole('button', { name: 'Add indicator' }).press('Enter')
    await page.getByText('Choose a positive whole number for the indicator window.').waitFor()
    await verify()
    assert.deepEqual(errors, [])
    console.log('PASS: Edge fixture Range 2 = 5, Range 3 = 6, persistence after refresh, and zero rejected')
  } else if (replay) {
    await page.getByText(/Yahoo Finance feed: disabled/).waitFor()
    await page.getByRole('button', { name: 'Replay recorded session' }).click()
    await page.getByLabel('Recorded session').locator('option').first().waitFor({ state: 'attached' })
    const count = () => Number(execFileSync(python, ['-B', '-c',
      'import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); print(db.execute("select count(*) from observations").fetchone()[0]); db.close()',
      join(directory, 'observations.sqlite3')], { encoding: 'utf8' }).trim())
    assert.equal(count(), sma ? 8 : 4)
    const assertDisplayed = async (label, expected) => {
      const value = page.getByText(label, { exact: true }).locator('..').locator('dd')
      await page.waitForFunction(([field, text]) => [...document.querySelectorAll('dt')]
        .some(term => term.textContent === field && term.nextElementSibling?.textContent === text),
      [label, expected])
      assert.equal(await value.innerText(), expected)
    }
    if (paper) {
      const press = name => page.getByRole('button', { name, exact: true }).press('Enter')
      const check = async (cash, shares) => {
        await assertDisplayed('Cash', cash)
        await assertDisplayed('Shares held', shares)
      }
      const history = page.getByRole('table', { name: 'Paper order history' })
      await press('Start replay')
      await page.getByText(/Observation 1 of 4/).waitFor()
      await check('$1,000.00', '0')

      await page.getByLabel('Order quantity').fill('4')
      const firstRequest = page.waitForRequest(request =>
        request.method() === 'POST' && request.url().endsWith('/api/paper/orders'))
      await press('Buy shares')
      const buy = (await firstRequest).postDataJSON()
      await history.getByText('pending', { exact: true }).waitFor()
      await check('$1,000.00', '0')
      await press('Next observation')
      await check('$600.00', '4')

      const retry = await page.request.post(vite.resolvedUrls.local[0] + 'api/paper/orders', { data: buy })
      assert.equal(retry.ok(), true)
      assert.equal((await retry.json()).orders.length, 1)
      await page.getByLabel('Order quantity').fill('1')
      await press('Sell shares')
      await history.getByText('pending', { exact: true }).waitFor()
      await press('Next observation')
      await check('$710.00', '3')

      await press('Close position')
      await history.getByText('pending', { exact: true }).waitFor()
      await press('Next observation')
      await check('$1,025.00', '0')
      await press('Sell shares')
      await history.getByText(/rejected/i).waitFor()
      await check('$1,025.00', '0')

      const store = await page.request.get(vite.resolvedUrls.local[0] + 'api/paper')
      const account = await store.json()
      assert.equal(account.orders.length, 4)
      assert.deepEqual(account.orders.filter(order => order.fill).map(order => order.fill.price).sort((a, b) => a - b),
        [100, 105, 110])
      const readLedger = () => JSON.parse(execFileSync(python, ['-B', '-c', `
import json, sqlite3, sys
db = sqlite3.connect(sys.argv[1])
cash = float(db.execute("SELECT cash FROM paper_account WHERE id=1").fetchone()[0])
shares = db.execute("SELECT COALESCE(SUM(shares), 0) FROM paper_positions").fetchone()[0]
fills = db.execute("SELECT CAST(price AS REAL), quantity FROM paper_fills ORDER BY order_id").fetchall()
db.close()
print(json.dumps({"cash": cash, "shares": shares, "fills": fills}))
`, join(directory, 'observations.sqlite3')], { encoding: 'utf8' }))
      const expectedLedger = { cash: 1025, shares: 0, fills: [[100, 4], [110, 1], [105, 3]] }
      assert.deepEqual(readLedger(), expectedLedger)
      backend.kill()
      await exited
      backend = spawnBackend()
      exited = once(backend, 'exit')
      await waitForBackend()
      await page.reload()
      await check('$1,025.00', '0')
      const reopened = await page.request.get(vite.resolvedUrls.local[0] + 'api/paper')
      assert.deepEqual(await reopened.json(), account)
      assert.deepEqual(readLedger(), expectedLedger)
      assert.deepEqual(errors, [])
      console.log('PASS: Edge buy, partial sell, close, idempotent retry, rejection, and backend restart')
    } else if (sma) {
      const expected = [
        ['Unavailable', 'Unavailable', 0],
        ['11.50', 'Unavailable', 0],
        ['8.50', '10.00', 0],
        ['10.00', '10.00', 0],
        ['16.00', '13.00', 1],
        ['13.00', '13.00', 1],
        ['4.00', '9.00', 2],
        ['Unavailable', 'Unavailable', 2],
      ]
      const markers = page.getByRole('list', { name: 'Crossover markers' })
      await page.getByRole('button', { name: 'Start replay' }).press('Enter')
      for (const [index, [short, long, signals]] of expected.entries()) {
        if (index) await page.getByRole('button', { name: 'Next observation' }).press('Enter')
        await page.getByText(new RegExp('Observation ' + (index + 1) + ' of 8')).waitFor()
        await assertDisplayed('Short SMA', short)
        await assertDisplayed('Long SMA', long)
        await page.waitForFunction(count =>
          document.querySelectorAll('[aria-label="Crossover markers"] li').length === count, signals)
      }
      await markers.getByText(/Upward crossover.*15:04:00 UTC/).waitFor()
      await markers.getByText(/Downward crossover.*15:06:00 UTC/).waitFor()
      assert.ok(await page.locator('.candle-chart__plot canvas').count() > 0)
      await page.getByLabel('Short SMA window').fill('0')
      await page.getByRole('button', { name: 'Apply moving averages' }).press('Enter')
      await page.getByText(/Choose positive whole numbers/).waitFor()
      assert.equal(await markers.getByRole('listitem').count(), 2)
      await page.getByLabel('Short SMA window').fill('3')
      await page.getByLabel('Long SMA window').fill('4')
      await page.getByRole('button', { name: 'Apply moving averages' }).press('Enter')
      await page.getByLabel('Inspect candle').selectOption({ label: '2026-11-09 15:06:00 UTC' })
      await assertDisplayed('Short SMA', '9.00')
      await assertDisplayed('Long SMA', '10.00')
      await page.getByLabel('Indicator type').selectOption('sma')
      await page.getByLabel('Indicator name').fill('Replay SMA')
      await page.getByLabel('Indicator window').fill('2')
      await page.getByRole('button', { name: 'Add indicator' }).press('Enter')
      await assertDisplayed('Replay SMA', '4')
      await page.getByRole('button', { name: 'Edit Replay SMA window' }).press('Enter')
      await page.getByLabel('New window for Replay SMA').fill('3')
      await page.getByRole('button', { name: 'Save window', exact: true }).press('Enter')
      await assertDisplayed('Replay SMA', '9')
      assert.equal(count(), 8)
      assert.deepEqual(errors, [])
      console.log('PASS: Edge SMA warm-up gaps, two crossover markers, unfinished candle, and window changes')
    } else {
      for (let pass = 0; pass < 2; pass++) {
        await page.getByRole('button', { name: 'Start replay' }).press('Enter')
        await page.getByText(/Observation 1 of 4/).waitFor()
        for (let step = 2; step <= 4; step++) {
          await page.getByRole('button', { name: 'Next observation' }).press('Enter')
          await page.getByText(new RegExp('Observation ' + step + ' of 4')).waitFor()
          if (step === 3) await assertDisplayed('High', '101.00')
        }
        await page.getByText(/Source 2026-11-09 15:00:20 UTC.*Received 2026-11-09 15:01:03 UTC/).waitFor()
        await page.getByLabel('Inspect candle').selectOption({ label: '2026-11-09 15:00:00 UTC' })
        await assertDisplayed('High', '103.00')
        await assertDisplayed('Close', '101.00')
        await assertDisplayed('Volume', '11 shares')
        assert.equal(count(), sma ? 8 : 4)
      }
      await page.getByLabel('Start (UTC)').fill('2026-11-10T14:30')
      await page.getByLabel('End (UTC)').fill('2026-11-10T21:00')
      await page.getByRole('button', { name: 'Start replay' }).press('Enter')
      await page.getByText('No recorded observations in this range.').waitFor()
      assert.deepEqual(errors, [])
      console.log('PASS: Edge replay twice, late quote timing, close 101, volume 11, unchanged SQLite, and empty range')
    }
  } else if (live) {
    try {
      await page.getByText('AAPL · Yahoo Finance', { exact: true }).waitFor({ timeout: 45000 })
    } catch (error) {
      const count = execFileSync(python, ['-B', '-c',
        'import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); print(db.execute("select count(*) from observations").fetchone()[0]); db.close()',
        join(directory, 'observations.sqlite3')], { encoding: 'utf8' }).trim()
      console.error('Recorded Yahoo observations:', count)
      throw error
    }
    const observation = execFileSync(python, ['-B', '-c',
      'import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); print(db.execute("select source_json from observations order by source_time_ms desc,id desc limit 1").fetchone()[0]); db.close()',
      join(directory, 'observations.sqlite3')], { encoding: 'utf8' }).trim()
    const quote = JSON.parse(observation)
    const expectedTime = new Date(Math.floor(Number(quote.time) / 60000) * 60000).toISOString()
      .replace('T', ' ').replace('.000Z', ' UTC')
    await page.getByLabel('Inspect candle').selectOption({ label: expectedTime })
    const displayedClose = await page.getByText('Close', { exact: true }).locator('..').locator('dd').innerText()
    assert.equal(Number(displayedClose.replaceAll(',', '')), quote.price)
    console.log('PASS live quote:', expectedTime, 'close', displayedClose)
    if (process.platform === 'win32') {
      execFileSync('powershell.exe', ['-NoProfile', '-Command',
        'Get-CimInstance Win32_Process -Filter "ParentProcessId=' + backend.pid +
        '" | Where-Object CommandLine -Match "backend\.live_feed" | ForEach-Object { Stop-Process -Id $_.ProcessId }'])
      await page.getByText(/Yahoo Finance feed: disconnected/).waitFor()
      console.log('PASS live Yahoo disconnect while dashboard stayed connected')
      const readObservations = () => JSON.parse(execFileSync(python, ['-B', '-c',
        'import json, sqlite3, sys; db=sqlite3.connect(sys.argv[1]); print(json.dumps(db.execute("select id, source_time_ms, received_at_utc, source_json from observations order by id").fetchall())); db.close()',
        join(directory, 'observations.sqlite3')], { encoding: 'utf8' }))
      const before = readObservations()
      const [, sourceTime, receiptTime, sourceJson] = before[0]
      const firstQuote = JSON.parse(sourceJson)
      await page.getByRole('button', { name: 'Replay recorded session' }).click()
      await page.getByLabel('Recorded session').locator('option').first().waitFor({ state: 'attached' })
      await page.getByRole('button', { name: 'Start replay' }).press('Enter')
      const frame = page.getByText(/Observation 1 of /)
      await frame.waitFor()
      const displayUtc = value => new Date(value).toISOString().slice(0, 19).replace('T', ' ') + ' UTC'
      const frameText = await frame.innerText()
      assert.ok(frameText.includes('Source ' + displayUtc(sourceTime)), frameText)
      assert.ok(frameText.includes('Received ' + displayUtc(receiptTime)), frameText)
      const replayClose = await page.getByText('Close', { exact: true }).locator('..').locator('dd').innerText()
      assert.equal(Number(replayClose.replaceAll(',', '')), firstQuote.price)
      assert.deepEqual(readObservations(), before)
      console.log('PASS real Yahoo replay:', firstQuote.id, sourceTime, receiptTime, 'close', replayClose)
    }
  } else {
    await page.getByText('AAPL · Synthetic one-minute sample', { exact: true }).waitFor()
    await page.getByLabel('Inspect candle').selectOption({ label: '2026-11-09 14:31:00 UTC' })
    await page.getByText('850 shares', { exact: true }).waitFor()
    await page.getByLabel('Timeframe').selectOption('5m')
    await page.getByText('3,550 shares', { exact: true }).waitFor()
    await page.getByLabel('Timeframe').selectOption('1m')

    const mark = name => writeFile(join(directory, name), '')
    await mark('begin')
    await page.getByText('AAPL · Yahoo Finance', { exact: true }).waitFor()
    await page.getByText('4 shares', { exact: true }).waitFor()
    await mark('update')
    await page.getByText('11 shares', { exact: true }).waitFor()
    assert.equal(await page.getByLabel('Inspect candle').locator('option').count(), 2)
    await mark('append')
    await page.getByLabel('Inspect candle').locator('option').filter({ hasText: '15:01:00 UTC' }).waitFor({ state: 'attached' })
    await page.getByLabel('Inspect candle').selectOption({ label: '2026-11-09 15:01:00 UTC' })
    await page.getByText('4 shares', { exact: true }).waitFor()
    assert.equal(await page.getByLabel('Inspect candle').locator('option').count(), 3)
    assert.ok(await page.locator('.candle-chart__plot canvas').count() > 0)

    const count = execFileSync(python, ['-B', '-c',
      'import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); print(db.execute("select count(*) from observations").fetchone()[0]); db.close()',
      join(directory, 'observations.sqlite3')], { encoding: 'utf8' }).trim()
    assert.equal(count, '4')
    await mark('disconnect')
    await page.getByText(/Yahoo Finance feed: disconnected/).waitFor()
    assert.deepEqual(errors, [])
    console.log('PASS: Edge timeframe, aligned chart, updated and appended candles, SQLite rows, and upstream disconnect')
  }
} catch (error) {
  if (page) console.error(await page.locator('body').innerText())
  throw error
} finally {
  await browser?.close()
  await vite?.close()
  if (backend.exitCode === null && backend.signalCode === null) {
    if (process.platform === 'win32') {
      try {
        execFileSync('taskkill.exe', ['/PID', String(backend.pid), '/T', '/F'], { stdio: 'ignore' })
      } catch {
        backend.kill()
      }
    } else {
      backend.kill()
    }
  }
  await exited
  await rm(directory, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 })
}
