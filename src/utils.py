# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Shared utility functions."""

import ipaddress
import json
import os
import socket
import time
from pathlib import Path
from urllib.parse import urlparse

import yaml
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_FILENAME = "prompts.yaml"
TOOLS_FILENAME = "tools.yaml"


def _services_cloud_path() -> Path:
    return Path(os.getenv("SERVICES_CLOUD_PATH", str(PROJECT_ROOT / "src/cascaded/generic/services.cloud.yaml")))


def _services_local_path() -> Path:
    return Path(os.getenv("SERVICES_LOCAL_PATH", str(PROJECT_ROOT / "src/cascaded/generic/services.local.yaml")))


_SLOT_CONFIG_KEYS: dict[str, frozenset[str]] = {
    "llm": frozenset({"llm_id", "model_id", "base_url", "system_prompt", "extra_params"}),
    "asr": frozenset({"asr_id", "asr_server", "asr_model", "asr_function_id"}),
    "tts": frozenset({"tts_id", "tts_server", "tts_voice_id", "tts_function_id"}),
    "s2s": frozenset({"s2s_id", "s2s_server"}),
}
_SLOT_AGNOSTIC_KEYS: frozenset[str] = frozenset({"pipeline_mode", "prompt_key", "prompt_content"})
_active_slots: frozenset[str] | None = None
_active_slot_order: tuple[str, ...] | None = None


def set_active_slots(slots: list[str] | tuple[str, ...] | None) -> None:
    """Declare which example slots are active; ``None`` disables filtering."""
    global _active_slots, _active_slot_order
    if slots:
        _active_slot_order = tuple(slots)
        _active_slots = frozenset(_active_slot_order)
    else:
        _active_slot_order = None
        _active_slots = None


def resolve_prompt_catalog_path(module_file: str | Path) -> Path:
    """Return the prompts.yaml path beside an example module (``PROMPT_FILE_PATH`` env overrides)."""
    override = os.getenv("PROMPT_FILE_PATH", "").strip()
    return Path(override) if override else Path(module_file).resolve().parent / PROMPTS_FILENAME


def load_prompt_catalog(module_file: str | Path) -> dict:
    """Load the prompt catalog beside an example module."""
    return load_yaml_file(resolve_prompt_catalog_path(module_file))


def resolve_tools_catalog_path(module_file: str | Path) -> Path:
    """Return the tools.yaml path beside an example module (``TOOLS_FILE_PATH`` env overrides)."""
    override = os.getenv("TOOLS_FILE_PATH", "").strip()
    return Path(override) if override else Path(module_file).resolve().parent / TOOLS_FILENAME


def load_tools_catalog(module_file: str | Path) -> dict:
    """Load the tools catalog beside an example module."""
    return load_yaml_file(resolve_tools_catalog_path(module_file))


def resolve_tools_available(module_file: str | Path, prompt_key: str) -> list[str]:
    """Return the list of tool names declared under a prompt's ``tools_available``.

    Returns an empty list when the prompt is missing from the example catalog
    (e.g. a custom client-supplied prompt) or has no tools declared.
    """
    if not prompt_key:
        return []
    catalog = load_prompt_catalog(module_file)
    entry = catalog.get(prompt_key)
    if not isinstance(entry, dict):
        return []
    raw = entry.get("tools_available")
    if not isinstance(raw, list):
        return []
    return [name for name in raw if isinstance(name, str)]


def default_prompt_key(catalog: dict) -> str | None:
    """First entry marked ``default: true``, else first valid entry, else ``None``."""
    first_valid = None
    for key, value in catalog.items():
        if not isinstance(value, dict) or "content" not in value:
            continue
        if value.get("default") is True:
            return key
        if first_valid is None:
            first_valid = key
    return first_valid


def resolve_prompt(
    module_file: str | Path,
    prompt_content: str = "",
    prompt_key: str = "",
) -> tuple[str, str]:
    """Resolve ``(key, content)`` from the client body or the example's prompt catalog.

    Priority: client-provided content > ``prompt_key`` > ``PROMPT_SELECTOR`` env > catalog default.
    """
    if prompt_content:
        return prompt_key or "custom", prompt_content

    catalog_path = resolve_prompt_catalog_path(module_file)
    catalog = load_yaml_file(catalog_path)
    fallback = default_prompt_key(catalog)
    if fallback is None:
        raise KeyError(f"No prompts with content in {catalog_path}")

    requested = prompt_key or os.getenv("PROMPT_SELECTOR", "").strip() or fallback
    if requested not in catalog:
        logger.warning(f"Prompt '{requested}' not found in {catalog_path}; using '{fallback}'")
        requested = fallback
    logger.info(f"Loaded prompt from {catalog_path} [{requested}]")
    return requested, catalog[requested]["content"]


def load_yaml_file(filepath: Path) -> dict:
    """Load and return the contents of a YAML file as a dict.

    Returns an empty dict if the file is absent, unreadable, malformed, or
    the parsed value is not a mapping.
    """
    if not filepath.is_file():
        return {}
    try:
        data = yaml.safe_load(filepath.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        logger.warning(f"Failed to load YAML from {filepath}: {exc}")
        return {}
    return data if isinstance(data, dict) else {}


def is_nvcf(server: str) -> bool:
    """Auto-detect if a gRPC server is NVIDIA Cloud Functions (requires SSL)."""
    return "nvcf.nvidia.com" in server


def _normalize_services_catalog(data: object) -> dict:
    """Normalize a services catalog into ``{category: {key: entry}}``."""
    src = data if isinstance(data, dict) else {}
    return {category: dict(section) for category, section in src.items() if isinstance(section, dict)}


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
            .replace("booking-server:8001", "localhost:8001")
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


def _section_default_key(section: dict, explicit_key: str = "") -> str:
    """Return ``explicit_key`` when present, else the first key in ``section``."""
    if explicit_key and explicit_key in section:
        return explicit_key
    return next(iter(section), "")


_REACHABILITY_TIMEOUT_SECS = 2.0
_REACHABILITY_CACHE_TTL_SECS = 5.0
_reachability_cache: dict[str, tuple[float, bool]] = {}


def parse_endpoint(server: str) -> tuple[str, int] | None:
    """Parse ``server`` (host[:port] or URL) into ``(host, port)``.

    Returns ``None`` when the address cannot be parsed.
    """
    if not server:
        return None
    parsed = urlparse(server if "://" in server else f"//{server}")
    host = parsed.hostname
    if not host:
        return None
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return host, port


def is_endpoint_reachable(server: str) -> bool:
    """Return whether ``server`` accepts a TCP connection.

    Cached for ``_REACHABILITY_CACHE_TTL_SECS`` seconds per address so a single
    ``/api/services`` request does not probe each endpoint multiple times.
    """
    address = parse_endpoint(server)
    if address is None:
        return False
    cache_key = f"{address[0]}:{address[1]}"
    cached = _reachability_cache.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] < _REACHABILITY_CACHE_TTL_SECS:
        return cached[1]
    try:
        with socket.create_connection(address, timeout=_REACHABILITY_TIMEOUT_SECS):
            ok = True
    except OSError:
        ok = False
    _reachability_cache[cache_key] = (now, ok)
    return ok


def _filter_reachable_entries(catalog: dict) -> dict:
    """Drop catalog entries whose endpoint is not reachable from this runtime."""
    filtered: dict = {}
    for category, section in catalog.items():
        if not isinstance(section, dict):
            filtered[category] = section
            continue
        kept = {
            key: entry
            for key, entry in section.items()
            if not isinstance(entry, dict)
            or is_endpoint_reachable(str(entry.get("server") or entry.get("base_url") or ""))
        }
        filtered[category] = kept
    return filtered


def _load_cloud_services_catalog() -> dict:
    """Load cloud service entries from ``services.cloud.yaml``."""
    return _normalize_services_catalog(load_yaml_file(_services_cloud_path()))


def _load_local_services_catalog() -> dict:
    """Load all platform sections from ``services.local.yaml`` into one catalog.

    Identical entries across platforms are deduplicated; conflicting entries are
    suffixed with the platform name so each variant remains addressable.
    """
    local_path = _services_local_path()
    if not local_path.is_file():
        return _normalize_services_catalog({})
    data = load_yaml_file(local_path)
    if not isinstance(data, dict):
        return _normalize_services_catalog({})
    merged: dict = {}
    for platform_name, platform_data in data.items():
        if not isinstance(platform_data, dict):
            continue
        for category, section in platform_data.items():
            if not isinstance(section, dict):
                continue
            cat_merged = merged.setdefault(category, {})
            for key, entry in section.items():
                if key not in cat_merged:
                    cat_merged[key] = entry
                elif cat_merged[key] != entry:
                    cat_merged[f"{key}-{platform_name}"] = entry
    return _rewrite_local_runtime_endpoints(_normalize_services_catalog(merged))


def _merge_services_catalogs(*catalogs: dict) -> dict:
    """Merge service catalogs by category and key (later catalogs win on conflicts)."""
    merged: dict = {}
    for catalog in catalogs:
        for category, section in catalog.items():
            if not isinstance(section, dict):
                continue
            target = merged.setdefault(category, {})
            target.update(section)
    return merged


def _load_effective_services_catalog() -> dict:
    """Return the merged catalog combining cloud and reachable local entries.

    Local entries win on shared keys when their endpoint is reachable, so the
    pipeline picks the deployed local service. When the local endpoint is not
    reachable it is dropped, and the cloud entry takes effect.
    """
    cloud = _load_cloud_services_catalog()
    local = _filter_reachable_entries(_load_local_services_catalog())
    return _merge_services_catalogs(cloud, local)


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
            elif isinstance(value, dict | list):
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
    if not key:
        return {}
    if source == "cloud-nim":
        catalog = _load_cloud_services_catalog()
    elif source == "self-hosted":
        catalog = _load_local_services_catalog()
    else:
        return {}
    entry = catalog.get(category, {}).get(key)
    return dict(entry) if isinstance(entry, dict) else {}


def load_service_entry(category: str, key: str) -> dict:
    """Load a catalog entry by category and key from the effective catalog.

    Falls back to the first entry in the category when the explicit ``key`` is
    not present (or empty).
    """
    data = _load_effective_services_catalog()
    section = data.get(category, {})
    if not isinstance(section, dict) or not section:
        return {}
    default_key = _section_default_key(section, key)
    if key and default_key != key:
        logger.warning(f"Service key '{key}' not found in category '{category}', using fallback '{default_key}'")
    return dict(section[default_key]) if default_key in section else {}


def _build_services_api_entries(section: dict, category: str, source: str) -> list[dict]:
    """Convert one catalog section into API entries for a source."""
    if not isinstance(section, dict):
        return []

    selected_key = _section_default_key(section)
    ordered_items = list(section.items())
    if selected_key in section:
        ordered_items.sort(key=lambda item: item[0] != selected_key)

    return [
        {
            "id": f"{source}:{key}",
            "name": val.get("name", key),
            "builtIn": True,
            "source": source,
            **{k: v for k, v in val.items() if k != "name"},
            "selected": key == selected_key,
        }
        for key, val in ordered_items
        if isinstance(val, dict)
    ]


def _services_api_categories(*catalogs: dict) -> tuple[str, ...]:
    """Return service categories ordered by the active example's ``slots``."""
    ordered: list[str] = list(_active_slot_order or ())
    for catalog in catalogs:
        ordered.extend(category for category in catalog if category not in ordered)
    return tuple(ordered)


def build_services_api_response() -> dict:
    """Build the payload for ``GET /api/services`` with cloud and reachable local entries."""
    cloud_data = _load_cloud_services_catalog()
    local_data = _filter_reachable_entries(_load_local_services_catalog())
    result: dict = {}
    for category in _services_api_categories(cloud_data, local_data):
        if _active_slots is not None and category not in _active_slots:
            result[category] = []
            continue
        cloud_entries = _build_services_api_entries(cloud_data.get(category, {}), category, "cloud-nim")
        local_entries = _build_services_api_entries(local_data.get(category, {}), category, "self-hosted")
        result[category] = local_entries + cloud_entries
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


def parse_env_int(name: str, default: int, min_value: int | None = None) -> int:
    """Parse an integer environment variable with safe fallback and optional minimum."""
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError:
        logger.warning(f"Invalid {name}={raw!r}, falling back to default {default}")
        value = default
    if min_value is not None and value < min_value:
        logger.warning(f"{name}={value!r} is below minimum {min_value}, clamping")
        return min_value
    return value


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
