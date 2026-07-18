import { useState } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import { VoiceAgent } from './components/VoiceAgent'
import { Architecture } from './components/Architecture'

type Tab = 'voice' | 'architecture'

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('voice')
  const ws = useWebSocket()

  return (
    <div className="app">
      <header className="app-header">
        <h1>Voice Agent</h1>
        <nav className="tabs">
          <button
            className={`tab ${activeTab === 'voice' ? 'active' : ''}`}
            onClick={() => setActiveTab('voice')}
          >
            Voice Agent
          </button>
          <button
            className={`tab ${activeTab === 'architecture' ? 'active' : ''}`}
            onClick={() => setActiveTab('architecture')}
          >
            Architecture
          </button>
        </nav>
      </header>

      <main className="app-main">
        {activeTab === 'voice' ? (
          <VoiceAgent
            connectionState={ws.connectionState}
            bots={ws.bots}
            messages={ws.messages}
            metrics={ws.metrics}
            error={ws.error}
            clearError={ws.clearError}
            sendAudioChunk={ws.sendAudioChunk}
            startListening={ws.startListening}
            stopListening={ws.stopListening}
            selectBot={ws.selectBot}
          />
        ) : (
          <Architecture />
        )}
      </main>
    </div>
  )
}

export default App
