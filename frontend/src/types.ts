export type ConnectionState = 'connected' | 'listening' | 'thinking' | 'speaking' | 'disconnected'

export interface Bot {
  id: string
  name: string
  enabled: boolean
}

export interface Metrics {
  stt_ms: number
  llm_total_ms: number
  llm_time_to_first_token_ms: number
  tts_time_to_first_audio_ms: number
  total_ms: number
}

export interface ChatMessage {
  id: string
  text: string
  speaker: 'user' | 'assistant'
  timestamp: number
}

export interface AudioFormat {
  sample_rate: number
  channels: number
  encoding: string
}
