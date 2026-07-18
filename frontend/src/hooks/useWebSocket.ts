import { useEffect, useRef, useState, useCallback } from 'react'
import type { ConnectionState, Bot, Metrics, ChatMessage } from '../types'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const WS_URL = API_URL.replace(/^http/, 'ws') + '/ws'

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected')
  const [bots, setBots] = useState<Bot[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [error, setError] = useState<string | null>(null)
  const audioChunksRef = useRef<string[]>([])

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      setConnectionState('connected')
      setError(null)
    }

    ws.onclose = () => {
      setConnectionState('disconnected')
      wsRef.current = null
    }

    ws.onerror = () => {
      setError('WebSocket connection failed')
      setConnectionState('disconnected')
    }

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)

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
          audioChunksRef.current = []
          break

        case 'audio_chunk':
          audioChunksRef.current.push(msg.data)
          break

        case 'audio_end':
          playAudioChunks(audioChunksRef.current)
          audioChunksRef.current = []
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
    wsRef.current?.close()
    wsRef.current = null
    setConnectionState('disconnected')
  }, [])

  const sendMessage = useCallback((msg: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg))
    }
  }, [])

  const sendAudioChunk = useCallback((base64Data: string) => {
    sendMessage({ type: 'audio_chunk', data: base64Data })
  }, [sendMessage])

  const startListening = useCallback(() => {
    sendMessage({ type: 'start_listening' })
  }, [sendMessage])

  const stopListening = useCallback(() => {
    sendMessage({ type: 'stop_listening' })
  }, [sendMessage])

  const selectBot = useCallback(
    (botId: string) => {
      sendMessage({ type: 'select_bot', bot: botId })
    },
    [sendMessage]
  )

  const clearError = useCallback(() => setError(null), [])

  useEffect(() => {
    connect()
    return () => disconnect()
  }, [connect, disconnect])

  return {
    connectionState,
    bots,
    messages,
    metrics,
    error,
    clearError,
    sendAudioChunk,
    startListening,
    stopListening,
    selectBot,
    connect,
    disconnect,
  }
}

async function playAudioChunks(chunks: string[]) {
  if (chunks.length === 0) return

  const audioContext = new AudioContext({ sampleRate: 44100 })

  // Decode base64 chunks into float32 audio data
  const float32Arrays: Float32Array[] = []
  for (const b64 of chunks) {
    const binary = atob(b64)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i)
    }
    // pcm_f32le: each sample is 4 bytes (float32)
    const float32 = new Float32Array(bytes.buffer)
    float32Arrays.push(float32)
  }

  // Concatenate all chunks
  const totalLength = float32Arrays.reduce((acc, arr) => acc + arr.length, 0)
  const combined = new Float32Array(totalLength)
  let offset = 0
  for (const arr of float32Arrays) {
    combined.set(arr, offset)
    offset += arr.length
  }

  // Create AudioBuffer and play
  const audioBuffer = audioContext.createBuffer(1, combined.length, 44100)
  audioBuffer.getChannelData(0).set(combined)

  const source = audioContext.createBufferSource()
  source.buffer = audioBuffer
  source.connect(audioContext.destination)
  source.start()
}
