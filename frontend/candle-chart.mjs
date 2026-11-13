import { h, onMounted, onUnmounted, ref, shallowRef } from 'vue'
import { CandlestickSeries, createChart, createSeriesMarkers, HistogramSeries, LineSeries } from 'lightweight-charts'
import ChartDecision from './chart-decision.mjs'
import PaperAutomation from './paper-automation.mjs'
import PaperAccount from './paper-account.mjs'
import SavedIndicators from './saved-indicators.mjs'
import './candle-chart.css'

const up = '#087f5b'
const down = '#c4314b'
const price = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 8 })
const shares = new Intl.NumberFormat('en-US')

function utcLabel(timestamp) {
  return timestamp.slice(0, 10) + ' ' + timestamp.slice(11, 19) + ' UTC'
}

export default {
  setup() {
    const container = ref(null)
    const candles = shallowRef([])
    const selected = ref(null)
    const message = ref('Loading candles…')
    const timeframe = ref('1m')
    const source = ref('Synthetic one-minute sample')
    const feed = shallowRef({ feed_status: 'connecting', source_time_ms: null })
    const now = ref(Date.now())
    const symbol = 'AAPL'
    const replay = ref(false)
    const sessions = shallowRef([])
    const replaySymbol = ref('AAPL')
    const replayStart = ref('')
    const replayEnd = ref('')
    const frame = shallowRef(null)
    let replayRequest
    let request
    let socket
    let chart
    let prices
    let volume
    let clock
    const sma = shallowRef(new Map())
    const smaMessage = ref('')
    const shortInput = ref('2')
    const longInput = ref('3')
    let windows = { short_window: 2, long_window: 3 }
    let smaRequest
    let shortLine
    let longLine
    let markers

    async function refreshAverages(points) {
      smaRequest?.abort()
      const controller = new AbortController()
      smaRequest = controller
      sma.value = new Map()
      smaMessage.value = ''
      shortLine.setData([])
      longLine.setData([])
      markers.setMarkers([])
      if (!points.length) return

      try {
        const response = await fetch('/api/indicators/sma', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          signal: controller.signal,
          body: JSON.stringify({
            ...windows,
            candles: points.map(({ timestamp, close, complete }) => ({
              timestamp, close, complete: complete === true,
            })),
          }),
        })
        if (!response.ok) throw new Error('Average calculation failed')
        const values = await response.json()
        if (controller.signal.aborted) return
        const byTime = new Map(values.map(value => [Date.parse(value.timestamp) / 1000, value]))
        const line = field => points.map(({ time }) => {
          const value = byTime.get(time)?.[field]
          return value == null ? { time } : { time, value }
        })
        shortLine.setData(line('short'))
        longLine.setData(line('long'))
        markers.setMarkers([...byTime].flatMap(([time, value]) => value.crossover ? [{
          time,
          position: value.crossover === 'up' ? 'belowBar' : 'aboveBar',
          shape: value.crossover === 'up' ? 'arrowUp' : 'arrowDown',
          color: value.crossover === 'up' ? up : down,
          text: value.crossover === 'up' ? 'Upward crossover' : 'Downward crossover',
        }] : []))
        sma.value = byTime
      } catch {
        if (!controller.signal.aborted) smaMessage.value = 'Could not calculate moving averages.'
      }
    }

    function applyWindows(event) {
      event.preventDefault()
      const short = Number(shortInput.value)
      const long = Number(longInput.value)
      if (!Number.isSafeInteger(short) || !Number.isSafeInteger(long) || short < 1 || short >= long) {
        smaMessage.value = 'Choose positive whole numbers with the short window smaller than the long window.'
        return
      }
      windows = { short_window: short, long_window: long }
      refreshAverages(candles.value)
    }

    function displayAverage(field) {
      const value = sma.value.get(selected.value?.time)?.[field]
      return value == null ? 'Unavailable' : price.format(value)
    }

    function showSeries(rows, coverage, nextSource) {
      const prior = candles.value
      const reset = prior.length === 0 || source.value !== nextSource
      const points = rows.map((candle, index) => ({
        ...candle,
        time: Date.parse(candle.timestamp) / 1000,
        complete: coverage[index]?.complete,
      }))
      const pricePoint = ({ time, open, high, low, close }) => ({ time, open, high, low, close })
      const volumePoint = ({ time, volume, close, open }) => volume == null
        ? { time }
        : { time, value: volume, color: close >= open ? up : down }

      // Replacing a historic candle requires a full series update. A forming
      // candle and an appended candle can use the chart's incremental API.
      const common = Math.max(0, prior.length - 1)
      const incremental = !reset && points.length >= prior.length
        && prior.slice(0, common).every((point, index) => {
          const next = points[index]
          return point.time === next.time && point.open === next.open
            && point.high === next.high && point.low === next.low
            && point.close === next.close && point.volume === next.volume
        })
        && prior.at(-1).time === points[common].time
      if (incremental) {
        for (const point of points.slice(common)) {
          prices.update(pricePoint(point))
          volume.update(volumePoint(point))
        }
      } else {
        prices.setData(points.map(pricePoint))
        volume.setData(points.map(volumePoint))
      }
      source.value = nextSource
      candles.value = points
      selected.value = points.find(point => point.time === selected.value?.time) ?? points.at(-1) ?? null
      message.value = points.length ? '' : 'No candles available.'
      if (reset && points.length) chart.timeScale().fitContent()
      refreshAverages(points)
    }

    async function loadTimeframe(value) {
      timeframe.value = value
      request?.abort()
      socket?.close()
      const controller = new AbortController()
      request = controller
      const query = new URLSearchParams({ symbol, timeframe: value })
      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
      const stream = new WebSocket(protocol + '//' + location.host + '/api/live?' + query)
      socket = stream
      feed.value = { feed_status: 'connecting', source_time_ms: null }
      showSeries([], [], value === '1m' ? 'Synthetic one-minute sample' : 'Synthetic sample')
      message.value = 'Loading candles…'
      let liveReceived = false

      stream.addEventListener('message', event => {
        if (request !== controller) return
        const snapshot = JSON.parse(event.data)
        if (snapshot.timeframe !== value || snapshot.symbol !== symbol) return
        feed.value = snapshot
        if (snapshot.candles.length || liveReceived) {
          liveReceived = true
          showSeries(snapshot.candles, snapshot.coverage, snapshot.source)
        }
      })
      const disconnected = () => {
        if (request === controller) {
          feed.value = { ...feed.value, feed_status: 'browser connection closed' }
        }
      }
      stream.addEventListener('close', disconnected)
      stream.addEventListener('error', disconnected)

      try {
        query.set('include_metadata', 'true')
        const response = await fetch('/api/history?' + query, { signal: controller.signal })
        if (!response.ok) throw new Error('History request failed')
        const history = await response.json()
        if (!controller.signal.aborted && !liveReceived) {
          showSeries(history.candles, history.coverage, source.value)
        }
      } catch {
        if (!controller.signal.aborted && !liveReceived) message.value = 'Could not load the candle chart.'
      }
    }

    async function enterReplay() {
      replay.value = true
      request?.abort()
      request = undefined
      socket?.close()
      showSeries([], [], 'Replay')
      message.value = 'Choose a recorded time range.'
      const controller = new AbortController()
      replayRequest = controller
      try {
        const response = await fetch('/api/replay/sessions', { signal: controller.signal })
        if (!response.ok) throw new Error('Session lookup failed')
        sessions.value = await response.json()
        if (!controller.signal.aborted && sessions.value.length) chooseSession(0)
        if (!controller.signal.aborted && !sessions.value.length) message.value = 'No recorded observations.'
      } catch {
        if (!controller.signal.aborted) message.value = 'Could not load recorded sessions.'
      }
    }

    function chooseSession(index) {
      const session = sessions.value[index]
      replaySymbol.value = session.symbol
      replayStart.value = new Date(session.start).toISOString().slice(0, 16)
      replayEnd.value = new Date(session.end).toISOString().slice(0, 16)
    }

    async function replayFrame(step, selection = frame.value?.selection) {
      const range = selection ?? {
        symbol: replaySymbol.value,
        start: replayStart.value ? replayStart.value + ':00Z' : '',
        end: replayEnd.value ? replayEnd.value + ':00Z' : '',
      }
      if (!range.start || !range.end || Date.parse(range.start) >= Date.parse(range.end)) {
        message.value = 'Choose a start and end in UTC, with the end after the start.'
        return
      }
      replayRequest?.abort()
      const controller = new AbortController()
      replayRequest = controller
      try {
        const query = new URLSearchParams({ ...range, timeframe: timeframe.value, step })
        const response = await fetch('/api/replay?' + query, { signal: controller.signal })
        if (!response.ok) throw new Error('Replay request failed')
        const result = await response.json()
        if (controller.signal.aborted) return
        frame.value = { ...result, selection: range }
        showSeries(result.candles, result.coverage, 'Replay')
        if (result.source_time_ms != null) {
          selected.value = candles.value.findLast(point => point.time * 1000 <= result.source_time_ms)
            ?? selected.value
        }
        if (!result.total) message.value = 'No recorded observations in this range.'
      } catch {
        if (!controller.signal.aborted) message.value = 'Could not load the replay frame.'
      }
    }

    function exitReplay() {
      replayRequest?.abort()
      replay.value = false
      frame.value = null
      loadTimeframe(timeframe.value)
    }

    onMounted(() => {
      chart = createChart(container.value, {
        autoSize: true,
        timeScale: { timeVisible: true, secondsVisible: false },
        layout: { attributionLogo: false },
      })
      prices = chart.addSeries(CandlestickSeries, {
        upColor: up, downColor: down, wickUpColor: up, wickDownColor: down,
        borderVisible: false,
      })
      volume = chart.addSeries(HistogramSeries, {
        title: 'Volume (shares)',
        priceFormat: { type: 'volume' },
        priceLineVisible: false,
      }, 1)
      shortLine = chart.addSeries(LineSeries, {
        color: '#2358ba', title: 'Short SMA', lineWidth: 2, priceLineVisible: false,
      })
      longLine = chart.addSeries(LineSeries, {
        color: '#87521e', title: 'Long SMA', lineWidth: 2, priceLineVisible: false,
      })
      markers = createSeriesMarkers(prices, [])
      chart.panes()[0].setStretchFactor(3)
      chart.panes()[1].setStretchFactor(1)
      chart.subscribeCrosshairMove(({ time }) => {
        if (replay.value) return
        const point = candles.value.find(candle => candle.time === time)
        if (point) selected.value = point
      })
      clock = setInterval(() => { now.value = Date.now() }, 1000)
      loadTimeframe(timeframe.value)
    })

    onUnmounted(() => {
      request?.abort()
      request = undefined
      socket?.close()
      replayRequest?.abort()
      smaRequest?.abort()
      clearInterval(clock)
      chart?.remove()
    })

    return () => h('section', { class: 'candle-chart', 'aria-labelledby': 'candle-title' }, [
      h('h2', { id: 'candle-title' }, 'Price and trading volume'),
      h('p', (replay.value ? frame.value?.selection.symbol ?? replaySymbol.value : symbol) + ' · ' + source.value),
      h('button', {
        type: 'button',
        onClick: () => replay.value ? exitReplay() : enterReplay(),
      }, replay.value ? 'Return to market chart' : 'Replay recorded session'),
      replay.value && h('div', [
        h('label', { for: 'replay-session' }, 'Recorded session'),
        h('select', {
          id: 'replay-session',
          onChange: event => chooseSession(Number(event.target.value)),
        }, sessions.value.map((session, index) => h('option', { value: index },
          session.symbol + ' · ' + utcLabel(new Date(session.start).toISOString())))),
        h('label', { for: 'replay-start' }, 'Start (UTC)'),
        h('input', {
          id: 'replay-start', type: 'datetime-local', value: replayStart.value,
          onInput: event => { replayStart.value = event.target.value },
        }),
        h('label', { for: 'replay-end' }, 'End (UTC)'),
        h('input', {
          id: 'replay-end', type: 'datetime-local', value: replayEnd.value,
          onInput: event => { replayEnd.value = event.target.value },
        }),
        h('button', { type: 'button', onClick: () => replayFrame(1, null) }, 'Start replay'),
        frame.value?.total > 0 && h('div', [
          h('button', {
            type: 'button', disabled: frame.value.step <= 1,
            onClick: () => replayFrame(frame.value.step - 1),
          }, 'Previous observation'),
          h('button', {
            type: 'button', disabled: frame.value.step >= frame.value.total,
            onClick: () => replayFrame(frame.value.step + 1),
          }, 'Next observation'),
          h('p', { role: 'status' }, 'Observation ' + frame.value.step + ' of ' + frame.value.total
            + (frame.value.source_time_ms == null ? '' : ' · Source '
              + utcLabel(new Date(frame.value.source_time_ms).toISOString()))
            + (frame.value.received_at_utc ? ' · Received '
              + utcLabel(new Date(frame.value.received_at_utc).toISOString()) : '')),
        ]),
      ]),
      h('label', { for: 'candle-timeframe' }, 'Timeframe'),
      h('select', {
        id: 'candle-timeframe',
        value: timeframe.value,
        onChange: event => {
          if (!replay.value) {
            loadTimeframe(event.target.value)
            return
          }
          timeframe.value = event.target.value
          if (frame.value) replayFrame(frame.value.step)
        },
      }, Object.entries({
        '1m': '1 minute', '5m': '5 minutes', '15m': '15 minutes', '1h': '1 hour', '1d': '1 day',
      }).map(([value, label]) => h('option', { value }, label))),
      !replay.value && h('p', { role: 'status' }, 'Yahoo Finance feed: ' + feed.value.feed_status
        + (feed.value.source_time_ms == null ? ' · Awaiting source data'
          : ' · Last source observation ' + Math.max(0, Math.floor((now.value - feed.value.source_time_ms) / 1000)) + ' seconds ago')),
      candles.value.at(-1)?.complete === false && h('p', 'Latest candle is still forming.'),
      message.value && h('p', { role: 'status' }, message.value),
      h('form', { class: 'candle-chart__sma', onSubmit: applyWindows, novalidate: true }, [
        h('label', { for: 'short-sma' }, 'Short SMA window'),
        h('input', {
          id: 'short-sma', type: 'number', min: 1, step: 1, value: shortInput.value,
          onInput: event => { shortInput.value = event.target.value },
        }),
        h('label', { for: 'long-sma' }, 'Long SMA window'),
        h('input', {
          id: 'long-sma', type: 'number', min: 1, step: 1, value: longInput.value,
          onInput: event => { longInput.value = event.target.value },
        }),
        h('button', { type: 'submit' }, 'Apply moving averages'),
      ]),
      smaMessage.value && h('p', { role: 'status' }, smaMessage.value),
      h('ul', { 'aria-label': 'Crossover markers' }, [...sma.value.values()]
        .filter(value => value.crossover)
        .map(value => h('li', { key: value.timestamp },
          (value.crossover === 'up' ? 'Upward crossover' : 'Downward crossover') + ' · ' + utcLabel(value.timestamp)))),
      h('div', { key: 'chart-plot', ref: container, class: 'candle-chart__plot' }),
      selected.value && h('div', [
        h('label', { for: 'candle-time' }, 'Inspect candle'),
        h('select', {
          id: 'candle-time',
          value: selected.value.time,
          onChange: event => {
            selected.value = candles.value.find(candle => candle.time === Number(event.target.value))
          },
        }, candles.value.map(candle => h('option', { value: candle.time }, utcLabel(candle.timestamp)))),
        h('dl', { class: 'candle-chart__values' }, [
          ['Open', price.format(selected.value.open)],
          ['High', price.format(selected.value.high)],
          ['Low', price.format(selected.value.low)],
          ['Close', price.format(selected.value.close)],
          ['Short SMA', displayAverage('short')],
          ['Long SMA', displayAverage('long')],
          ['Volume', selected.value.volume == null ? 'Unknown' : shares.format(selected.value.volume) + ' shares'],
        ].map(([label, value]) => h('div', [h('dt', label), h('dd', value)]))),
      ]),
      h(SavedIndicators, { key: 'saved-indicators', candles: candles.value, selected: selected.value }),
      h(PaperAccount, { key: 'paper-account', replayActive: replay.value, frame: frame.value }),
      h(PaperAutomation, {
        key: 'paper-automation',
        candles: candles.value,
        context: {
          symbol, timeframe: timeframe.value, ...windows,
          source: source.value.startsWith('Synthetic') ? 'sample' : 'recorded',
          ...(replay.value && frame.value ? {
            replay: { start: frame.value.selection.start, end: frame.value.selection.end, step: frame.value.step },
          } : {}),
        },
        visibleRange: () => chart?.timeScale().getVisibleRange(),
      }),
      h(ChartDecision, {
        key: 'chart-decision',
        selection: selected.value?.complete ? {
          symbol, timeframe: timeframe.value, timestamp: selected.value.timestamp, ...windows,
          source: source.value.startsWith('Synthetic') ? 'sample' : 'recorded',
          ...(replay.value && frame.value ? {
            replay: { start: frame.value.selection.start, end: frame.value.selection.end, step: frame.value.step },
          } : {}),
        } : null,
        visibleRange: () => chart?.timeScale().getVisibleRange(),
      }),
      h('p', { class: 'candle-chart__notice' }, [
        'TradingView Lightweight Charts™. Copyright © 2025 ',
        h('a', { href: 'https://www.tradingview.com/' }, 'TradingView, Inc.'),
      ]),
    ])
  },
}
