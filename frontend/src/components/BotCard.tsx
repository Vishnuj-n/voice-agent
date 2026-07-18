import type { Bot } from '../types'

interface BotCardProps {
  bot: Bot
  isSelected: boolean
  onSelect: (id: string) => void
}

export function BotCard({ bot, isSelected, onSelect }: BotCardProps) {
  return (
    <button
      className={`bot-card ${isSelected ? 'selected' : ''} ${!bot.enabled ? 'disabled' : ''}`}
      onClick={() => bot.enabled && onSelect(bot.id)}
      disabled={!bot.enabled}
      title={!bot.enabled ? 'Available in Sprint 4' : undefined}
    >
      <span className="bot-icon">{bot.enabled ? '✅' : '⏳'}</span>
      <span className="bot-name">{bot.name}</span>
    </button>
  )
}
