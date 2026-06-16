# Evaluation and Performance

This guide provides reference benchmarks for the Nemotron Voice Agent covering **accuracy**, **full-duplex behavior**, and **latency/throughput**.

---

## Accuracy: BigBench Audio Benchmarking

BigBench Audio evaluates **answer correctness** on the [ArtificialAnalysis/big_bench_audio](https://huggingface.co/datasets/ArtificialAnalysis/big_bench_audio) dataset.

### Reference Results

The following table shows accuracy (%) on Big Bench Audio for the LLM standalone (text-only) vs the LLM running in the voice agent pipeline:

| Model / API | Reasoning Mode | Text Only Standalone LLM (%) | LLM In Voice Agent Pipeline (%) |
| --- | --- | --- | --- |
| Nemotron 49B (`nvidia/llama-3.3-nemotron-super-49b-v1.5`) | Reasoning ON | 91.90 | 81.30 |
| Nemotron 49B | Reasoning OFF | 82.70 | 60.30 |
| Nemotron 30B (`nvidia/nemotron-3-nano`) | Reasoning ON, Budget 500 | 78.76 | 75.60 |
| Nemotron 30B | Reasoning OFF | 56.50 | 50.40 |

### How to Reproduce

[`benchmarking_tools/AA-BigBenchAudio-Eval/`](../benchmarking_tools/AA-BigBenchAudio-Eval/README.md) drives the full pipeline (download → preprocess → inference → Riva transcription → LLM-judge scoring). Prerequisites: a running voice agent (see [Getting Started](01-getting-started.md)), `ffmpeg`, a Riva ASR endpoint (default `localhost:50051`), and judge-LLM credentials (`EVAL_API_URL`, `EVAL_API_KEY`).

From the **repo root**, install benchmark dependencies once:

```bash
uv sync --group benchmark
```

Then, from `benchmarking_tools/AA-BigBenchAudio-Eval/`, run the speech pipeline:

```bash
uv run python download_dataset.py --input_dir ./datasets/bigbench_audio --split train
uv run python speech-inference.py --input_dir ./datasets/bigbench_audio --preprocess
uv run python speech-inference.py --input_dir ./datasets/bigbench_audio --inference \
  --server-url http://127.0.0.1:7860
uv run python transcribe.py --input_dir ./datasets/bigbench_audio
EVAL_API_URL=https://.../invoke EVAL_API_KEY=your_key \
  uv run python eval.py --input_dir ./datasets/bigbench_audio
uv run python analyze_results.py --input_dir ./datasets/bigbench_audio
```

See the [eval README](../benchmarking_tools/AA-BigBenchAudio-Eval/README.md) for the text-only pipeline, HTTPS / self-signed-cert flags, and per-script options.

---

## Full-Duplex Behavior

[Full-Duplex-Bench](https://github.com/DanielLin94144/Full-Duplex-Bench) (v1, v1.5) probes turn-taking behavior under interruption — when the agent yields to a user barge-in, when it keeps talking through background noise, and how quickly the bot reply lands after the user finishes speaking. The repo's [`benchmarking_tools/Full-Duplex-Bench-Eval/`](../benchmarking_tools/Full-Duplex-Bench-Eval/README.md) tool acts as the inference client: it streams each dataset sample to the running voice agent over WebSocket and writes the bot's reply audio back into the per-sample folders. Scoring (TOR, P_resp, P_inter, …) is then computed by the upstream Full-Duplex-Bench tooling against those output WAVs.

### How to Reproduce

Install benchmark dependencies once and start the agent from the **repo root**:

```bash
uv sync --group benchmark
PIPELINE_TLS=false uv run python src/server.py
```

Then, from `benchmarking_tools/Full-Duplex-Bench-Eval/`, point the client at the running server:

```bash
uv run python inference.py \
  --input_dir /path/to/full-duplex-bench/samples \
  --server-url http://127.0.0.1:7860
```

This populates `output.wav` (and `clean_output.wav` when a `clean_input.wav` is present) in each numeric sample folder. Feed those into Full-Duplex-Bench's evaluation scripts to compute the metrics. See the [eval README](../benchmarking_tools/Full-Duplex-Bench-Eval/README.md) for HTTPS / self-signed-cert flags and `--retry_samples` for re-running specific IDs.

---

## Latency and Scalability

### Reference Results

**The Nemotron Voice Agent** performance benchmark shows **sub-second End-to-End (E2E) latency**. The setup uses **4x H100 GPUs** (one for Parakeet CTC 1.1B ASR, one for Magpie TTS, and two for Nemotron-3-Nano LLM). All latencies are in seconds.

> **Note:** This benchmark uses a 4-GPU setup to measure scalability. The [minimum deployment requirement](01-getting-started.md#gpu-requirements) is cloud-only (no local GPUs) or 1 GPU with roughly 80 GB available VRAM for a local profile.

| Parallel Streams | E2E Latency | ASR Latency | TTS TTFB | LLM TTFT | LLM First-Sentence Latency |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.79 | 0.04 | 0.078 | 0.126 | 0.138 |
| 4 | 0.76 | 0.046 | 0.066 | 0.061 | 0.181 |
| 8 | 0.77 | 0.052 | 0.066 | 0.062 | 0.136 |
| 16 | 0.91 | 0.057 | 0.068 | 0.105 | 0.208 |
| 32 | 0.80 | 0.061 | 0.080 | 0.073 | 0.294 |
| 64 | 1.00 | 0.067 | 0.110 | 0.156 | 0.386 |

*E2E: End-to-End · TTFB: Time to First Byte · TTFT: Time to First Token*

For production targets and tuning guidance, refer to [Best Practices](04-best-practices.md) and [Tune Pipeline Performance](how-to/tune-pipeline-performance.md).
