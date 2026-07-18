import type { ConnectionState } from '../types'

const STATE_LABELS: Record<ConnectionState, string> = {
  connected: 'Connected',
  listening: 'Listening...',
  thinking: 'Thinking...',
  speaking: 'Speaking...',
  disconnected: 'Disconnected',
}

const STATE_COLORS: Record<ConnectionState, string> = {
  connected: '#22c55e',
  listening: '#3b82f6',
  thinking: '#f59e0b',
  speaking: '#a855f7',
  disconnected: '#6b7280',
}

export function StatusBar({ state }: { state: ConnectionState }) {
  return (
    <div className="status-bar">
      <span
        className="status-dot"
        style={{ backgroundColor: STATE_COLORS[state] }}
      />
      <span>{STATE_LABELS[state]}</span>
    </div>
  )
}
