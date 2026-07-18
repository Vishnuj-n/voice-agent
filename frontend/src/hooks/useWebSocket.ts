import { useRef, useState, useCallback, type MutableRefObject } from 'react'
import type { ConnectionState, Bot, Metrics, ChatMessage } from '../types'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const WS_URL = API_URL.replace(/^http/, 'ws') + '/ws'

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected')
  const [sessionActive, setSessionActive] = useState(false)
  const [bots, setBots] = useState<Bot[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Persistent AudioContext — must be created inside a user gesture to satisfy
  // the browser autoplay policy. Call initAudio() on the "Start" button click.
  const audioCtxRef = useRef<AudioContext | null>(null)
  // Streaming audio scheduler state
  const audioFormatRef = useRef<{ sample_rate: number; channels: number; encoding: string } | null>(null)
  const nextPlayTimeRef = useRef<number>(0)
  // Track active audio sources so we can stop them on cancel
  const activeSourcesRef = useRef<AudioBufferSourceNode[]>([])

  const connect = useCallback(() => {
    const existing = wsRef.current
    if (existing) {
      if (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING) return
    }

    console.log('[WS] Connecting to', WS_URL)
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      console.log('[WS] Connected')
      setConnectionState('connected')
      setError(null)
    }

    ws.onclose = (event) => {
      console.log('[WS] Disconnected', event.code, event.reason)
      if (wsRef.current === ws) {
        wsRef.current = null
        setConnectionState('disconnected')
        setSessionActive(false)
      }
    }

    ws.onerror = (event) => {
      console.error('[WS] Error:', event)
      setError('WebSocket connection failed')
      setConnectionState('disconnected')
    }

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      console.log('[WS] Received:', msg.type)

      switch (msg.type) {
        case 'status':
          setConnectionState(msg.state as ConnectionState)
          break

        case 'bots':
          setBots(msg.bots)
          break

        case 'transcript':
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              text: msg.text,
              speaker: msg.speaker,
              timestamp: Date.now(),
            },
          ])
          break

        case 'response_text':
          setMessages((prev) => {
            const last = prev[prev.length - 1]
            if (last && last.speaker === 'assistant') {
              return [...prev.slice(0, -1), { ...last, text: last.text + msg.text }]
            }
            return [
              ...prev,
              {
                id: crypto.randomUUID(),
                text: msg.text,
                speaker: 'assistant',
                timestamp: Date.now(),
              },
            ]
          })
          break

        case 'audio_start':
          audioFormatRef.current = msg.format ?? null
          nextPlayTimeRef.current = 0
          break

        case 'audio_chunk': {
          const ctx = audioCtxRef.current
          if (!ctx) { console.warn('[WS] AudioContext not ready'); break }
          ctx.resume().then(() => {
            scheduleAudioChunk(msg.data, ctx, audioFormatRef.current, nextPlayTimeRef, activeSourcesRef)
          })
          break
        }

        case 'audio_end':
          console.log('[WS] Audio stream complete')
          break

        case 'metrics':
          setMetrics(msg as Metrics)
          break

        case 'error':
          setError(msg.message)
          break
      }
    }
  }, [])

  const disconnect = useCallback(() => {
    const ws = wsRef.current
    if (!ws) return
    console.log('[WS] Disconnecting, readyState:', ws.readyState)
    if (ws.readyState === WebSocket.OPEN) {
      ws.close()
    }
    wsRef.current = null
    setConnectionState('disconnected')
  }, [])

  const sendMessage = useCallback((msg: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg))
    } else {
      console.warn('[WS] Cannot send, readyState:', wsRef.current?.readyState)
    }
  }, [])

  const initAudio = useCallback(() => {
    if (!audioCtxRef.current || audioCtxRef.current.state === 'closed') {
      audioCtxRef.current = new AudioContext()
      console.log('[WS] AudioContext created, sampleRate:', audioCtxRef.current.sampleRate)
    } else if (audioCtxRef.current.state === 'suspended') {
      audioCtxRef.current.resume()
    }
  }, [])

  let audioChunkCount = 0
  // connectionState is captured via a ref so the callback always sees the
  // latest value without needing to be recreated (avoids stale-closure issues).
  const connectionStateRef = useRef<ConnectionState>('disconnected')
  connectionStateRef.current = connectionState

  const sendAudioChunk = useCallback((pcmData: ArrayBuffer) => {
    // Drop mic audio while the bot is thinking or speaking.
    // This is the primary guard against phantom transcriptions: without it,
    // chunks captured during TTS playback accumulate in the server buffer and
    // are fed to STT at the start of the next turn — producing "Thank you"
    // and other echo artifacts.
    const state = connectionStateRef.current
    if (state !== 'listening') return

    audioChunkCount++
    if (audioChunkCount % 50 === 1) {
      console.log(`[WS] Audio chunks sent: ${audioChunkCount}`)
    }
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(pcmData)
    }
  }, [])

  const startSession = useCallback(() => {
    setSessionActive(true)
    sendMessage({ type: 'start_session' })
  }, [sendMessage])

  const stopSession = useCallback(() => {
    setSessionActive(false)
    // Stop any active audio playback immediately
    for (const src of activeSourcesRef.current) {
      try { src.stop() } catch { /* already stopped */ }
    }
    activeSourcesRef.current = []
    nextPlayTimeRef.current = 0

    sendMessage({ type: 'stop_session' })
  }, [sendMessage])

  const selectBot = useCallback(
    (botId: string) => {
      sendMessage({ type: 'select_bot', bot: botId })
    },
    [sendMessage]
  )

  const clearError = useCallback(() => setError(null), [])

  return {
    connectionState,
    sessionActive,
    bots,
    messages,
    metrics,
    error,
    clearError,
    initAudio,
    sendAudioChunk,
    startSession,
    stopSession,
    selectBot,
    connect,
    disconnect,
  }
}

/**
 * Schedule a single base64-encoded PCM audio chunk for immediate gapless playback.
 *
 * Uses the AudioContext clock (ctx.currentTime) to chain chunks back-to-back:
 * nextPlayTimeRef tracks the end time of the last scheduled buffer so each new
 * chunk is queued exactly where the previous one ends — producing seamless,
 * low-latency streaming audio without waiting for audio_end.
 */
function scheduleAudioChunk(
  b64: string,
  ctx: AudioContext,
  format: { sample_rate: number; channels: number; encoding: string } | null,
  nextPlayTimeRef: MutableRefObject<number>,
  activeSourcesRef: MutableRefObject<AudioBufferSourceNode[]>,
) {
  const sampleRate = format?.sample_rate ?? 44100
  const numChannels = format?.channels ?? 1
  const encoding = format?.encoding ?? 'pcm_f32le'

  // Decode base64 → raw bytes
  const binary = atob(b64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)

  // Decode PCM encoding → Float32
  let channelData: Float32Array
  if (encoding === 'pcm_f32le' || encoding === 'float32') {
    channelData = new Float32Array(bytes.buffer)
  } else if (encoding === 'pcm_s16le' || encoding === 'int16') {
    const int16 = new Int16Array(bytes.buffer)
    channelData = new Float32Array(int16.length)
    for (let i = 0; i < int16.length; i++) channelData[i] = int16[i] / 32768.0
  } else {
    channelData = new Float32Array(bytes.buffer)
  }

  const numSamples = channelData.length / numChannels
  const audioBuffer = ctx.createBuffer(numChannels, numSamples, sampleRate)
  for (let ch = 0; ch < numChannels; ch++) {
    audioBuffer.getChannelData(ch).set(channelData.subarray(ch * numSamples, (ch + 1) * numSamples))
  }

  const startAt = Math.max(ctx.currentTime, nextPlayTimeRef.current)
  nextPlayTimeRef.current = startAt + audioBuffer.duration

  const source = ctx.createBufferSource()
  source.buffer = audioBuffer
  source.connect(ctx.destination)
  source.start(startAt)
  activeSourcesRef.current.push(source)
  source.onended = () => {
    const idx = activeSourcesRef.current.indexOf(source)
    if (idx !== -1) activeSourcesRef.current.splice(idx, 1)
  }
}
