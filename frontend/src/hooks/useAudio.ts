import { useRef, useCallback, useState } from 'react'

export function useAudio(onChunk: (base64: string) => void) {
  const [isRecording, setIsRecording] = useState(false)
  const streamRef = useRef<MediaStream | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)

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

      const source = audioContext.createMediaStreamSource(stream)
      // ScriptProcessorNode with 4096 buffer, 1 input channel, 1 output channel
      const processor = audioContext.createScriptProcessor(4096, 1, 1)
      processorRef.current = processor

      processor.onaudioprocess = (event) => {
        const inputData = event.inputBuffer.getChannelData(0)
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
    } catch (err) {
      console.error('Microphone access denied:', err)
      throw err
    }
  }, [onChunk])

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
