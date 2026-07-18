import { useCallback } from 'react'
import type { ConnectionState, Bot, ChatMessage, Metrics } from '../types'
import { useAudio } from '../hooks/useAudio'
import { BotCard } from './BotCard'
import { MetricsPanel } from './MetricsPanel'
import { StatusBar } from './StatusBar'

interface VoiceAgentProps {
  connectionState: ConnectionState
  sessionActive: boolean
  bots: Bot[]
  messages: ChatMessage[]
  metrics: Metrics | null
  error: string | null
  clearError: () => void
  initAudio: () => void
  sendAudioChunk: (pcmData: ArrayBuffer) => void
  startSession: () => void
  stopSession: () => void
  selectBot: (id: string) => void
  connect: () => void
  disconnect: () => void
}

export function VoiceAgent({
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
}: VoiceAgentProps) {
  const { isRecording, startRecording, stopRecording } = useAudio({
    onChunk: sendAudioChunk,
  })

  const handleStart = useCallback(async () => {
    try {
      // initAudio MUST run first — we are inside a click handler (user gesture).
      // This unlocks AudioContext playback for TTS audio received later.
      initAudio()
      // Connect WS if not already connected
      if (connectionState !== 'connected') {
        connect()
        await new Promise((r) => setTimeout(r, 500))
      }
      // Tell backend to start the conversation session BEFORE mic streaming,
      // so the backend is ready to receive audio_chunk messages. Without this
      // ordering, the backend drops all chunks that arrive before
      // conversation_task is created (api.py:199).
      startSession()
      await startRecording()
    } catch (err) {
      console.error('[VoiceAgent] Failed to start:', err)
    }
  }, [connectionState, connect, initAudio, startRecording, startSession])

  const handleStop = useCallback(() => {
    stopRecording()
    stopSession()
  }, [stopRecording, stopSession])

  const selectedBot = bots.find((b) => b.enabled)?.id || 'healthcare'

  return (
    <div className="voice-agent">
      <div className="bots-row">
        {bots.map((bot) => (
          <BotCard
            key={bot.id}
            bot={bot}
            isSelected={bot.id === selectedBot}
            onSelect={selectBot}
          />
        ))}
      </div>

      <StatusBar state={connectionState} />

      {error && (
        <div className="error-banner" onClick={clearError}>
          {error}
          <span className="error-dismiss">dismiss</span>
        </div>
      )}

      <div className="chat-area">
        {messages.length === 0 && (
          <div className="chat-empty">
            Press Start Conversation and speak to the Healthcare bot.
          </div>
        )}
        {messages.map((msg) => (
          <div key={msg.id} className={`chat-bubble ${msg.speaker}`}>
            <div className="bubble-label">{msg.speaker === 'user' ? 'You' : 'Bot'}</div>
            <div className="bubble-text">{msg.text}</div>
          </div>
        ))}
      </div>

      <div className="controls">
        <button
          className="btn btn-start"
          onClick={handleStart}
          disabled={sessionActive}
        >
          Start Conversation
        </button>
        <button
          className="btn btn-stop"
          onClick={handleStop}
          disabled={!sessionActive}
        >
          Stop Conversation
        </button>
      </div>

      <MetricsPanel metrics={metrics} />
    </div>
  )
}
