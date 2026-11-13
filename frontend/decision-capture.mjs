import { CandlestickSeries, createChart, createSeriesMarkers, HistogramSeries, LineSeries } from 'lightweight-charts'

const up = '#087f5b'
const down = '#c4314b'
const timeOf = timestamp => Date.parse(timestamp) / 1000

export async function captureDecisionChart(snapshot, visibleRange) {
  const cutoff = timeOf(snapshot.timestamp)
  const all = snapshot.candles.filter(candle => timeOf(candle.timestamp) <= cutoff)
  if (!all.length || all.at(-1).timestamp !== snapshot.timestamp) {
    throw new Error('Choose a completed candle and capture the chart again.')
  }
  const selected = all.filter(candle => timeOf(candle.timestamp) >= (visibleRange?.from ?? -Infinity))
  const candles = selected.length ? selected : all
  const earliest = timeOf(candles[0].timestamp)
  const indicators = snapshot.indicator_points.filter(point => {
    const time = timeOf(point.timestamp)
    return time >= earliest && time <= cutoff
  })
  const host = document.createElement('div')
  host.style.cssText = 'position:fixed;top:0;left:-2000px;width:960px;height:540px'
  document.body.append(host)
  let chart
  try {
    chart = createChart(host, {
      width: 960, height: 540,
      timeScale: { timeVisible: true, secondsVisible: false },
      layout: { attributionLogo: false },
    })
    const price = chart.addSeries(CandlestickSeries, {
      upColor: up, downColor: down, wickUpColor: up, wickDownColor: down, borderVisible: false,
    })
    const volume = chart.addSeries(HistogramSeries, {
      title: 'Volume (shares)', priceFormat: { type: 'volume' }, priceLineVisible: false,
    }, 1)
    price.setData(candles.map(({ timestamp, open, high, low, close }) => ({
      time: timeOf(timestamp), open, high, low, close,
    })))
    volume.setData(candles.map(candle => candle.volume == null ? { time: timeOf(candle.timestamp) } : {
      time: timeOf(candle.timestamp), value: candle.volume, color: candle.close >= candle.open ? up : down,
    }))
    for (const [key, title, color] of [['short', 'Short SMA', '#2358ba'], ['long', 'Long SMA', '#87521e']]) {
      const line = chart.addSeries(LineSeries, { title, color, lineWidth: 2, priceLineVisible: false })
      line.setData(indicators.map(point => point[key] == null
        ? { time: timeOf(point.timestamp) }
        : { time: timeOf(point.timestamp), value: point[key] }))
    }
    createSeriesMarkers(price, indicators.flatMap(point => point.crossover ? [{
      time: timeOf(point.timestamp),
      position: point.crossover === 'up' ? 'belowBar' : 'aboveBar',
      shape: point.crossover === 'up' ? 'arrowUp' : 'arrowDown',
      color: point.crossover === 'up' ? up : down,
    }] : []))
    chart.panes()[0].setStretchFactor(3)
    chart.panes()[1].setStretchFactor(1)
    chart.timeScale().fitContent()
    await new Promise(resolve => requestAnimationFrame(resolve))
    return {
      image_data: chart.takeScreenshot(true, false).toDataURL('image/png'),
      chart_start: candles[0].timestamp,
      chart_end: snapshot.timestamp,
    }
  } finally {
    chart?.remove()
    host.remove()
  }
}


// Render the exact historical bars returned by the server as a separate image.
export async function captureHistoryChart(history) {
  if (!history.bars?.length) return null
  const host = document.createElement('div')
  host.style.cssText = 'position:fixed;top:0;left:-2000px;width:960px;height:540px'
  document.body.append(host)
  let chart
  try {
    chart = createChart(host, {
      width: 960, height: 540,
      timeScale: { timeVisible: true, secondsVisible: false },
      layout: { attributionLogo: false },
    })
    const price = chart.addSeries(CandlestickSeries, {
      upColor: up, downColor: down, wickUpColor: up, wickDownColor: down, borderVisible: false,
    })
    const sessions = history.coverage?.sessions ?? []
    price.setData(history.bars.map(({ timestamp, open, high, low, close }) => {
      const time = timeOf(timestamp)
      const session = sessions.find(item => {
        const opening = timeOf(item.market_open)
        const closing = timeOf(item.market_close)
        return time >= opening - 12 * 60 * 60 && time < closing + 12 * 60 * 60
      })
      const opening = session && timeOf(session.market_open)
      const closing = session && timeOf(session.market_close)
      let color = close >= open ? up : down
      if (session && time < opening) color = close >= open ? '#759bd4' : '#365e9b'
      if (session && time >= closing) color = close >= open ? '#b695cb' : '#805597'
      return { time, open, high, low, close, color, borderColor: color, wickColor: color }
    }))
    chart.timeScale().fitContent()
    await new Promise(resolve => requestAnimationFrame(resolve))
    return chart.takeScreenshot(true, false).toDataURL('image/png')
  } finally {
    chart?.remove()
    host.remove()
  }
}
