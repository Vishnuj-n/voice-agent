export function Architecture() {
  return (
    <div className="architecture">
      <section>
        <h2>Modular Providers</h2>
        <div className="arch-grid">
          <div className="arch-card">
            <h3>Transport</h3>
            <p>Audio I/O abstraction — Local mic/speaker, Browser WebSocket, future Twilio</p>
          </div>
          <div className="arch-card">
            <h3>STT Provider</h3>
            <p>Speech-to-Text — Groq Whisper (whisper-large-v3-turbo)</p>
          </div>
          <div className="arch-card">
            <h3>LLM Provider</h3>
            <p>Language Model — Groq Llama 3.3 70B via PydanticAI, streaming</p>
          </div>
          <div className="arch-card">
            <h3>TTS Provider</h3>
            <p>Text-to-Speech — Cartesia Sonic, streaming</p>
          </div>
          <div className="arch-card">
            <h3>Provider Registry</h3>
            <p>Config-driven provider selection and instantiation</p>
          </div>
        </div>
      </section>

      <section>
        <h2>Streaming Pipeline</h2>
        <div className="pipeline-flow">
          <span className="flow-node">Browser</span>
          <span className="flow-arrow">&rarr;</span>
          <span className="flow-node">STT</span>
          <span className="flow-arrow">&rarr;</span>
          <span className="flow-node">LLM</span>
          <span className="flow-arrow">&rarr;</span>
          <span className="flow-node">Streaming TTS</span>
          <span className="flow-arrow">&rarr;</span>
          <span className="flow-node">Browser</span>
        </div>
        <p className="pipeline-note">
          LLM output streams into TTS incrementally — audio playback begins before the full response is generated.
        </p>
      </section>

      <section>
        <h2>Benefits</h2>
        <ul className="benefits-list">
          <li><strong>Modular</strong> — swap any provider with a config change</li>
          <li><strong>Streaming</strong> — low latency, audio starts before response completes</li>
          <li><strong>Concurrent Processing</strong> — LLM and TTS run in parallel</li>
          <li><strong>Low Latency</strong> — designed for 1-2s end-to-end response</li>
          <li><strong>Provider Swapping</strong> — Groq, Cartesia, OpenAI via adapter pattern</li>
        </ul>
      </section>

      <section>
        <h2>Current Features</h2>
        <ul className="features-list">
          <li>Healthcare Bot</li>
          <li>Streaming Voice Pipeline</li>
          <li>Browser Transport</li>
          <li>WebSockets</li>
          <li>Live Metrics</li>
        </ul>
      </section>

      <section>
        <h2>Planned Features</h2>
        <ul className="planned-list">
          <li>Travel Bot</li>
          <li>Finance Bot</li>
          <li>Legal Bot</li>
          <li>RAG with pgvector</li>
          <li>Persistent Conversations</li>
        </ul>
      </section>
    </div>
  )
}
