import { h, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { captureDecisionChart } from './decision-capture.mjs'

async function request(path, data, signal) {
  const response = await fetch('/api/paper/automation' + path, {
    signal,
    ...(data ? {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    } : {}),
  })
  const result = await response.json()
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Paper automation request failed.')
  return result
}

export default {
  props: {
    candles: { type: Array, required: true },
    context: { type: Object, required: true },
    visibleRange: Function,
  },
  setup(props) {
    const state = shallowRef(null)
    const busy = ref(false)
    const error = ref('')
    const buySize = ref('1')
    const sellSize = ref('1')
    const controller = new AbortController()
    let seen = new Set()
    let contextKey = ''
    let timer
    let queue = Promise.resolve()

    const keyFor = context => JSON.stringify([context.source, context.timeframe,
      context.replay?.start, context.replay?.end])
    const completed = points => points.filter(point => point.complete)
    function baseline() {
      contextKey = keyFor(props.context)
      seen = new Set(completed(props.candles).map(candle => candle.timestamp))
    }

    async function refresh() {
      try {
        const next = await request('', undefined, controller.signal)
        if (!busy.value) {
          if (next.generation !== state.value?.generation) baseline()
          state.value = next
        }
      } catch (problem) {
        if (!controller.signal.aborted && !state.value) error.value = problem.message
      }
    }

    async function toggle(enabled) {
      if (busy.value) return
      const buy = Number(buySize.value)
      const sell = Number(sellSize.value)
      if (enabled && (!Number.isSafeInteger(buy) || buy < 1 || !Number.isSafeInteger(sell) || sell < 1)) {
        error.value = 'Choose positive whole share quantities for automation.'
        return
      }
      busy.value = true
      error.value = ''
      try {
        state.value = await request('/control', { enabled }, controller.signal)
        baseline()
      } catch (problem) {
        if (!controller.signal.aborted) error.value = problem.message
      } finally {
        busy.value = false
      }
    }

    async function analyze(candle, selection, generation, visible) {
      if (!state.value?.enabled || state.value.generation !== generation || busy.value) return
      try {
        const response = await fetch('/api/decision-snapshots', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          signal: controller.signal, body: JSON.stringify({ ...selection, timestamp: candle.timestamp }),
        })
        if (!response.ok) throw new Error('Could not freeze the completed candle.')
        const snapshot = await response.json()
        let capture
        try {
          capture = await captureDecisionChart(snapshot, visible)
        } catch {
          capture = { capture_error: 'The completed candle chart could not be captured.' }
        }
        if (!state.value?.enabled || state.value.generation !== generation || busy.value) return
        await request('/analyze', { generation, snapshot_id: snapshot.id, ...capture }, controller.signal)
        await refresh()
      } catch (problem) {
        if (!controller.signal.aborted) error.value = problem.message
      }
    }

    watch(() => props.candles, points => {
      if (keyFor(props.context) !== contextKey || !state.value?.enabled || busy.value) {
        baseline()
        return
      }
      const fresh = completed(points).filter(point => !seen.has(point.timestamp))
      const generation = state.value.generation
      const selection = {
        ...props.context, order_size: Number(buySize.value), sell_size: Number(sellSize.value),
      }
      const range = props.visibleRange()
      for (const candle of fresh) {
        seen.add(candle.timestamp)
        queue = queue.then(() => analyze(candle, selection, generation, range))
      }
    })

    onMounted(() => {
      baseline()
      refresh()
      timer = setInterval(refresh, 1500)
    })
    onUnmounted(() => {
      clearInterval(timer)
      controller.abort()
    })

    const input = (id, label, value) => [
      h('label', { for: id }, label),
      h('input', {
        id, type: 'number', min: 1, step: 1, value: value.value,
        onInput: event => { value.value = event.target.value },
      }),
    ]

    return () => h('section', { 'aria-labelledby': 'automation-title' }, [
      h('h3', { id: 'automation-title' }, 'Paper automation'),
      h('div', { class: 'candle-chart__sma' }, [
        ...input('automation-buy', 'Automation buy shares', buySize),
        ...input('automation-sell', 'Automation sell shares', sellSize),
        h('button', { type: 'button', disabled: busy.value || !state.value,
          onClick: () => toggle(!state.value.enabled) },
        state.value?.enabled ? 'Stop paper automation' : 'Start paper automation'),
      ]),
      h('p', { role: 'status' }, state.value?.enabled ? 'Paper automation is running.' : 'Paper automation is stopped.'),
      error.value && h('p', { role: 'status' }, error.value),
      state.value?.attempts.length > 0 && h('div', { class: 'paper-table-scroll' }, [
        h('table', { class: 'paper-table', 'aria-label': 'Paper automation history' }, [
          h('thead', h('tr', ['Candle (UTC)', 'Signal', 'Decision', 'Analyst', 'Reviewer', 'Outcome']
            .map(label => h('th', { scope: 'col' }, label)))),
          h('tbody', state.value.attempts.map(attempt => h('tr', { key: attempt.id ?? attempt.timestamp }, [
            attempt.candle_timestamp, attempt.crossover, attempt.decision_id,
            attempt.proposal, attempt.review,
            [attempt.order_status ?? attempt.status, attempt.fill_price == null ? null : '$' + attempt.fill_price,
              attempt.fill_cash == null ? null : 'Cash $' + attempt.fill_cash + ', shares ' + attempt.fill_shares,
              attempt.explanation].filter(Boolean).join(' · '),
          ].map(value => h('td', String(value ?? '—')))))),
        ]),
      ]),
    ])
  },
}
