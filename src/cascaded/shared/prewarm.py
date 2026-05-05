# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Service pre-warming to avoid blocking the event loop during first connection."""

import os

from loguru import logger
from pipecat.services.nvidia.tts import NvidiaTTSService, NvidiaTTSSettings

import config_store
from utils import is_nvcf


def _create_tts_service(server: str, voice_id: str) -> NvidiaTTSService:
    return NvidiaTTSService(
        api_key=os.getenv("NVIDIA_API_KEY"),
        server=server,
        settings=NvidiaTTSSettings(voice=voice_id),
        use_ssl=is_nvcf(server),
    )


def _parse_tts_config(raw_config, model_prefix: str) -> dict:
    """Parse the TTS synthesis config into a frontend-friendly structure.

    Voice IDs are returned in full form (e.g. "Magpie-Multilingual.EN-US.Aria")
    so the frontend can use them as-is without any prefix manipulation.
    """
    if not raw_config or not raw_config.model_config:
        return {"languages": [], "voices": []}

    params = dict(raw_config.model_config[0].parameters)
    languages = [lang_code.strip() for lang_code in params.get("language_code", "").split(",") if lang_code.strip()]
    subvoices_raw = params.get("subvoices", "")

    voices: list[dict] = []
    seen: set[str] = set()
    for entry in subvoices_raw.split(","):
        entry = entry.strip()
        if ":" not in entry or "." not in entry:
            continue
        short_id = entry.split(":")[0]
        parts = short_id.split(".")
        if len(parts) < 2:
            continue
        if short_id in seen:
            continue
        seen.add(short_id)
        full_id = f"{model_prefix}.{short_id}" if model_prefix else short_id
        lang = parts[0]
        name = ".".join(parts[1:])
        voices.append({"id": full_id, "name": name, "language": lang})

    return {
        "languages": languages,
        "voices": sorted(voices, key=lambda v: (v["language"], v["name"])),
    }


def _cache_key(server: str) -> str:
    return f"tts:{server}"


def prewarm_tts(server: str, voice_id: str) -> dict:
    """Pre-warm a TTS server and cache its voice/language config.

    Returns the TTS config dict (languages, voices, defaultVoiceId).
    Results are cached per server in config_store.
    """
    cached = config_store.get(_cache_key(server))
    if cached:
        logger.debug(f"TTS config for {server} already cached")
        return cached

    logger.info(f"Pre-warming TTS on {server} (this may take 10-20s on first run)...")
    try:
        svc = _create_tts_service(server, voice_id)
        svc._initialize_client()
        raw_config = svc._create_synthesis_config()

        model_prefix = voice_id.split(".")[0] if "." in voice_id else ""
        tts_config = _parse_tts_config(raw_config, model_prefix)
        tts_config["defaultVoiceId"] = voice_id
        tts_config["server"] = server

        config_store.set(_cache_key(server), tts_config)
        config_store.set("tts", tts_config)

        n_langs = len(tts_config["languages"])
        n_voices = len(tts_config["voices"])
        logger.info(f"TTS pre-warmed ({server}) — {n_langs} languages, {n_voices} voices")
        return tts_config
    except Exception as e:
        logger.warning(f"TTS pre-warm failed for {server}: {e}")
        return {
            "languages": [],
            "voices": [],
            "defaultVoiceId": voice_id,
            "server": server,
            "error": str(e),
        }


def warmup_tts_synthesis(server: str, voice_id: str) -> bool:
    """Run a tiny synthesis request to verify the selected TTS is responsive."""
    logger.info(f"Warming up TTS synthesis on {server}...")
    try:
        svc = _create_tts_service(server, voice_id)
        svc._initialize_client()

        responses = svc._service.synthesize_online(
            "Hello.",
            svc._settings.voice,
            svc._settings.language,
            sample_rate_hz=16000,
            zero_shot_audio_prompt_file=None,
            zero_shot_quality=svc._settings.quality,
            custom_dictionary={},
        )
        for _ in responses:
            break

        logger.info(f"TTS synthesis warm-up completed ({server})")
        return True
    except Exception as e:
        logger.warning(f"TTS synthesis warm-up failed ({server}): {e}")
        return False
