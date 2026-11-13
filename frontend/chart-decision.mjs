import { h, onUnmounted, ref, shallowRef } from 'vue'
import { captureDecisionChart, captureHistoryChart } from './decision-capture.mjs'
import DecisionVoice from './decision-voice.mjs'

async function post(path, body, signal) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  const result = await response.json()
  if (!response.ok) {
    throw new Error(typeof result.detail === 'string' ? result.detail : 'Could not request the chart decision.')
  }
  return result
}

function renderCoverage(value) {
  if (value == null) return 'Unavailable'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (Array.isArray(value)) {
    if (!value.length) return 'None'
    return h('ul', value.map((item, index) => h('li', { key: index }, [renderCoverage(item)])))
  }
  if (typeof value === 'object') {
    return h('dl', Object.entries(value).flatMap(([key, item]) => [
      h('dt', { key: key + '-label' }, key.replaceAll('_', ' ')),
      h('dd', { key }, [renderCoverage(item)]),
    ]))
  }
  return String(value)
}

export default {
  props: { selection: Object, visibleRange: Function },
  setup(props) {
    const preview = shallowRef(null)
    const decision = shallowRef(null)
    const chartReading = shallowRef(null)
    const historicalPreview = shallowRef(null)
    const message = ref('')
    const busy = ref(false)
    const lifetime = new AbortController()
    onUnmounted(() => lifetime.abort())

    async function ask(imageOnly = false) {
      if (busy.value || !props.selection) return
      const selection = props.selection
      const range = props.visibleRange()
      busy.value = true
      message.value = 'Preparing chart…'
      decision.value = null
      chartReading.value = null
      historicalPreview.value = null
      preview.value = null
      try {
        const snapshot = await post('/api/decision-snapshots', selection, lifetime.signal)
        const capture = await captureDecisionChart(snapshot, range)
        if (lifetime.signal.aborted) return
        preview.value = { snapshot, capture }
        let historyFields = {}
        if (imageOnly) {
          message.value = 'Loading historical chart…'
          const response = await fetch('/api/chart-history?snapshot_id=' + encodeURIComponent(snapshot.id), {
            signal: lifetime.signal,
          })
          const history = await response.json()
          if (!response.ok) throw new Error(history.detail ?? 'Could not load chart history.')
          const historyImage = await captureHistoryChart(history)
          historicalPreview.value = { history, image: historyImage }
          if (history.id && historyImage) {
            historyFields = { history_id: history.id, history_image_data: historyImage }
          }
        }
        message.value = 'Waiting for the model…'
        const result = await post(imageOnly ? '/api/chart-analysis' : '/api/decisions', {
          snapshot_id: snapshot.id, ...capture, ...historyFields,
        }, lifetime.signal)
        if (imageOnly) chartReading.value = result
        else decision.value = result
        message.value = ''
      } catch (error) {
        if (!lifetime.signal.aborted) message.value = error.message
      } finally {
        busy.value = false
      }
    }

    return () => h('section', { 'aria-labelledby': 'chart-question-title' }, [
      h('h3', { id: 'chart-question-title' }, 'Chart analysis'),
      h('button', { type: 'button', disabled: !props.selection || busy.value, onClick: () => ask(false) }, 'Ask about chart'),
      h('button', { type: 'button', disabled: !props.selection || busy.value, onClick: () => ask(true) }, 'Analyze chart direction'),
      !props.selection && h('p', 'Select a completed candle to ask about the chart.'),
      message.value && h('p', { role: 'status' }, message.value),
      preview.value && h('figure', { class: 'chart-decision-preview' }, [
        h('figcaption', preview.value.snapshot.symbol + ' · ' + preview.value.snapshot.timeframe
          + ' · Cutoff ' + preview.value.snapshot.cutoff + ' · ' + preview.value.snapshot.market_data_label),
        h('img', { src: preview.value.capture.image_data, alt: 'Frozen price, volume, and indicator chart' }),
      ]),
      historicalPreview.value && h('div', { 'aria-label': 'Historical chart evidence' }, [
        h('p', historicalPreview.value.history.source ?? 'Historical market data'),
        historicalPreview.value.history.error && h('p', { role: 'status' }, historicalPreview.value.history.error),
        historicalPreview.value.image && h('figure', { class: 'chart-decision-preview' }, [
          h('figcaption', 'Historical five-minute candles · Retrieved after the chart cutoff'),
          h('p', 'Green and red candles show regular hours. Blue shows premarket and purple shows postmarket.'),
          h('img', { src: historicalPreview.value.image, alt: 'Historical five-minute price candles' }),
        ]),
      ]),
      chartReading.value && h('div', { 'aria-label': 'Chart direction result' }, [
        h('p', 'Chart direction: ' + (chartReading.value.choice ?? 'Unavailable')),
        chartReading.value.explanation && h('p', chartReading.value.explanation),
        h('dl', { 'aria-label': 'Evidence coverage' }, Object.entries(chartReading.value.coverage ?? {}).flatMap(([key, value]) => [
          h('dt', { key: key + '-label' }, key.replaceAll('_', ' ')),
          h('dd', { key }, [renderCoverage(value)]),
        ])),
      ]),
      decision.value && h('div', { 'aria-label': 'Chart decision result' }, [
        h('p', 'Decision ' + decision.value.id + ' · ' + decision.value.status),
        h('p', decision.value.explanation),
        h('p', 'Analyst: ' + (decision.value.proposal ?? 'Unavailable') + ' · ' + (decision.value.model ?? 'Unavailable')),
        decision.value.review && h('p', 'Reviewer: ' + (decision.value.review.verdict ?? 'Unavailable')
          + ' · ' + (decision.value.review.model ?? 'Unavailable')),
        h('p', 'Python crossover: ' + (preview.value?.snapshot.crossover ?? 'none')),
        h('dl', { 'aria-label': 'Chart questions and answers' }, (decision.value.questions ?? []).flatMap(question => {
          const answer = decision.value.answers?.find(item => item.name === question.name)
          return [h('dt', { key: question.name }, question.instructions), h('dd', answer?.choice ?? 'Unavailable')]
        })),
      ]),
      h(DecisionVoice, { key: 'decision-voice', newest: decision.value }),
    ])
  },
}
