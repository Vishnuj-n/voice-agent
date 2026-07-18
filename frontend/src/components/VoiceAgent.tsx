import { useCallback } from 'react'
import type { ConnectionState, Bot, ChatMessage, Metrics } from '../types'
import { useAudio } from '../hooks/useAudio'
import { BotCard } from './BotCard'
import { MetricsPanel } from './MetricsPanel'
import { StatusBar } from './StatusBar'

interface VoiceAgentProps {
  connectionState: ConnectionState
  bots: Bot[]
  messages: ChatMessage[]
  metrics: Metrics | null
  error: string | null
  clearError: () => void
  sendAudioChunk: (base64: string) => void
  startListening: () => void
  stopListening: () => void
  selectBot: (id: string) => void
}

export function VoiceAgent({
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
}: VoiceAgentProps) {
  const { isRecording, startRecording, stopRecording } = useAudio(sendAudioChunk)

  const handleStart = useCallback(async () => {
    try {
      await startRecording()
      startListening()
    } catch {
      // Error handled by useAudio
    }
  }, [startRecording, startListening])

  const handleStop = useCallback(() => {
    stopRecording()
    stopListening()
  }, [stopRecording, stopListening])

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
            Press Start Listening and speak to the Healthcare bot.
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
          disabled={isRecording || connectionState !== 'connected'}
        >
          🎤 Start Listening
        </button>
        <button
          className="btn btn-stop"
          onClick={handleStop}
          disabled={!isRecording}
        >
          ⏹ Stop Listening
        </button>
      </div>

      <MetricsPanel metrics={metrics} />
    </div>
  )
}
