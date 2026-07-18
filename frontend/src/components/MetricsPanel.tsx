import type { Metrics } from '../types'

interface MetricsPanelProps {
  metrics: Metrics | null
}

const METRIC_ITEMS = [
  { key: 'stt_ms' as const, label: 'STT' },
  { key: 'llm_total_ms' as const, label: 'LLM Total' },
  { key: 'llm_time_to_first_token_ms' as const, label: 'TTFT' },
  { key: 'tts_total_ms' as const, label: 'TTS Total' },
  { key: 'tts_time_to_first_audio_ms' as const, label: 'TTFA' },
  { key: 'total_ms' as const, label: 'Total' },
]

export function MetricsPanel({ metrics }: MetricsPanelProps) {
  return (
    <div className="metrics-panel">
      <h3>Metrics</h3>
      <div className="metrics-grid">
        {METRIC_ITEMS.map(({ key, label }) => (
          <div key={key} className="metric-item">
            <span className="metric-label">{label}</span>
            <span className="metric-value">
              {metrics ? `${metrics[key]}ms` : '--'}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
