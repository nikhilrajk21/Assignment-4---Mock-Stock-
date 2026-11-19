import { h, ref } from 'vue'

const fixtureCloses = [13, 10, 7, 13, 19, 7, 1, 2]
const fixture = ['timestamp,open,close', ...fixtureCloses.map((close, i) =>
  `2026-11-09T15:0${i}:00Z,${i === 5 ? 10 : i === 7 ? 8 : close},${close}`)].join('\n')
const dollars = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
const money = value => dollars.format(Number(value))

function table(label, headings, rows) {
  return h('div', { class: 'backtest-scroll', tabindex: 0, 'aria-label': label }, [
    h('table', [h('caption', label), h('thead', h('tr', headings.map(name => h('th', { scope: 'col' }, name)))),
      h('tbody', rows.map((row, index) => h('tr', { key: index }, row.map(value => h('td', String(value ?? '—'))))))]),
  ])
}

export default {
  setup() {
    const file = ref(null)
    const shortWindow = ref(2)
    const longWindow = ref(3)
    const initialCash = ref(100)
    const quantity = ref(2)
    const result = ref(null)
    const dataset = ref('')
    const error = ref('')
    const running = ref(false)

    async function run(event) {
      event.preventDefault()
      if (running.value) return
      running.value = true
      error.value = ''
      result.value = null
      try {
        const selected = file.value
        if (selected?.size > 1_000_000) throw new Error('Choose a CSV smaller than 1 MB.')
        const csv = selected ? await selected.text() : fixture
        const response = await fetch('/api/backtest/csv', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ csv, short_window: Number(shortWindow.value), long_window: Number(longWindow.value),
            initial_cash: Number(initialCash.value), quantity: Number(quantity.value) }),
        })
        const data = await response.json()
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the settings and CSV columns.')
        dataset.value = selected?.name ?? 'Synthetic crossover example'
        result.value = data
      } catch (failure) {
        error.value = failure.message || 'The backtest could not run.'
      } finally {
        running.value = false
      }
    }

    const input = (label, value, step = '1') => h('label', [label, h('input', {
      type: 'number', min: step, step, required: true, value: value.value,
      onInput: event => { value.value = event.target.value },
    })])

    return () => h('section', { class: 'backtest-panel', 'aria-labelledby': 'backtest-title' }, [
      h('h2', { id: 'backtest-title' }, 'Historical SMA backtest'),
      h('p', 'Decide at the close of a completed minute. Simulate a fill at the next available bar’s open.'),
      h('form', { class: 'backtest-controls', onSubmit: run }, [
        h('label', [file.value?.name ?? 'Historical minute CSV (optional)', h('input', { type: 'file', accept: '.csv,text/csv',
          'aria-describedby': 'backtest-csv-hint', onChange: event => { file.value = event.target.files[0] ?? null },
        })]),
        input('Short SMA', shortWindow), input('Long SMA', longWindow),
        input('Starting cash (USD)', initialCash, '0.01'), input('Shares per buy', quantity),
        h('button', { type: 'submit', disabled: running.value }, running.value ? 'Running backtest…' : 'Run backtest'),
      ]),
      h('p', { id: 'backtest-csv-hint' }, 'Use timestamp, open, and close columns. Timestamps must include a time zone. The default example uses synthetic data.'),
      error.value && h('p', { role: 'alert' }, error.value),
      result.value && h('div', { 'aria-live': 'polite' }, [
        h('h3', dataset.value),
        h('p', `Starting cash ${money(result.value.starting_cash)} · Ending equity ${money(result.value.ending_equity)} · Return ${Number(result.value.return_percent).toFixed(2)}%`),
        result.value.signals.length ? table('Crossover signals', ['Time', 'Side', 'Short SMA', 'Long SMA', 'Note'],
          result.value.signals.map(x => [x.time, x.side, x.short, x.long, x.reason])) : h('p', 'No crossovers in this dataset.'),
        result.value.orders.length ? table('Simulated orders', ['Signal time', 'Side', 'Shares', 'Status', 'Fill time', 'Fill price', 'Note'],
          result.value.orders.map(x => [x.signal_at, x.side, x.quantity, x.status, x.fill_at, x.price == null ? null : money(x.price), x.reason])) : null,
        table('Account after each candle', ['Time', 'Cash', 'Shares', 'Realized P&L', 'Unrealized P&L', 'Equity'],
          result.value.equity_curve.map(x => [x.time, money(x.cash), x.shares, money(x.realized), money(x.unrealized), money(x.equity)])),
      ]),
    ])
  },
}
