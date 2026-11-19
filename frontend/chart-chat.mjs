import { h, onUnmounted, ref } from 'vue'
import { captureDecisionChart } from './decision-capture.mjs'

function toolOutput(call) {
  const answer = call.result
  if (call.tool === 'read_decision_rules') {
    return h('ul', answer.choices.map(choice => h('li', { key: choice.value },
      `${choice.value.toUpperCase()} — ${choice.description}`)))
  }
  if (answer.error) return h('p', answer.error)
  const snapshot = answer.snapshot
  const probability = answer.probability == null ? 'unavailable' : `${(answer.probability * 100).toFixed(1)}%`
  return h('p', `${snapshot.symbol} · ${snapshot.timestamp} · ${snapshot.market_data_label} · ${answer.choice.toUpperCase()} · Choice probability ${probability}`)
}

export default {
  props: { selection: Object, visibleRange: Function, post: Function },
  setup(props) {
    const turns = ref([])
    const text = ref('')
    const error = ref('')
    const busy = ref(false)
    const attached = ref(true)
    let id = null
    let request = null
    onUnmounted(() => request?.abort())

    function reset() {
      request?.abort()
      request = null
      turns.value = []
      text.value = ''
      error.value = ''
      busy.value = false
      id = null
    }

    async function send(event) {
      event.preventDefault()
      const message = text.value.trim()
      if (!message || busy.value) return
      const controller = new AbortController()
      request = controller
      busy.value = true
      error.value = ''
      const selection = attached.value && props.selection?.timeframe === '1m' ? props.selection : null
      const range = selection ? props.visibleRange() : null
      try {
        let capture = null
        if (selection) {
          const snapshot = await props.post('/api/decision-snapshots', selection, controller.signal)
          capture = { snapshot_id: snapshot.id, ...await captureDecisionChart(snapshot, range) }
        }
        const answer = await props.post('/api/chart-chat', { conversation_id: id, message, capture }, controller.signal)
        if (request !== controller || controller.signal.aborted) return
        id = answer.conversation_id
        turns.value.push({ question: message, answer })
        text.value = ''
      } catch (failure) {
        if (!controller.signal.aborted) error.value = failure.message
      } finally {
        if (request === controller) busy.value = false
      }
    }

    return () => h('section', { 'aria-labelledby': 'chart-chat-title' }, [
      h('h3', { id: 'chart-chat-title' }, 'Chart chat'),
      h('button', { type: 'button', onClick: reset }, 'New chat'),
      h('ol', { 'aria-label': 'Chat messages', 'aria-live': 'polite' }, turns.value.map(({ question, answer }, index) =>
        h('li', { key: index }, [h('p', question), h('p', answer.message),
          ...answer.calls.map((call, i) => h('details', { key: i }, [
            h('summary', call.tool === 'read_decision_rules' ? 'Rules used' : 'Chart assessment used'), toolOutput(call),
          ])),
        ]))),
      h('form', { onSubmit: send }, [
        h('label', [h('input', { type: 'checkbox', checked: attached.value, disabled: props.selection?.timeframe !== '1m',
          onChange: event => { attached.value = event.target.checked } }), ' Include selected one-minute chart']),
        h('label', [' Message ', h('input', { value: text.value, maxlength: 2000, required: true, disabled: busy.value,
          onInput: event => { text.value = event.target.value }, placeholder: 'What does WAIT mean?' })]),
        h('button', { type: 'submit', disabled: busy.value }, busy.value ? 'Waiting for reply…' : 'Send'),
      ]),
      error.value && h('p', { role: 'status' }, error.value),
    ])
  },
}
