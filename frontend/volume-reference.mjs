import { h, onUnmounted, ref, watch } from 'vue'

const shares = new Intl.NumberFormat('en-US')

export default {
  props: { timestamp: { type: String, required: true } },
  setup(props) {
    const busy = ref(false)
    const message = ref('')
    let request = null
    function reset() {
      request?.abort()
      request = null
      busy.value = false
      message.value = ''
    }
    watch(() => props.timestamp, reset)
    onUnmounted(reset)

    async function compare() {
      const controller = new AbortController()
      request = controller
      busy.value = true
      message.value = ''
      try {
        const query = new URLSearchParams({ timestamp: props.timestamp })
        const response = await fetch(`/api/volume-reference?${query}`, { signal: controller.signal })
        const data = await response.json()
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Yahoo volume is unavailable.')
        if (request === controller) message.value = data.volume == null
          ? 'Yahoo historical volume unavailable for this minute.'
          : `Yahoo historical volume: ${shares.format(data.volume)} shares · Retrieved ${data.retrieved_at}`
      } catch (error) {
        if (request === controller) message.value = error.message
      } finally {
        if (request === controller) busy.value = false
      }
    }

    return () => h('div', [
      h('button', { type: 'button', disabled: busy.value, onClick: compare },
        busy.value ? 'Loading historical volume…' : 'Compare with Yahoo historical volume'),
      message.value && h('p', { role: 'status' }, message.value),
    ])
  },
}
