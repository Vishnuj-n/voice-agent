/**
 * AudioWorklet processor: captures mic audio, resamples to 16 kHz,
 * converts to Int16 PCM, and posts raw bytes to the main thread.
 * Runs off the main thread — no ScriptProcessorNode deprecation issues.
 */

const TARGET_SAMPLE_RATE = 16000;

class AudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = [];
    this.bufferDuration = 0;
    this.flushInterval = 0.1; // send every ~100 ms
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;

    const channelData = input[0];
    if (!channelData || channelData.length === 0) return true;

    this.buffer.push(new Float32Array(channelData));
    this.bufferDuration += channelData.length / sampleRate;

    if (this.bufferDuration >= this.flushInterval) {
      this.flush();
    }

    return true;
  }

  flush() {
    if (this.buffer.length === 0) return;

    const totalSamples = this.buffer.reduce((sum, chunk) => sum + chunk.length, 0);
    const concatenated = new Float32Array(totalSamples);
    let offset = 0;
    for (const chunk of this.buffer) {
      concatenated.set(chunk, offset);
      offset += chunk.length;
    }
    this.buffer = [];
    this.bufferDuration = 0;

    let resampled;
    if (sampleRate === TARGET_SAMPLE_RATE) {
      resampled = concatenated;
    } else {
      resampled = this.resample(concatenated, sampleRate, TARGET_SAMPLE_RATE);
    }

    // Float32 [-1,1] → Int16 [-32768, 32767]
    const int16 = new Int16Array(resampled.length);
    for (let i = 0; i < resampled.length; i++) {
      const s = Math.max(-1, Math.min(1, resampled[i]));
      int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }

    // Transfer the underlying ArrayBuffer (zero-copy)
    this.port.postMessage(int16.buffer, [int16.buffer]);
  }

  resample(input, fromRate, toRate) {
    const ratio = fromRate / toRate;
    const outputLength = Math.round(input.length / ratio);
    const output = new Float32Array(outputLength);

    for (let i = 0; i < outputLength; i++) {
      const srcIndex = i * ratio;
      const srcIndexFloor = Math.floor(srcIndex);
      const srcIndexCeil = Math.min(srcIndexFloor + 1, input.length - 1);
      const frac = srcIndex - srcIndexFloor;
      output[i] = input[srcIndexFloor] * (1 - frac) + input[srcIndexCeil] * frac;
    }

    return output;
  }
}

registerProcessor('audio-processor', AudioProcessor);
