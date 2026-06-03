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
- Any recipe ending in `/dgx-spark` or `/jetson-thor`: `HF_TOKEN`

## Workstation

Recipes: `cascaded-generic/workstation`, `cascaded-multilingual/workstation`, `cascaded-omni/workstation`, `cascaded-thinker-talker/workstation`.

Services depend on the recipe:
- `cascaded-generic/workstation`: `cascaded-generic`, `nvidia-llm`, `asr-service`, `tts-service`
- `cascaded-multilingual/workstation`: `cascaded-multilingual`, `nvidia-llm`, `parakeet-rnnt-asr`, `tts-service`
- `cascaded-omni/workstation`: `cascaded-omni`, `nvidia-llm-vllm-omni`, `tts-service`
- `cascaded-thinker-talker/workstation`: `cascaded-thinker-talker`, `booking-server`, `nvidia-llm`, `asr-service`, `tts-service`

Requires enough GPU VRAM for the selected local NIM services. Single-GPU hosts are valid when capacity is sufficient. Multi-GPU hosts may split ASR/TTS and LLM across devices.

```bash
nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader
docker compose --profile cascaded-generic/workstation up -d
# or: docker compose --profile cascaded-multilingual/workstation up -d
# or: docker compose --profile cascaded-omni/workstation up -d
# or: docker compose --profile cascaded-thinker-talker/workstation up -d
```

## DGX Spark

Recipes: `cascaded-generic/dgx-spark`, `cascaded-multilingual/dgx-spark`, `cascaded-omni/dgx-spark`.

Services depend on the recipe:
- `cascaded-generic/dgx-spark`: `cascaded-generic`, `nvidia-llm-vllm`, `asr-service`, `tts-service`
- `cascaded-multilingual/dgx-spark`: `cascaded-multilingual`, `nvidia-llm-vllm`, `parakeet-rnnt-asr`, `tts-service`
- `cascaded-omni/dgx-spark`: `cascaded-omni`, `nvidia-llm-vllm-omni`, `tts-service`

```bash
free -h
docker compose --profile cascaded-generic/dgx-spark up -d
# docker compose --profile cascaded-multilingual/dgx-spark up -d
# docker compose --profile cascaded-omni/dgx-spark up -d
```

## Jetson Thor

Recipes: `cascaded-generic/jetson-thor` only. Omni and Multilingual examples are not supported on Jetson today.

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
docker compose --profile cascaded-generic/jetson-thor up -d
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
docker compose --profile cascaded-generic --profile turn up -d
docker compose --profile cascaded-generic/workstation --profile turn up -d
```

## Verify / Stop

```bash
docker compose ps
docker compose logs --tail 200 <service-name>
docker compose down
```
