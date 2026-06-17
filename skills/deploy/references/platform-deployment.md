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
- Any recipe ending in `/dgx-spark` or `/jetson-thor`, plus `omni-assistant/workstation` and `omni-assistant-subagents/workstation` (local Omni vLLM downloads the model from HF on first run): `HF_TOKEN`

## Workstation

Recipes: `generic-assistant/workstation`, `multilingual-assistant/workstation`, `omni-assistant/workstation`, `thinker-talker/workstation`.

Services depend on the recipe:
- `generic-assistant/workstation`: `generic-assistant`, `nvidia-llm`, `nemotron-asr-streaming-english`, `tts-service`
- `multilingual-assistant/workstation`: `multilingual-assistant`, `nvidia-llm`, `nemotron-asr-streaming-multilingual`, `tts-service`
- `omni-assistant/workstation`: `omni-assistant`, `nvidia-llm-vllm-omni`, `tts-service`
- `thinker-talker/workstation`: `thinker-talker`, `booking-server`, `nvidia-llm`, `nemotron-asr-streaming-english`, `tts-service`

Requires enough GPU VRAM for the selected local NIM services. Single-GPU hosts are valid when capacity is sufficient. Multi-GPU hosts may split ASR/TTS and LLM across devices.

```bash
nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader
docker compose --profile generic-assistant/workstation up -d
# or: docker compose --profile multilingual-assistant/workstation up -d
# or: docker compose --profile omni-assistant/workstation up -d
# or: docker compose --profile thinker-talker/workstation up -d
```

## DGX Spark

Recipes: `generic-assistant/dgx-spark`, `multilingual-assistant/dgx-spark`, `omni-assistant/dgx-spark`.

Services depend on the recipe:
- `generic-assistant/dgx-spark`: `generic-assistant`, `nvidia-llm-vllm`, `nemotron-asr-streaming-english`, `tts-service`
- `multilingual-assistant/dgx-spark`: `multilingual-assistant`, `nvidia-llm-vllm`, `nemotron-asr-streaming-multilingual`, `tts-service`
- `omni-assistant/dgx-spark`: `omni-assistant`, `nvidia-llm-vllm-omni`, `tts-service`

```bash
free -h
docker compose --profile generic-assistant/dgx-spark up -d
# docker compose --profile multilingual-assistant/dgx-spark up -d
# docker compose --profile omni-assistant/dgx-spark up -d
```

## Jetson Thor

Recipes: `generic-assistant/jetson-thor` only. Omni and Multilingual examples are not supported on Jetson today.

Services: `generic-assistant`, `nvidia-llm-vllm`, `nemotron-speech`.

One-time Riva model setup, from the repo parent. Uses the Riva Speech Skills v2.26.0 L4T quickstart (NGC `nvidia/riva` org, 2.26.0 models by default):

```bash
cd ..
ngc registry resource download-version "nvidia/riva/riva_quickstart_arm64:2.26.0"
cd riva_quickstart_arm64_v2.26.0   # resource extracts into this dir
bash riva_init.sh && cd ../nemotron-voice-agent
```

Deploy:

```bash
sudo bash scripts/start-mps.sh
docker compose --profile generic-assistant/jetson-thor up -d
```

Thor tuning `.env`:

```env
VLLM_MPS_THREAD_PCT=50
RIVA_MPS_THREAD_PCT=50
VLLM_CPUSET=0-3
RIVA_CPUSET=4-7
PIPECAT_CPUSET=8-11
```

If a service fails to start on low memory (e.g. `nvidia-llm-vllm` logs `Engine core initialization failed`), reclaim cached memory and retry:

```bash
free -h
sudo sync && sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'
docker compose --profile generic-assistant/jetson-thor up -d
```

## TURN

Add `--profile turn` when clients connect from outside the host network.

```bash
docker compose --profile generic-assistant --profile turn up -d
docker compose --profile generic-assistant/workstation --profile turn up -d
```

## Verify / Stop

```bash
docker compose ps
docker compose logs --tail 200 <service-name>
docker compose down
```
