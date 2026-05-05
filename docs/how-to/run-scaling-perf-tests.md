# Run Scaling & Performance Tests

Use [`benchmarking_tools/scaling-perf/`](../../benchmarking_tools/scaling-perf/) to run latency and scaling tests against a running voice-agent server.

`benchmark.py` drives a single client. `simulate_concurrency.sh` orchestrates multiple parallel clients and rolls up suite-level results.

## Setup

1. Add **16 kHz, mono, 16-bit PCM** WAV files to `benchmarking_tools/scaling-perf/dataset/`.
2. From the repository root, install benchmark dependencies once:

    ```bash
    uv sync --group benchmark
    ```

3. Start the voice-agent server. From the repository root:

    ```bash
    uv run python src/server.py --no-tls
    ```

    Or run it under Docker Compose with any of the cloud profiles described in [Getting Started](../01-getting-started.md).

## Run

From `benchmarking_tools/scaling-perf/`:

Single client (smoke test):

```bash
uv run python3 benchmark.py
```

Concurrent run (N parallel clients, single concurrency level):

```bash
./simulate_concurrency.sh --clients 4
```

Scaling sweep (one run per concurrency level, with cooldown between levels):

```bash
./simulate_concurrency.sh --clients "1 2 4 8 16"
```

Useful flags (passed through to `simulate_concurrency.sh`):

```bash
./simulate_concurrency.sh --host localhost --port 7860 --clients "1 4"
./simulate_concurrency.sh --clients "1 4" --test-duration 30 --cooldown 5
./simulate_concurrency.sh --clients "4" --no-save-audio
```

## Outputs

- Single-level run: `results_<timestamp>/` with `benchmark_summary.json`, `results.txt`, `results.tsv`, `results.json`, plus per-client logs and audio dumps.
- Sweep: `perf_suite_<timestamp>/` with suite-level `results.txt`, `results.tsv`, `results.json`, and one `run_<N>_clients/` directory per concurrency level.

See the perf README for the full output layout and per-flag reference:

- [`benchmarking_tools/scaling-perf/README.md`](../../benchmarking_tools/scaling-perf/README.md)
