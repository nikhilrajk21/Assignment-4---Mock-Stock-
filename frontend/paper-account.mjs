import { h, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'

const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

export default {
  props: { replayActive: Boolean, frame: Object },
  setup(props) {
    const account = shallowRef(null)
    const pnl = shallowRef([])
    const pnlError = ref('')
    const quantity = ref('1')
    const busy = ref(false)
    const message = ref('')
    const retry = shallowRef(null)
    const lifetime = new AbortController()
    let serial = 0
    let clock

    async function load(path = '/api/paper', data) {
      const sequence = ++serial
      const options = data ? {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      } : {}
      const response = await fetch(path, { ...options, signal: lifetime.signal })
      if (!response.ok) throw new Error('Could not update the paper account.')
      const state = await response.json()
      if (sequence === serial) account.value = state
      try {
        const history = await fetch('/api/paper/pnl', { signal: lifetime.signal })
        if (!history.ok) throw new Error('History unavailable')
        const rows = await history.json()
        if (sequence === serial) {
          pnl.value = rows
          pnlError.value = ''
        }
      } catch {
        if (!lifetime.signal.aborted && sequence === serial) pnlError.value = 'Could not load profit and loss history.'
      }
      return state
    }

    function refresh() {
      if (!busy.value) load().catch(error => {
        if (!lifetime.signal.aborted && !account.value) message.value = error.message
      })
    }

    onMounted(() => {
      refresh()
      clock = setInterval(refresh, 2000)
    })
    onUnmounted(() => {
      clearInterval(clock)
      lifetime.abort()
    })

    function replayContext(frame) {
      if (!frame?.total || !frame.step) return undefined
      const { start, end, symbol } = frame.selection
      return { start, end, symbol, step: frame.step }
    }

    watch(() => props.frame, (current, previous) => {
      const next = replayContext(current)
      const prior = replayContext(previous)
      if (!props.replayActive || !next || !prior || next.step !== prior.step + 1
        || next.start !== prior.start || next.end !== prior.end || next.symbol !== prior.symbol) return
      load('/api/paper/replay-step', next).catch(error => {
        if (!lifetime.signal.aborted) message.value = error.message
      })
    })

    async function send(order) {
      if (busy.value) return
      message.value = ''
      busy.value = true
      try {
        await load('/api/paper/orders', order)
        retry.value = null
      } catch (error) {
        if (!lifetime.signal.aborted) {
          message.value = error.message
          retry.value = order
        }
      } finally {
        busy.value = false
      }
    }

    function submit(side) {
      const replay = replayContext(props.frame)
      if (props.replayActive && !replay) {
        message.value = 'Start replay before submitting a replay order.'
        return
      }
      const order = { request_id: crypto.randomUUID(), symbol: replay?.symbol ?? 'AAPL', side }
      if (side !== 'close') {
        const shares = Number(quantity.value)
        if (!Number.isSafeInteger(shares) || shares < 1) {
          message.value = 'Enter a positive whole number of shares.'
          return
        }
        order.quantity = shares
      }
      if (props.replayActive) {
        const { start, end, step } = replay
        order.replay = { start, end, step }
      }
      send(order)
    }

    const valuation = value => value == null ? 'Unavailable' : money.format(value)

    const control = (label, side) => h('button', {
      type: 'button', disabled: busy.value || !account.value,
      onClick: () => submit(side),
    }, label)

    return () => h('section', { 'aria-labelledby': 'paper-account-title' }, [
      h('h3', { id: 'paper-account-title' }, 'Paper account'),
      h('p', 'Orders fill at the next eligible observation with zero fees. In replay, advance to the next observation to supply a price.'),
      account.value && h('dl', { class: 'candle-chart__values', 'aria-label': 'Paper balances' }, [
        h('div', [h('dt', 'Cash'), h('dd', money.format(account.value.cash))]),
        h('div', [h('dt', 'Shares held'), h('dd', String(account.value.shares))]),
      ]),
      h('div', { class: 'candle-chart__sma' }, [
        h('label', { for: 'paper-shares' }, 'Order quantity'),
        h('input', {
          id: 'paper-shares', type: 'number', min: 1, step: 1, value: quantity.value,
          onInput: event => { quantity.value = event.target.value },
        }),
        control('Buy shares', 'buy'),
        control('Sell shares', 'sell'),
        control('Close position', 'close'),
        retry.value && h('button', {
          type: 'button', disabled: busy.value, onClick: () => send(retry.value),
        }, 'Retry order'),
      ]),
      message.value && h('p', { role: 'status' }, message.value),
      account.value?.orders.length > 0 && h('table', { 'aria-label': 'Paper order history' }, [
        h('thead', h('tr', ['Order', 'Symbol', 'Side', 'Shares', 'Status', 'Fill price', 'Submitted (UTC)']
          .map(text => h('th', { scope: 'col' }, text)))),
        h('tbody', account.value.orders.map(order => h('tr', { key: order.id }, [
          order.id, order.symbol, order.side, order.quantity,
          order.rejection_reason ? order.status + ': ' + order.rejection_reason : order.status,
          order.fill ? money.format(order.fill.price) : '—',
          order.submitted_at,
        ].map(text => h('td', String(text ?? '—')))))),
      ]),
      h('h4', 'Profit and loss history'),
      pnlError.value && h('p', { role: 'status' }, pnlError.value),
      !pnlError.value && !pnl.value.length && h('p', 'No valuations recorded.'),
      pnl.value.length > 0 && h('div', { class: 'paper-table-scroll' }, [
        h('table', { class: 'paper-table', 'aria-label': 'Profit and loss history' }, [
          h('thead', h('tr', ['Event', 'Symbol', 'Valuation time (UTC)', 'Valuation price', 'Price source',
            'Cash', 'Shares', 'Realized', 'Unrealized', 'Total P&L']
            .map(text => h('th', { scope: 'col' }, text)))),
          h('tbody', pnl.value.map(row => h('tr', { key: row.id }, [
            row.event_type, row.symbol, row.price_time ?? row.timestamp, valuation(row.price), row.price_source,
            valuation(row.cash), row.shares, valuation(row.realized),
            valuation(row.unrealized), valuation(row.total),
          ].map(value => h('td', String(value ?? 'Unavailable')))))),
        ]),
      ]),
    ])
  },
}
