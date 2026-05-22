# Platform Deployment Reference

Use from repository root after `deploy` selects a hardware profile.

## Common Setup

```bash
test -f .env || cp .env.example .env
export NGC_API_KEY="$NVIDIA_API_KEY"
echo "$NGC_API_KEY" | docker login nvcr.io -u '$oauthtoken' --password-stdin
```

Required `.env` keys:
- All modes: `NVIDIA_API_KEY`
- `dgxspark` / `jetson`: `HF_TOKEN`

## Workstation

Services: example app variant (`cascaded-generic` / `cascaded-agentic-airline`), `nvidia-llm`, `asr-service`, `tts-service` (and `booking-server` when running the agentic-airline example).
Requires enough GPU VRAM for the selected local NIM services. Single-GPU hosts are valid when capacity is sufficient; multi-GPU hosts may split ASR/TTS and LLM across devices.

```bash
nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader
docker compose --profile cascaded/generic --profile workstation up -d
# or: docker compose --profile cascaded/agentic-airline --profile workstation up -d
```

## DGX Spark

Services: `cascaded-generic`, `nvidia-llm-vllm`, `asr-service`, `tts-service`.

```bash
free -h
docker compose --profile cascaded/generic --profile dgxspark up -d
```

Optional `.env`: `TTS_DOCKER_IMAGE=<image>` for DGX Spark / staging Magpie.

## Jetson

Services: `cascaded-generic`, `nvidia-llm-vllm`, `nemotron-speech`.

One-time Riva model setup, from the repo parent:

```bash
cd ..
ngc registry resource download-version nvidia/riva/riva_quickstart_arm64:2.24.0
cd riva_quickstart_arm64_v2.24.0 && bash riva_init.sh && cd ../nemotron-voice-agent
```

Deploy:

```bash
sudo bash scripts/start-mps.sh
docker compose --profile cascaded/generic --profile jetson up -d
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
docker compose --profile cascaded/generic --profile turn up -d
docker compose --profile cascaded/generic --profile workstation --profile turn up -d
```

## Verify / Stop

```bash
docker compose ps
docker compose logs --tail 200 <service-name>
docker compose down
```
