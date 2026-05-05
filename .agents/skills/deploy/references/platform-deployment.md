# Platform Deployment Reference

Use from repository root after `deploy` selects a local profile.

## Common Setup

```bash
test -f .env || cp .env.example .env
export NGC_API_KEY="$NVIDIA_API_KEY"
echo "$NGC_API_KEY" | docker login nvcr.io -u '$oauthtoken' --password-stdin
```

Required `.env` keys:
- All modes: `NVIDIA_API_KEY`
- `dgxspark` / `jetson`: `HF_TOKEN`
- Local modes: `DEPLOYMENT_PLATFORM=workstation|dgxspark|jetson`

## Workstation

Services: `generic-example-workstation` or `agentic-airline-example-workstation`, `nvidia-llm`, `asr-service`, `tts-service`.
Requires GPUs `0` and `1`: ASR/TTS use GPU `0`; `nvidia-llm` uses GPU `1`.

```bash
nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader
docker compose --profile generic-workstation up -d
# or: docker compose --profile agentic-airline-workstation up -d
```

## DGX Spark

Services: `generic-example-dgxspark`, `nvidia-llm-vllm`, `asr-service`, `tts-service`.

```bash
free -h
docker compose --profile generic-dgxspark up -d
```

Optional `.env`: `TTS_DOCKER_IMAGE=<image>` for DGX Spark / staging Magpie.

## Jetson

Services: `generic-example-jetson`, `nvidia-llm-vllm`, `nemotron-speech`.

One-time Riva model setup, from the repo parent:

```bash
cd ..
ngc registry resource download-version nvidia/riva/riva_quickstart_arm64:2.24.0
cd riva_quickstart_arm64_v2.24.0 && bash riva_init.sh && cd ../nemotron-voice-agent
```

Deploy:

```bash
sudo bash scripts/start-mps.sh
docker compose --profile generic-jetson up -d
```

Thor tuning `.env`:

```env
VLLM_MPS_THREAD_PCT=50
RIVA_MPS_THREAD_PCT=50
VLLM_CPUSET=0-3
RIVA_CPUSET=4-7
PIPECAT_CPUSET=8-11
```

## TURN

Add `--profile turn` when clients connect from outside the host network.

```bash
docker compose --profile generic --profile turn up -d
docker compose --profile generic-workstation --profile turn up -d
```

## Verify / Stop

```bash
docker compose ps
docker compose logs --tail 200 <example-service>
docker compose down
```
