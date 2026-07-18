import { useRef, useCallback, useState } from 'react'

interface UseAudioOptions {
  onChunk: (pcm16: ArrayBuffer) => void
}

export function useAudio({ onChunk }: UseAudioOptions) {
  const [isRecording, setIsRecording] = useState(false)
  const streamRef = useRef<MediaStream | null>(null)
  const contextRef = useRef<AudioContext | null>(null)
  const workletRef = useRef<AudioWorkletNode | null>(null)

  const startRecording = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
      },
    })

    streamRef.current = stream

    // Use native sample rate — the worklet handles resampling to 16 kHz
    const ctx = new AudioContext()
    contextRef.current = ctx

    await ctx.audioWorklet.addModule('/audio-processor.js')

    const worklet = new AudioWorkletNode(ctx, 'audio-processor')
    workletRef.current = worklet

    worklet.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
      onChunk(event.data)
    }

    const source = ctx.createMediaStreamSource(stream)
    source.connect(worklet)
    // Do NOT connect worklet to destination — that would play mic audio
    // through the speakers, causing the bot's TTS voice to be picked up
    // by the mic and fed back as "user speech" (feedback loop).

    setIsRecording(true)
    console.log('[Audio] Recording started via AudioWorklet')
  }, [onChunk])

  const stopRecording = useCallback(() => {
    workletRef.current?.disconnect()
    workletRef.current = null
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    contextRef.current?.close()
    contextRef.current = null
    setIsRecording(false)
    console.log('[Audio] Recording stopped')
  }, [])

  return { isRecording, startRecording, stopRecording }
}
