# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Shared utility functions."""

import ipaddress
import json
import os
from pathlib import Path

import yaml
from loguru import logger

from timeutils import TOOL_HANDLERS as TOOL_HANDLERS  # noqa: F401

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPT_FILE = Path(os.getenv("PROMPT_FILE_PATH", str(PROJECT_ROOT / "prompt.yaml")))
PROMPT_SELECTOR = os.getenv("PROMPT_SELECTOR", "flowershop")


def _services_cloud_path() -> Path:
    return Path(os.getenv("SERVICES_CLOUD_PATH", str(PROJECT_ROOT / "services.cloud.yaml")))


def _services_local_path() -> Path:
    return Path(os.getenv("SERVICES_LOCAL_PATH", str(PROJECT_ROOT / "services.local.yaml")))


_LOCAL_DEPLOY_PLATFORMS = frozenset({"jetson", "dgxspark", "workstation"})
_SERVICE_CATEGORIES = ("llm", "vlm", "tts", "asr", "s2s")
_DEFAULT_SERVICE_ENV_VARS = {
    "llm": "DEFAULT_LLM",
    "tts": "DEFAULT_TTS",
    "asr": "DEFAULT_ASR",
}
_DEFAULT_ASR_DOCKER_IMAGE = "nvcr.io/nim/nvidia/nemotron-asr-streaming:1.0.0"
_ASR_IMAGE_TO_LOCAL_KEY = {
    "nemotron-asr-streaming": "nemotron-speech",
    "parakeet-1-1b-ctc-en-us": "parakeet-ctc",
    "parakeet-1-1b-rnnt-multilingual": "parakeet-rnnt",
}

_SLOT_CONFIG_KEYS: dict[str, frozenset[str]] = {
    "llm": frozenset({"llm_id", "model_id", "base_url", "system_prompt", "extra_params"}),
    "asr": frozenset({"asr_id", "asr_server", "asr_model", "asr_function_id"}),
    "tts": frozenset({"tts_id", "tts_server", "tts_voice_id", "tts_function_id"}),
    "s2s": frozenset({"s2s_id", "s2s_server"}),
}
_SLOT_AGNOSTIC_KEYS: frozenset[str] = frozenset({"pipeline_mode", "prompt_key", "prompt_content"})
_active_slots: frozenset[str] | None = None


def set_active_slots(slots: list[str] | tuple[str, ...] | None) -> None:
    """Declare which example slots are active; ``None`` disables filtering."""
    global _active_slots
    _active_slots = frozenset(slots) if slots else None


def resolve_prompt(prompt_content: str = "", prompt_key: str = "") -> str:
    """Resolve prompt content from client body or prompt.yaml.

    Priority: client-provided content > prompt_key lookup > PROMPT_SELECTOR default.
    """
    if prompt_content:
        logger.info(f"Using client-provided prompt (key={prompt_key or 'custom'})")
        return prompt_content

    if not prompt_key:
        prompt_key = PROMPT_SELECTOR
    try:
        content = _load_yaml_entry(PROMPT_FILE, prompt_key)["content"]
    except KeyError:
        logger.warning(f"Prompt '{prompt_key}' not found, falling back to '{PROMPT_SELECTOR}'")
        content = _load_yaml_entry(PROMPT_FILE, PROMPT_SELECTOR)["content"]
        prompt_key = PROMPT_SELECTOR
    logger.info(f"Loaded prompt from prompt.yaml [{prompt_key}]")
    return content


def load_yaml_file(filepath: Path) -> dict:
    """Load and return the contents of a YAML file as a dict.

    Returns an empty dict if the file doesn't exist or is empty.
    """
    if not filepath.is_file():
        return {}
    data = yaml.safe_load(filepath.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _load_yaml_entry(filepath: Path, key: str) -> dict:
    """Load a top-level entry from a YAML file.

    Args:
        filepath: Path to the YAML file.
        key: Top-level key to look up.

    Returns:
        The dict value for the given key.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        KeyError: If the key is not found in the file.
    """
    if not filepath.exists():
        raise FileNotFoundError(f"YAML file not found: {filepath}")
    data = yaml.safe_load(filepath.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or key not in data:
        available = list(data.keys()) if isinstance(data, dict) else []
        raise KeyError(f"Key '{key}' not found in {filepath}. Available: {available}")
    return data[key]


def is_nvcf(server: str) -> bool:
    """Auto-detect if a gRPC server is NVIDIA Cloud Functions (requires SSL)."""
    return "nvcf.nvidia.com" in server


def _normalize_services_catalog(data: object) -> dict:
    """Normalize a services catalog to the expected category layout."""
    src = data if isinstance(data, dict) else {}
    return {cat: dict(section) if isinstance(section := src.get(cat), dict) else {} for cat in _SERVICE_CATEGORIES}


def get_deployment_platform() -> str:
    """Return the normalized deployment platform, or ``""`` for remote/NVCF."""
    return os.getenv("DEPLOYMENT_PLATFORM", "").strip().lower()


def _is_container_runtime() -> bool:
    """Return ``True`` when running under Compose (``APP_RUNTIME=container``)."""
    return os.getenv("APP_RUNTIME", "").strip().lower() == "container"


def _rewrite_endpoint_for_host_runtime(field: str, value: str) -> str:
    """Convert Compose-oriented built-ins to host-accessible endpoints."""
    if field == "base_url":
        if value in {"http://nvidia-llm:8000/v1", "http://nvidia-llm-vllm:8000/v1"}:
            return "http://localhost:18000/v1"
        return value

    if field == "server":
        return (
            value.replace("tts-service:50051", "localhost:50151")
            .replace("asr-service:50052", "localhost:50152")
            .replace("nemotron-speech:50051", "localhost:50051")
            .replace("host.docker.internal", "localhost")
        )

    return value


def _rewrite_local_runtime_endpoints(catalog: dict) -> dict:
    """Rewrite local built-ins only when the backend runs outside Docker."""
    if _is_container_runtime():
        return catalog

    def _rewrite_entry(entry: dict) -> dict:
        out = dict(entry)
        for field in ("base_url", "server"):
            value = out.get(field)
            if isinstance(value, str):
                out[field] = _rewrite_endpoint_for_host_runtime(field, value)
        return out

    return {
        category: (
            {key: _rewrite_entry(entry) if isinstance(entry, dict) else entry for key, entry in section.items()}
            if isinstance(section, dict)
            else section
        )
        for category, section in catalog.items()
    }


def _resolve_section_default_key(section: dict, category: str, explicit_key: str = "") -> str:
    """Pick the effective default key for a category: explicit > ``DEFAULT_*`` env > ``""``."""
    explicit_key = explicit_key.strip()
    if explicit_key and explicit_key in section:
        return explicit_key
    env_var = _DEFAULT_SERVICE_ENV_VARS.get(category, "")
    configured_key = os.getenv(env_var, "").strip() if env_var else ""
    if configured_key and configured_key in section:
        return configured_key
    return ""


def _configured_local_asr_key() -> str:
    image = (os.getenv("ASR_DOCKER_IMAGE", "").strip() or _DEFAULT_ASR_DOCKER_IMAGE).lower()
    for image_name, catalog_key in _ASR_IMAGE_TO_LOCAL_KEY.items():
        if image_name in image:
            return catalog_key
    return ""


def _filter_local_asr_for_deployed_image(catalog: dict) -> dict:
    asr_section = catalog.get("asr", {})
    if not isinstance(asr_section, dict) or len(asr_section) <= 1:
        return catalog
    configured_key = _configured_local_asr_key()
    if configured_key not in asr_section:
        logger.warning("ASR_DOCKER_IMAGE does not match a local ASR catalog entry; showing all local ASR entries")
        return catalog
    return {**catalog, "asr": {configured_key: asr_section[configured_key]}}


def _load_cloud_services_catalog() -> dict:
    """Load cloud service entries."""
    return _normalize_services_catalog(load_yaml_file(_services_cloud_path()))


def _load_local_services_catalog(platform: str) -> dict:
    """Load the local catalog for a specific platform.

    Entries must be nested under a platform key (``workstation`` / ``dgxspark``
    / ``jetson``), each containing ``llm`` / ``asr`` / ``tts`` / ``s2s`` maps.
    """
    platform_data = load_yaml_file(_services_local_path()).get(platform)
    if not isinstance(platform_data, dict):
        logger.warning(f"services.local.yaml has no section for platform={platform!r}")
        return _normalize_services_catalog({})
    return _rewrite_local_runtime_endpoints(_normalize_services_catalog(platform_data))


def _load_effective_services_catalog() -> dict:
    """Load the active service catalog for the configured deployment mode."""
    platform = get_deployment_platform()
    if platform in _LOCAL_DEPLOY_PLATFORMS:
        return _load_local_services_catalog(platform)
    return _load_cloud_services_catalog()


# Whitelist of keys accepted on session-config / offer bodies. Anything else
# sent by the client is dropped before the pipeline sees it.
SESSION_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "pipeline_mode",
        "llm_id",
        "asr_id",
        "tts_id",
        "s2s_id",
        "model_id",
        "base_url",
        "system_prompt",
        "extra_params",
        "prompt_key",
        "prompt_content",
        "s2s_server",
        "asr_server",
        "asr_model",
        "asr_function_id",
        "tts_server",
        "tts_voice_id",
        "tts_function_id",
    }
)

# For each category, map YAML field → session-body field. YAML is the source of
# truth for built-in selections. `tts_voice_id` is intentionally absent — voice
# is a user-driven runtime choice.
_CATALOG_HYDRATION: tuple[tuple[str, str, dict[str, str]], ...] = (
    (
        "llm_id",
        "llm",
        {
            "model_id": "model_id",
            "base_url": "base_url",
            "system_prompt": "system_prompt",
            "extra_params": "extra_params",
        },
    ),
    (
        "asr_id",
        "asr",
        {
            "server": "asr_server",
            "model": "asr_model",
            "function_id": "asr_function_id",
        },
    ),
    (
        "tts_id",
        "tts",
        {
            "server": "tts_server",
            "function_id": "tts_function_id",
        },
    ),
    (
        "s2s_id",
        "s2s",
        {
            "server": "s2s_server",
        },
    ),
)


def hydrate_config_from_catalog(config: dict) -> None:
    """Overwrite detail fields in ``config`` from YAML for built-in selections.

    Mutates ``config`` in place. Custom (user-authored) entries are left alone so
    the client-provided details continue to drive the pipeline.
    """
    for id_field, category, field_map in _CATALOG_HYDRATION:
        entry = _load_catalog_entry_by_id(category, config.get(id_field, ""))
        if not entry:
            continue
        for yaml_field, body_field in field_map.items():
            value = entry.get(yaml_field, "")
            if value in ("", None):
                config.pop(body_field, None)
            elif isinstance(value, (dict, list)):
                config[body_field] = json.dumps(value)
            else:
                config[body_field] = value if isinstance(value, str) else str(value)


def filter_session_config(data: dict) -> dict:
    """Return a sanitized session config ready for the pipeline.

    Keeps only keys in ``SESSION_CONFIG_KEYS`` and hydrates built-in catalog
    selections from YAML (see :func:`hydrate_config_from_catalog`).
    """
    filtered = {k: v for k, v in data.items() if k in SESSION_CONFIG_KEYS and v not in ("", None)}
    if _active_slots is not None:
        allowed: set[str] = set(_SLOT_AGNOSTIC_KEYS)
        for slot in _active_slots:
            allowed |= _SLOT_CONFIG_KEYS.get(slot, frozenset())
        filtered = {k: v for k, v in filtered.items() if k in allowed}
    hydrate_config_from_catalog(filtered)
    return filtered


def _load_catalog_entry_by_id(category: str, entry_id: str) -> dict:
    """Look up a built-in catalog entry by category and API id (``<source>:<key>``).

    Returns the raw YAML entry, or ``{}`` if the id is empty, malformed, points
    at a user-authored service (``custom-*``), or is not present in the active
    catalog for the given category. Keeps ``services.*.yaml`` as the single
    source of truth for built-in services.
    """
    if not entry_id or entry_id.startswith("custom-") or ":" not in entry_id:
        return {}
    source, key = entry_id.split(":", 1)
    if not key or category not in _SERVICE_CATEGORIES:
        return {}
    if source == "cloud-nim":
        catalog = _load_cloud_services_catalog()
    elif source == "self-hosted":
        platform = get_deployment_platform()
        if platform not in _LOCAL_DEPLOY_PLATFORMS:
            return {}
        catalog = _load_local_services_catalog(platform)
    else:
        return {}
    entry = catalog.get(category, {}).get(key)
    return dict(entry) if isinstance(entry, dict) else {}


def load_service_entry(category: str, key: str) -> dict:
    """Load a catalog entry by category and key from the effective catalog.

    Preference order: explicit key, deploy-time ``DEFAULT_*`` override, first
    entry in the category.
    """
    data = _load_effective_services_catalog()
    section = data.get(category, {})
    if not isinstance(section, dict) or not section:
        return {}
    if key in section:
        return dict(section[key])
    default_key = _resolve_section_default_key(section, category, explicit_key=key)
    if default_key in section:
        if key:
            logger.warning(f"Service key '{key}' not found in category '{category}', using fallback '{default_key}'")
        return dict(section[default_key])
    return next(iter(section.values()), {})


def _build_services_api_entries(section: dict, category: str, source: str) -> list[dict]:
    """Convert one catalog section into API entries for a source."""
    if not isinstance(section, dict):
        return []

    default_key = _resolve_section_default_key(section, category)
    ordered_items = list(section.items())
    if default_key in section:
        ordered_items.sort(key=lambda item: item[0] != default_key)

    return [
        {
            "id": f"{source}:{key}",
            "name": val.get("name", key),
            "builtIn": True,
            "source": source,
            **{k: v for k, v in val.items() if k != "name"},
        }
        for key, val in ordered_items
        if isinstance(val, dict)
    ]


def build_services_api_response() -> dict:
    """Build the payload for ``GET /api/services`` with cloud and active local entries."""
    platform = get_deployment_platform()
    is_local = platform in _LOCAL_DEPLOY_PLATFORMS
    cloud_data = _load_cloud_services_catalog()
    local_data = _load_local_services_catalog(platform) if is_local else {}
    if is_local:
        local_data = _filter_local_asr_for_deployed_image(local_data)
    result: dict = {}
    for category in _SERVICE_CATEGORIES:
        if _active_slots is not None and category not in _active_slots:
            result[category] = []
            continue
        cloud_entries = _build_services_api_entries(cloud_data.get(category, {}), category, "cloud-nim")
        local_entries = _build_services_api_entries(local_data.get(category, {}), category, "self-hosted")
        result[category] = local_entries + cloud_entries if is_local else cloud_entries + local_entries
    return result


def parse_json_dict(raw: str, label: str = "JSON") -> dict:
    """Parse a JSON string into a dict. Returns {} on empty input or failure."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"Invalid {label}, ignoring: {raw!r}")
    return {}


def parse_env_int(name: str, default: int) -> int:
    """Parse an integer environment variable with safe fallback."""
    raw = os.getenv(name, str(default))
    try:
        return int(raw)
    except ValueError:
        logger.warning(f"Invalid {name}={raw!r}, falling back to default {default}")
        return default


def parse_env_bool(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable, treating empty as unset."""
    raw = (os.getenv(name) or "").strip()
    return raw.lower() == "true" if raw else default


def load_ipa_dictionary() -> dict | None:
    """Load a word-to-IPA pronunciation dictionary for ``NvidiaTTSService``.

    Reads ``TTS_IPA_FILE_PATH`` and parses JSON or YAML into a flat
    ``{grapheme: ipa}`` dict. Relative paths resolve from ``PROJECT_ROOT``.
    Returns ``None`` when unset, missing, malformed, or empty so callers can
    pass the result straight into ``custom_dictionary=``.
    """
    raw_path = os.getenv("TTS_IPA_FILE_PATH", "").strip()
    if not raw_path:
        return None

    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.is_file():
        logger.warning(f"TTS_IPA_FILE_PATH points to a missing file, ignoring: {path}")
        return None

    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        logger.warning(f"Failed to load TTS IPA dictionary from {path}: {exc}")
        return None

    if not isinstance(data, dict):
        logger.warning(f"TTS IPA dictionary must be a mapping, ignoring: {path}")
        return None

    dictionary = {
        str(word).strip(): str(ipa).strip() for word, ipa in data.items() if str(word).strip() and str(ipa).strip()
    }
    if not dictionary:
        logger.warning(f"TTS IPA dictionary is empty, ignoring: {path}")
        return None

    logger.info(f"Loaded TTS IPA dictionary from {path} ({len(dictionary)} entries)")
    return dictionary


def normalize_lang_code(code: str) -> str:
    """Normalize a language code to ISO casing (for example, ``DE-DE`` -> ``de-DE``)."""
    parts = code.split("-")
    if len(parts) == 2:
        return f"{parts[0].lower()}-{parts[1].upper()}"
    return code


def ensure_self_signed_cert(cert_dir: Path) -> tuple[str, str]:
    """Generate a self-signed TLS certificate if one doesn't already exist.

    Returns (cert_path, key_path).
    """
    cert_file = cert_dir / "cert.pem"
    key_file = cert_dir / "key.pem"
    if cert_file.exists() and key_file.exists():
        return str(cert_file), str(key_file)

    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.UTC))
        .not_valid_after(datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    cert_dir.mkdir(parents=True, exist_ok=True)
    key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    logger.info(f"Generated self-signed TLS cert at {cert_dir}")
    return str(cert_file), str(key_file)
