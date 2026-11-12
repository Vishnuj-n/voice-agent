"""
Voice Agent Performance Benchmark Suite

Measures:
1. Isolated STT latency & accuracy (Audio -> Text)
2. Isolated LLM streaming latency (Time to First Token - TTFT, Tokens Per Second - TPS, Total Duration)
3. Isolated TTS streaming latency (Time to First Audio - TTFA, Total Synthesis Time)
4. End-to-End Pipeline Turn (Time to Ear - TTE, Full Turn Latency)

Usage:
    uv run python scripts/benchmark.py
    uv run python scripts/benchmark.py --iterations 3 --audio output.wav
    uv run python scripts/benchmark.py --prompt "What are the common symptoms of the seasonal flu?"
"""

import os
import sys
import time
import wave
import io
import math
import asyncio
import argparse
import statistics
from typing import AsyncIterator, List, Dict, Any

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import load_config
from providers.registry import get_stt_provider, get_tts_provider, get_llm_provider
from providers.base import Transport, AudioFormat
from core.pipeline import StreamingPipeline, TurnResult
from bots.healthcare import agent as healthcare_agent


class HeadlessBenchmarkTransport(Transport):
    """Headless transport that records audio chunks without opening hardware audio devices."""

    def __init__(self):
        self.received_chunks: List[bytes] = []
        self.first_chunk_received_at: float | None = None

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def read_audio(self) -> bytes:
        return b""

    async def write_audio(self, audio_data: bytes) -> bool:
        if self.first_chunk_received_at is None:
            self.first_chunk_received_at = time.perf_counter()
        self.received_chunks.append(audio_data)
        return True

    async def play_stream(
        self, audio_chunks: AsyncIterator[bytes], audio_format: AudioFormat
    ) -> None:
        async for chunk in audio_chunks:
            if self.first_chunk_received_at is None:
                self.first_chunk_received_at = time.perf_counter()
            self.received_chunks.append(chunk)


def generate_synthetic_wav(duration_s: float = 1.5, sample_rate: int = 16000) -> bytes:
    """Generates a clean synthetic 16kHz mono WAV tone to ensure benchmark runs even without audio files."""
    num_samples = int(sample_rate * duration_s)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(num_samples):
            # 440 Hz soft sine wave
            val = int(32767 * 0.1 * math.sin(2 * math.pi * 440 * (i / sample_rate)))
            frames.extend(val.to_bytes(2, byteorder="little", signed=True))
        wf.writeframes(frames)
    return buf.getvalue()


def format_stats(values: List[float], unit: str = "ms") -> str:
    """Helper to format min/mean/median/p90/max."""
    if not values:
        return "N/A"
    if len(values) == 1:
        return f"{values[0]:.1f} {unit}"
    mean_val = statistics.mean(values)
    med_val = statistics.median(values)
    min_val = min(values)
    max_val = max(values)
    return f"Mean: {mean_val:.1f}{unit} | Med: {med_val:.1f}{unit} | Min: {min_val:.1f}{unit} | Max: {max_val:.1f}{unit}"


async def benchmark_stt(audio_bytes: bytes, iterations: int = 3) -> Dict[str, Any]:
    print(f"\n[1/4] Benchmarking STT (Speech-to-Text)... ({iterations} iterations)")
    stt = get_stt_provider()
    latencies: List[float] = []
    sample_text = ""

    for i in range(iterations):
        t0 = time.perf_counter()
        sample_text = await stt.transcribe(audio_bytes)
        dt = (time.perf_counter() - t0) * 1000
        latencies.append(dt)
        print(f"  - Run {i+1}: {dt:.1f} ms | Output: \"{sample_text.strip()[:60]}...\"")

    return {
        "provider": type(stt).__name__,
        "latencies_ms": latencies,
        "sample_output": sample_text.strip(),
    }


async def benchmark_llm(prompt: str, iterations: int = 3) -> Dict[str, Any]:
    print(f"\n[2/4] Benchmarking LLM Streaming... ({iterations} iterations)")
    llm = get_llm_provider()
    ttft_list: List[float] = []
    total_durations: List[float] = []
    tps_list: List[float] = []
    sample_response = ""

    for i in range(iterations):
        t0 = time.perf_counter()
        first_token_time = None
        token_count = 0
        text_accum = []

        async with healthcare_agent.run_stream(prompt) as stream_resp:
            async for token in stream_resp.stream_text(delta=True):
                if first_token_time is None:
                    first_token_time = time.perf_counter()
                token_count += 1
                text_accum.append(token)

        t_end = time.perf_counter()
        ttft = ((first_token_time or t_end) - t0) * 1000
        total_time = (t_end - t0) * 1000
        gen_time_s = max(0.001, (t_end - (first_token_time or t0)))
        tps = token_count / gen_time_s

        ttft_list.append(ttft)
        total_durations.append(total_time)
        tps_list.append(tps)
        sample_response = "".join(text_accum).strip()

        print(
            f"  - Run {i+1}: TTFT={ttft:.1f} ms | Total={total_time:.1f} ms | Chunks={token_count} (~{tps:.1f} chunks/sec)"
        )

    return {
        "model": getattr(llm, "model", "default"),
        "ttft_ms": ttft_list,
        "total_ms": total_durations,
        "tps": tps_list,
        "sample_output": sample_response[:100] + "...",
    }


async def benchmark_tts(text_chunks: List[str], iterations: int = 3) -> Dict[str, Any]:
    print(f"\n[3/4] Benchmarking TTS (Text-to-Speech Streaming)... ({iterations} iterations)")
    tts = get_tts_provider()
    ttfa_list: List[float] = []
    total_durations: List[float] = []
    audio_bytes_list: List[int] = []

    for i in range(iterations):
        async def mock_text_stream():
            for chunk in text_chunks:
                yield chunk
                await asyncio.sleep(0.02)  # simulate slight streaming cadence

        t0 = time.perf_counter()
        first_audio_time = None
        total_bytes = 0

        async for audio_chunk in tts.generate_speech_stream(mock_text_stream()):
            if first_audio_time is None:
                first_audio_time = time.perf_counter()
            total_bytes += len(audio_chunk)

        t_end = time.perf_counter()
        ttfa = ((first_audio_time or t_end) - t0) * 1000
        total_time = (t_end - t0) * 1000

        ttfa_list.append(ttfa)
        total_durations.append(total_time)
        audio_bytes_list.append(total_bytes)

        print(
            f"  - Run {i+1}: TTFA={ttfa:.1f} ms | Total={total_time:.1f} ms | Audio Bytes={total_bytes:,}"
        )

    return {
        "provider": type(tts).__name__,
        "ttfa_ms": ttfa_list,
        "total_ms": total_durations,
        "audio_bytes": audio_bytes_list,
    }


async def benchmark_e2e_pipeline(
    audio_bytes: bytes, iterations: int = 3
) -> Dict[str, Any]:
    print(f"\n[4/4] Benchmarking End-to-End Streaming Turn (Time-to-Ear)... ({iterations} iterations)")
    stt = get_stt_provider()
    tts = get_tts_provider()
    transport = HeadlessBenchmarkTransport()

    pipeline = StreamingPipeline(
        bot_agent=healthcare_agent,
        transport=transport,
        tts=tts,
        stt=stt,
    )

    tte_list: List[float] = []
    turn_results: List[TurnResult] = []

    for i in range(iterations):
        transport.received_chunks.clear()
        transport.first_chunk_received_at = None

        t0 = time.perf_counter()
        result = await pipeline.run_audio_turn(audio=audio_bytes)
        t_first_chunk = transport.first_chunk_received_at or time.perf_counter()
        tte = (t_first_chunk - t0) * 1000

        tte_list.append(tte)
        turn_results.append(result)

        print(
            f"  - Run {i+1}: TTE (Time-to-Ear)={tte:.1f} ms | STT={result.stt_ms:.1f} ms | "
            f"LLM TTFT={result.llm_time_to_first_token_ms:.1f} ms | TTS TTFA={result.tts_time_to_first_audio_ms:.1f} ms | "
            f"Total Turn={result.total_ms:.1f} ms"
        )

    return {
        "tte_ms": tte_list,
        "results": turn_results,
    }


def print_summary_table(
    stt_res: Dict[str, Any],
    llm_res: Dict[str, Any],
    tts_res: Dict[str, Any],
    e2e_res: Dict[str, Any],
):
    print("\n" + "=" * 80)
    print("                      VOICE PIPELINE BENCHMARK SUMMARY                      ")
    print("=" * 80)
    print(f"{'Metric':<35} | {'Statistics'}")
    print("-" * 80)
    print(f"{'STT Latency (' + stt_res['provider'] + ')':<35} | {format_stats(stt_res['latencies_ms'])}")
    print(f"{'LLM TTFT (Time to First Token)':<35} | {format_stats(llm_res['ttft_ms'])}")
    print(f"{'LLM Total Duration':<35} | {format_stats(llm_res['total_ms'])}")
    print(f"{'LLM Generation Speed':<35} | {format_stats(llm_res['tps'], unit=' chunks/s')}")
    print(f"{'TTS TTFA (Time to First Audio)':<35} | {format_stats(tts_res['ttfa_ms'])}")
    print(f"{'TTS Total Synthesis Duration':<35} | {format_stats(tts_res['total_ms'])}")
    print("-" * 80)
    print(f"{'>>> End-to-End Time to Ear (TTE)':<35} | {format_stats(e2e_res['tte_ms'])}")
    total_turn_ms = [r.total_ms for r in e2e_res["results"]]
    print(f"{'>>> End-to-End Total Turn Duration':<35} | {format_stats(total_turn_ms)}")
    print("=" * 80)

    mean_tte = statistics.mean(e2e_res["tte_ms"]) if e2e_res["tte_ms"] else 0
    if mean_tte < 600:
        rating = "Excellent (Real-time conversation grade, < 600ms)"
    elif mean_tte < 1000:
        rating = "Good (Acceptable voice response, 600ms - 1000ms)"
    else:
        rating = "High Latency (> 1000ms, optimization recommended)"
    print(f"Latency Grade: {rating}\n")


async def main():
    parser = argparse.ArgumentParser(description="Voice Agent STT-LLM-TTS Benchmark")
    parser.add_argument("--iterations", type=int, default=3, help="Number of test iterations")
    parser.add_argument("--audio", type=str, default="", help="Path to input WAV audio file")
    parser.add_argument(
        "--prompt",
        type=str,
        default="I have a slight headache and mild fever for two days. What general precautions should I take?",
        help="Text prompt for LLM & TTS isolated benchmark",
    )
    args = parser.parse_args()

    cfg = load_config()
    print("=" * 80)
    print("Initializing Voice Agent Benchmark Suite")
    print(f"  Configured STT : {cfg.provider_stt}")
    print(f"  Configured LLM : {cfg.provider_llm}")
    print(f"  Configured TTS : {cfg.provider_tts}")
    print(f"  Iterations     : {args.iterations}")
    print("=" * 80)

    # Prepare audio input
    if args.audio and os.path.exists(args.audio):
        print(f"Using audio input: {args.audio}")
        with open(args.audio, "rb") as f:
            audio_bytes = f.read()
    elif os.path.exists("output.wav"):
        print("Using existing output.wav file for audio benchmarks.")
        with open("output.wav", "rb") as f:
            audio_bytes = f.read()
    else:
        print("Generating synthetic 16kHz WAV tone for audio benchmarks...")
        audio_bytes = generate_synthetic_wav(duration_s=2.0)

    # 1. Run STT Benchmark
    stt_res = await benchmark_stt(audio_bytes, iterations=args.iterations)

    # 2. Run LLM Benchmark
    llm_res = await benchmark_llm(args.prompt, iterations=args.iterations)

    # 3. Run TTS Benchmark (feed text split by punctuation)
    tts_chunks = [
        "Headaches with mild fever can occur for several reasons, ",
        "such as viral infections, dehydration, or stress. ",
        "Make sure to drink plenty of fluids, get adequate rest, and monitor your temperature.",
    ]
    tts_res = await benchmark_tts(tts_chunks, iterations=args.iterations)

    # 4. Run Full E2E Pipeline Benchmark
    e2e_res = await benchmark_e2e_pipeline(audio_bytes, iterations=args.iterations)

    # Summary
    print_summary_table(stt_res, llm_res, tts_res, e2e_res)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBenchmark cancelled by user.")
    except Exception as e:
        print(f"\n[ERROR] Benchmark failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
