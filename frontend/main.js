import CandleChart from './candle-chart.mjs'
import { createApp, h, ref } from 'vue'

createApp({
  setup() {
    const status = ref('Ready to check the backend.')

    async function checkHealth() {
      status.value = 'Checking backend...'
      try {
        const response = await fetch('/api/health')
        if (!response.ok) throw new Error('Health request failed')
        const result = await response.json()
        status.value = 'Backend status: ' + result.status
      } catch {
        status.value = 'Backend unavailable.'
      }
    }

    return () => [
      h('h1', 'Assignment 4'),
      h(CandleChart),
      h('button', { type: 'button', onClick: checkHealth }, 'Check backend status'),
      h('p', { role: 'status' }, status.value),
    ]
  },
}).mount('#app')
