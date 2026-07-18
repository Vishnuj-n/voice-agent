import { useRef, useCallback, useState } from 'react'

interface UseAudioOptions {
  onChunk: (base64: string) => void
  onSpeechEnd?: () => void
  silenceThreshold?: number   // RMS energy threshold (default 300, matches CLI)
  silenceDuration?: number    // seconds of silence before auto-stop (default 1.5)
  maxDuration?: number        // max recording seconds (default 10)
}

export function useAudio({
  onChunk,
  onSpeechEnd,
  silenceThreshold = 300,
  silenceDuration = 1.5,
  maxDuration = 10,
}: UseAudioOptions) {
  const [isRecording, setIsRecording] = useState(false)
  const streamRef = useRef<MediaStream | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)

  // VAD state refs (mutable across renders without causing re-renders)
  const speechStartedRef = useRef(false)
  const consecutiveSilenceRef = useRef(0)
  const chunksRecordedRef = useRef(0)
  const onSpeechEndRef = useRef(onSpeechEnd)
  onSpeechEndRef.current = onSpeechEnd

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      })

      streamRef.current = stream
      const audioContext = new AudioContext({ sampleRate: 16000 })
      audioContextRef.current = audioContext

      // Reset VAD state
      speechStartedRef.current = false
      consecutiveSilenceRef.current = 0
      chunksRecordedRef.current = 0

      const source = audioContext.createMediaStreamSource(stream)
      // ScriptProcessorNode with 4096 buffer, 1 input channel, 1 output channel
      const processor = audioContext.createScriptProcessor(4096, 1, 1)
      processorRef.current = processor

      // VAD constants (matching CLI: chunk_size=1600 @ 16kHz = 0.1s per chunk)
      const SAMPLE_RATE = 16000
      const CHUNK_SIZE = 4096  // script processor buffer
      const SILENCE_CHUNKS_LIMIT = Math.floor(silenceDuration / (CHUNK_SIZE / SAMPLE_RATE))
      const MAX_CHUNKS = Math.floor(maxDuration / (CHUNK_SIZE / SAMPLE_RATE))
      const WARMUP_CHUNKS = Math.floor(3.0 / (CHUNK_SIZE / SAMPLE_RATE))  // 3s warmup
      let logCounter = 0

      processor.onaudioprocess = (event) => {
        const inputData = event.inputBuffer.getChannelData(0)

        // Compute RMS energy for VAD
        let sumSquares = 0
        for (let i = 0; i < inputData.length; i++) {
          sumSquares += inputData[i] * inputData[i]
        }
        const rms = Math.sqrt(sumSquares / inputData.length) * 32768  // scale to int16 range

        chunksRecordedRef.current++
        logCounter++
        if (logCounter % 20 === 0) {
          console.log(`[VAD] chunk=${chunksRecordedRef.current} rms=${rms.toFixed(1)} threshold=${silenceThreshold} speech=${speechStartedRef.current}`)
        }

        // VAD logic (mirrors CLI LocalTransport._record)
        if (!speechStartedRef.current) {
          if (rms > silenceThreshold) {
            speechStartedRef.current = true
            console.log('[VAD] Speech detected')
          } else if (chunksRecordedRef.current >= WARMUP_CHUNKS) {
            console.log('[VAD] No speech detected in warmup, stopping')
            stopRecording()
            onSpeechEndRef.current?.()
            return
          }
        } else {
          // Speech was active — check for silence
          if (rms < silenceThreshold) {
            consecutiveSilenceRef.current++
          } else {
            consecutiveSilenceRef.current = 0
          }

          if (consecutiveSilenceRef.current >= SILENCE_CHUNKS_LIMIT) {
            console.log('[VAD] Silence detected, stopping')
            stopRecording()
            onSpeechEndRef.current?.()
            return
          }
        }

        // Max duration safety limit
        if (chunksRecordedRef.current >= MAX_CHUNKS) {
          console.log('[VAD] Max duration reached, stopping')
          stopRecording()
          onSpeechEndRef.current?.()
          return
        }

        // Convert Float32 to Int16 PCM
        const int16 = new Int16Array(inputData.length)
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]))
          int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
        }
        // Encode as base64
        const bytes = new Uint8Array(int16.buffer)
        let binary = ''
        for (let i = 0; i < bytes.length; i++) {
          binary += String.fromCharCode(bytes[i])
        }
        const base64 = btoa(binary)
        onChunk(base64)
      }

      source.connect(processor)
      processor.connect(audioContext.destination)
      setIsRecording(true)
      console.log('[VAD] Recording started, waiting for speech...')
    } catch (err) {
      console.error('Microphone access denied:', err)
      throw err
    }
  }, [onChunk, silenceThreshold, silenceDuration, maxDuration])

  const stopRecording = useCallback(() => {
    processorRef.current?.disconnect()
    processorRef.current = null
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    audioContextRef.current?.close()
    audioContextRef.current = null
    setIsRecording(false)
  }, [])

  return { isRecording, startRecording, stopRecording }
}
