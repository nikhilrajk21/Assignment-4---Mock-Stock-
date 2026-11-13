import { h, onMounted, onUnmounted, ref, shallowRef } from 'vue'

function gatherIce(peer, signal) {
  if (peer.iceGatheringState === 'complete') return Promise.resolve()
  return new Promise((resolve, reject) => {
    function finish(error) {
      clearTimeout(timer)
      peer.removeEventListener('icegatheringstatechange', check)
      signal.removeEventListener('abort', abort)
      if (error) reject(error)
      else resolve()
    }
    function check() {
      if (peer.iceGatheringState === 'complete') finish()
    }
    function abort() { finish(new DOMException('Voice session ended', 'AbortError')) }
    const timer = setTimeout(() => finish(new Error('Timed out gathering connection details.')), 10000)
    signal.addEventListener('abort', abort, { once: true })
    peer.addEventListener('icegatheringstatechange', check)
    check()
  })
}

export default {
  props: { newest: Object },
  setup(props) {
    const choices = shallowRef([])
    const selected = ref('')
    const phase = ref('idle')
    const microphone = ref(false)
    const microphoneDevices = shallowRef([])
    const microphoneId = ref('')
    const signalDetected = ref(false)
    const message = ref('')
    const userTranscript = ref('')
    const assistantTranscript = ref('')
    const output = ref(null)
    let session

    async function refresh() {
      try {
        const response = await fetch('/api/decisions')
        if (!response.ok) throw new Error('Could not load saved decisions.')
        choices.value = await response.json()
        if (!selected.value) selected.value = choices.value[0]?.id ?? ''
      } catch (error) {
        message.value = error.message
      }
    }

    async function refreshMicrophones() {
      try {
        const devices = await navigator.mediaDevices?.enumerateDevices()
        microphoneDevices.value = devices?.filter(device => device.kind === 'audioinput' && device.deviceId && device.deviceId !== 'default') ?? []
      } catch {
        microphoneDevices.value = []
      }
    }

    onMounted(() => {
      refresh()
      refreshMicrophones()
    })
    function releaseMic(active) {
      active.media?.getTracks().forEach(track => track.stop())
      microphone.value = false
      signalDetected.value = false
      clearInterval(active.levelTimer)
      active.audioContext?.close().catch(() => {})
    }
    function cleanup(active) {
      if (session !== active) return
      session = undefined
      active.abort.abort()
      clearTimeout(active.timer)
      releaseMic(active)
      active.events?.close()
      active.peer?.close()
      if (output.value) output.value.srcObject = null
      phase.value = 'idle'
    }
    function stop() {
      const active = session
      if (!active) return
      if (phase.value !== 'connected' || active.events?.readyState !== 'open') {
        cleanup(active)
        message.value = 'Voice session ended.'
        return
      }
      phase.value = 'ending'
      releaseMic(active)
      try {
        active.events.send(JSON.stringify({ type: 'session.close' }))
      } catch {
        cleanup(active)
        message.value = 'Voice session closed locally.'
        return
      }
      clearTimeout(active.timer)
      active.timer = setTimeout(() => {
        cleanup(active)
        message.value = 'Voice session closed locally.'
      }, 15000)
    }

    async function start() {
      if (session || !selected.value) return
      const decisionId = selected.value
      userTranscript.value = ''
      assistantTranscript.value = ''
      const active = { abort: new AbortController() }
      session = active
      phase.value = 'connecting'
      message.value = 'Requesting microphone access…'
      try {
        const audio = { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
        if (microphoneId.value) audio.deviceId = { exact: microphoneId.value }
        const media = await navigator.mediaDevices.getUserMedia({ audio })
        if (session !== active) {
          media.getTracks().forEach(track => track.stop())
          return
        }
        active.media = media
        microphone.value = true
        refreshMicrophones()
        try {
          const audioContext = new AudioContext()
          active.audioContext = audioContext
          const analyser = audioContext.createAnalyser()
          audioContext.createMediaStreamSource(media).connect(analyser)
          const samples = new Float32Array(analyser.fftSize)
          active.levelTimer = setInterval(() => {
            analyser.getFloatTimeDomainData(samples)
            signalDetected.value = signalDetected.value || samples.some(sample => Math.abs(sample) > 0.015)
          }, 150)
        } catch {
          // Audio-level monitoring is optional. The media track still streams.
        }
        message.value = 'Connecting voice…'
        const peer = new RTCPeerConnection()
        active.peer = peer
        const events = peer.createDataChannel('oai-events')
        active.events = events
        const disconnected = () => {
          if (session !== active) return
          cleanup(active)
          message.value = 'Voice connection closed.'
        }
        peer.addEventListener('connectionstatechange', () => {
          if (['failed', 'closed', 'disconnected'].includes(peer.connectionState)) disconnected()
        })
        events.addEventListener('close', disconnected)
        events.addEventListener('message', ({ data }) => {
          if (session !== active) return
          let event
          try { event = JSON.parse(data) } catch { return }
          if (event.type === 'session.started' && phase.value === 'connecting') {
            clearTimeout(active.timer)
            phase.value = 'connected'
            message.value = 'Connected. Ask about the saved decision.'
          } else if (event.type === 'session.input_transcript.delta' && typeof event.delta === 'string') {
            userTranscript.value += event.delta
          } else if (event.type === 'session.output_transcript.delta' && typeof event.delta === 'string') {
            assistantTranscript.value += event.delta
          } else if (event.type === 'error') {
            message.value = event.error?.message ?? 'Voice session reported an error.'
          } else if (event.type === 'session.closed') {
            cleanup(active)
            message.value = 'Voice session ended.'
          }
        })
        peer.addEventListener('track', event => {
          if (session !== active || !output.value) return
          output.value.srcObject = event.streams[0] ?? new MediaStream([event.track])
          output.value.play().catch(() => { message.value = 'Use the audio controls to play the reply.' })
        })
        for (const track of media.getAudioTracks()) peer.addTrack(track, media)
        await peer.setLocalDescription(await peer.createOffer())
        await gatherIce(peer, active.abort.signal)
        active.timer = setTimeout(() => {
          cleanup(active)
          message.value = 'Voice connection timed out.'
        }, 25000)
        const response = await fetch('/api/voice/sessions', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ decision_id: decisionId, sdp: peer.localDescription.sdp }),
          signal: active.abort.signal,
        })
        const result = await response.json()
        if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Voice session could not start.')
        if (session !== active) return
        await peer.setRemoteDescription({ type: 'answer', sdp: result.transport.sdp })
      } catch (error) {
        if (session !== active) return
        cleanup(active)
        message.value = error.name === 'NotAllowedError' ? 'Microphone access was denied.' : error.message
      }
    }

    onUnmounted(() => { if (session) cleanup(session) })

    return () => {
      const saved = props.newest && !choices.value.some(choice => choice.id === props.newest.id)
        ? [props.newest, ...choices.value] : choices.value
      const current = saved.find(choice => choice.id === selected.value)
      return h('section', { 'aria-labelledby': 'voice-title' }, [
        h('h3', { id: 'voice-title' }, 'Discuss a decision'),
        h('label', { for: 'voice-decision' }, 'Saved decision'),
        h('select', {
          id: 'voice-decision', value: selected.value, disabled: phase.value !== 'idle',
          onChange: event => { selected.value = event.target.value },
        }, [h('option', { value: '' }, 'Choose a decision'), ...saved.map(choice =>
          h('option', { key: choice.id, value: choice.id }, choice.id + ' · ' + (choice.proposal ?? choice.status)))]),
        h('button', { type: 'button', onClick: refresh, disabled: phase.value !== 'idle' }, 'Refresh decisions'),
        current && h('p', 'Selected decision ' + current.id + ' · ' + current.status),
        microphoneDevices.value.length > 0 && h('label', [
          'Microphone input ',
          h('select', {
            value: microphoneId.value, disabled: phase.value !== 'idle',
            onChange: event => { microphoneId.value = event.target.value },
          }, [h('option', { value: '' }, 'System default'), ...microphoneDevices.value.map((device, index) =>
            h('option', { key: device.deviceId, value: device.deviceId }, device.label || 'Microphone ' + (index + 1)))]),
        ]),
        h('button', { type: 'button', onClick: start, disabled: !selected.value || phase.value !== 'idle' }, 'Start voice'),
        h('button', { type: 'button', onClick: stop, disabled: phase.value === 'idle' || phase.value === 'ending' }, 'End voice'),
        h('p', { role: 'status' }, microphone.value ? 'Microphone active' : 'Microphone inactive'),
        message.value && h('p', { role: 'status' }, message.value),
        microphone.value && h('p', signalDetected.value ? 'Microphone input detected.' : 'Waiting for microphone input.'),
        userTranscript.value && h('p', { 'aria-label': 'What you said' }, 'You: ' + userTranscript.value),
        assistantTranscript.value && h('p', { 'aria-label': 'Assistant reply' }, 'Assistant: ' + assistantTranscript.value),
        h('audio', { ref: output, controls: true, autoplay: true, 'aria-label': 'Decision conversation audio' }),
      ])
    }
  },
}
