import { h, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'

const number = new Intl.NumberFormat('en-US', { maximumFractionDigits: 8 })

async function request(url, options) {
  const response = await fetch(url, options)
  const data = await response.json()
  if (!response.ok) {
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not load indicators.')
  }
  return data
}

function jsonPost(body, signal) {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  }
}

export default {
  props: { candles: { type: Array, required: true }, selected: Object },
  setup(props) {
    const types = shallowRef([])
    const configs = shallowRef([])
    const values = shallowRef(new Map())
    const name = ref('')
    const type = ref('')
    const window = ref('2')
    const editing = ref(null)
    const newWindow = ref('')
    const message = ref('')
    const calculationError = ref('')
    const saving = ref(false)
    const lifecycle = new AbortController()
    let evaluation

    async function evaluate() {
      evaluation?.abort()
      values.value = new Map()
      calculationError.value = ''
      if (!configs.value.length || !props.candles.length) return
      const controller = new AbortController()
      evaluation = controller
      try {
        const result = await request('/api/indicators/evaluate', jsonPost({
          candles: props.candles.map(({ timestamp, high, low, close, complete }) => ({
            timestamp, high, low, close, complete: complete === true,
          })),
        }, controller.signal))
        if (controller.signal.aborted) return
        values.value = new Map(result.map(indicator => [
          indicator.id, new Map(indicator.values.map(({ timestamp, value }) => [timestamp, value])),
        ]))
      } catch (error) {
        if (!controller.signal.aborted) calculationError.value = error.message
      }
    }

    onMounted(async () => {
      try {
        const options = { signal: lifecycle.signal }
        const [definitions, saved] = await Promise.all([
          request('/api/indicators/types', options),
          request('/api/indicators', options),
        ])
        if (lifecycle.signal.aborted) return
        types.value = definitions
        type.value = definitions[0]?.type ?? ''
        configs.value = saved
        evaluate()
      } catch (error) {
        if (!lifecycle.signal.aborted) message.value = error.message
      }
    })

    watch(() => props.candles, evaluate)
    onUnmounted(() => {
      lifecycle.abort()
      evaluation?.abort()
    })

    async function add(event) {
      event.preventDefault()
      if (saving.value) return
      const length = Number(window.value)
      if (!Number.isSafeInteger(length) || length < 1) {
        message.value = 'Choose a positive whole number for the indicator window.'
        return
      }
      if (!name.value.trim()) {
        message.value = 'Enter a name for the indicator.'
        return
      }
      saving.value = true
      message.value = ''
      try {
        const saved = await request('/api/indicators', jsonPost({
          name: name.value.trim(), type: type.value, window: length,
        }, lifecycle.signal))
        if (lifecycle.signal.aborted) return
        configs.value = [...configs.value, saved]
        name.value = ''
        evaluate()
      } catch (error) {
        if (!lifecycle.signal.aborted) message.value = error.message
      } finally {
        saving.value = false
      }
    }

    async function updateWindow(event, config) {
      event.preventDefault()
      const length = Number(newWindow.value)
      if (!Number.isSafeInteger(length) || length < 1) {
        message.value = 'Choose a positive whole number for the indicator window.'
        return
      }
      try {
        const saved = await request('/api/indicators/' + config.id, {
          ...jsonPost({ window: length }, lifecycle.signal), method: 'PATCH',
        })
        configs.value = configs.value.map(row => row.id === saved.id ? saved : row)
        editing.value = null
        message.value = ''
        evaluate()
      } catch (error) {
        if (!lifecycle.signal.aborted) message.value = error.message
      }
    }

    return () => h('section', { 'aria-labelledby': 'saved-indicators-title' }, [
      h('h3', { id: 'saved-indicators-title' }, 'Saved indicators'),
      h('form', { class: 'candle-chart__sma', onSubmit: add, novalidate: true }, [
        h('label', { for: 'indicator-type' }, 'Indicator type'),
        h('select', {
          id: 'indicator-type',
          value: type.value,
          onChange: event => { type.value = event.target.value },
        }, types.value.map(item => h('option', { key: item.type, value: item.type }, item.label))),
        h('label', { for: 'indicator-name' }, 'Indicator name'),
        h('input', {
          id: 'indicator-name', class: 'indicator-name', value: name.value,
          onInput: event => { name.value = event.target.value },
        }),
        h('label', { for: 'indicator-window' }, 'Indicator window'),
        h('input', {
          id: 'indicator-window', type: 'number', min: 1, step: 1, value: window.value,
          onInput: event => { window.value = event.target.value },
        }),
        h('button', { type: 'submit', disabled: !type.value || saving.value }, 'Add indicator'),
      ]),
      message.value && h('p', { role: 'status' }, message.value),
      calculationError.value && h('p', { role: 'status' }, calculationError.value),
      h('dl', { class: 'candle-chart__values', 'aria-label': 'Saved indicator values' },
        configs.value.map(config => {
          const value = values.value.get(config.id)?.get(props.selected?.timestamp)
          return h('div', { key: config.id }, [
            h('dt', config.name),
            h('dd', value == null ? 'Unavailable' : number.format(value)),
            h('small', 'Window ' + config.window),
            h('button', { type: 'button', onClick: () => {
              editing.value = config.id
              newWindow.value = String(config.window)
            } }, 'Edit ' + config.name + ' window'),
            editing.value === config.id && h('form', { onSubmit: event => updateWindow(event, config), novalidate: true }, [
              h('label', { for: 'saved-window-' + config.id }, 'New window for ' + config.name),
              h('input', {
                id: 'saved-window-' + config.id, type: 'number', min: 1, step: 1, value: newWindow.value,
                onInput: event => { newWindow.value = event.target.value },
              }),
              h('button', { type: 'submit' }, 'Save window'),
            ]),
          ])
        })),
    ])
  },
}
