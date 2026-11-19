import { writeFile } from 'node:fs/promises'
import { setTimeout as delay } from 'node:timers/promises'

export async function recordDemo(page, destination, play) {
  await page.setViewportSize({ width: 1280, height: 900 })
  const recorder = await page.context().newPage()
  await recorder.setContent('<canvas width="1280" height="900"></canvas>')
  await recorder.evaluate(() => {
    const canvas = document.querySelector('canvas')
    const context = canvas.getContext('2d')
    context.fillStyle = '#10233b'
    context.fillRect(0, 0, canvas.width, canvas.height)
    const capture = new MediaRecorder(canvas.captureStream(8), { mimeType: 'video/webm;codecs=vp8' })
    const chunks = []
    capture.ondataavailable = event => { if (event.data.size) chunks.push(event.data) }
    window.finishCapture = () => new Promise(resolve => {
      capture.onstop = () => {
        const reader = new FileReader()
        reader.onload = () => resolve(String(reader.result).split(',')[1])
        reader.readAsDataURL(new Blob(chunks, { type: 'video/webm' }))
      }
      capture.stop()
    })
    window.paintFrame = async (frame, caption) => {
      const image = new Image()
      image.src = 'data:image/jpeg;base64,' + frame
      await image.decode()
      context.drawImage(image, 0, 0, canvas.width, canvas.height)
      context.fillStyle = '#10233b'
      context.fillRect(0, 846, canvas.width, 54)
      context.fillStyle = '#ffffff'
      context.font = '22px Arial, sans-serif'
      context.fillText(caption, 28, 881)
    }
    capture.start()
  })
  let caption = 'IST 402 · Assignment 4.2 · SMA crossover and backtest'
  let active = true
  const frames = (async () => {
    while (active) {
      const frame = await page.screenshot({ type: 'jpeg', quality: 72 })
      await recorder.evaluate(([image, text]) => window.paintFrame(image, text), [frame.toString('base64'), caption])
      await delay(180)
    }
  })()
  try {
    const start = Date.now()
    await play(text => { caption = text })
    await delay(Math.max(0, 34_000 - (Date.now() - start)))
    active = false
    await frames
    const bytes = await recorder.evaluate(() => window.finishCapture())
    await writeFile(destination, Buffer.from(bytes, 'base64'))
  } finally {
    active = false
    await frames.catch(() => {})
    await recorder.close()
  }
}
