# Platform Deployment Reference

Use from repository root after `deploy` picks a recipe profile.

## Common Setup

```bash
test -f .env || cp .env.example .env
export NGC_API_KEY="$NVIDIA_API_KEY"
echo "$NGC_API_KEY" | docker login nvcr.io -u '$oauthtoken' --password-stdin
```

Required `.env` keys:
- All recipes: `NVIDIA_API_KEY`
- Any recipe ending in `/dgxspark` or `/jetson`: `HF_TOKEN`

## Workstation

Recipes: `cascaded/generic/workstation`, `cascaded/agentic-airline/workstation`, `cascaded/omni-assistant/workstation`.

Services depend on the example:
- `cascaded/generic/workstation`: `cascaded-generic`, `nvidia-llm`, `asr-service`, `tts-service`
- `cascaded/agentic-airline/workstation`: `cascaded-agentic-airline`, `nvidia-llm`, `asr-service`, `tts-service`, `booking-server`
- `cascaded/omni-assistant/workstation`: `cascaded-omni-assistant`, `nvidia-llm-vllm-omni`, `tts-service`

Requires enough GPU VRAM for the selected local NIM services. Single-GPU hosts are valid when capacity is sufficient. Multi-GPU hosts may split ASR/TTS and LLM across devices.

```bash
nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader
docker compose --profile cascaded/generic/workstation up -d
# or: docker compose --profile cascaded/agentic-airline/workstation up -d
# or: docker compose --profile cascaded/omni-assistant/workstation up -d
```

## DGX Spark

Recipes: `cascaded/generic/dgxspark`, `cascaded/omni-assistant/dgxspark`, `cascaded/omni-assistant-subagents/dgxspark`.

Services depend on the example:
- `cascaded/generic/dgxspark`: `cascaded-generic`, `nvidia-llm-vllm`, `asr-service`, `tts-service`
- `cascaded/omni-assistant/dgxspark`: `cascaded-omni-assistant`, `nvidia-llm-vllm-omni`, `tts-service`
- `cascaded/omni-assistant-subagents/dgxspark`: `cascaded-omni-assistant-subagents`, `nvidia-llm-vllm-omni`, `tts-service`

```bash
free -h
docker compose --profile cascaded/generic/dgxspark up -d
docker compose --profile cascaded/omni-assistant/dgxspark up -d
docker compose --profile cascaded/omni-assistant-subagents/dgxspark up -d
```

Optional `.env`: `TTS_DOCKER_IMAGE=<image>` for DGX Spark / staging Magpie.

## Jetson

Recipes: `cascaded/generic/jetson` only. Omni examples are not supported on Jetson today (the 30B Omni NVFP4 model does not fit on Orin-class hardware).

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
docker compose --profile cascaded/generic/jetson up -d
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
docker compose --profile cascaded/generic/workstation --profile turn up -d
```

## Verify / Stop

```bash
docker compose ps
docker compose logs --tail 200 <service-name>
docker compose down
```
