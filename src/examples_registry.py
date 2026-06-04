# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Built-in voice-agent examples loaded from the root ``examples_registry.yaml``."""

import importlib
import os
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any, NamedTuple, TypedDict

import yaml

from utils import is_endpoint_reachable


class ExampleEntry(TypedDict):
    """Raw registry entry for one example."""

    label: str
    slots: list[str]
    capabilities: list[str]
    defaults: dict[str, list[str]]
    bot: str


class EnrichedExample(ExampleEntry):
    """Registry entry plus derived family/id/key fields."""

    family: str
    id: str
    key: str


class ServiceDefault(TypedDict, total=False):
    """Resolved default service entry from an example's service catalog."""

    id: str
    key: str
    name: str
    builtIn: bool
    source: str


class PromptDefault(TypedDict, total=False):
    """Resolved default prompt entry from an example's prompt catalog."""

    key: str
    description: str
    content: str
    default: bool
    builtIn: bool
    tools: list[str]


class PipelineFamily(TypedDict):
    """Pipeline family metadata exposed to the client."""

    id: str
    label: str


_SRC_ROOT = Path(__file__).resolve().parent
_REGISTRY_PATH = _SRC_ROOT.parent / "examples_registry.yaml"


def _load_yaml_registry() -> dict:
    """Load the registry YAML, failing loudly because startup depends on it."""
    try:
        data = yaml.safe_load(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RuntimeError(f"Failed to load examples registry from {_REGISTRY_PATH}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Examples registry root must be a mapping: {_REGISTRY_PATH}")
    return data


def _split_bot_spec(spec: str) -> tuple[str, str]:
    if ":" not in spec:
        raise RuntimeError(f"Example bot must be 'module.path:attr' (got {spec!r})")
    module_path, attr = spec.split(":", 1)
    if not module_path or not attr:
        raise RuntimeError(f"Example bot must be 'module.path:attr' (got {spec!r})")
    return module_path, attr


@cache
def _resolve_bot(spec: str) -> Callable[..., Any]:
    """Resolve a ``module.path:callable`` string only when the bot is used."""
    module_path, attr = _split_bot_spec(spec)
    module = importlib.import_module(module_path)
    bot = getattr(module, attr, None)
    if not callable(bot):
        raise RuntimeError(f"Example bot target is not callable: {spec!r}")
    return bot


def resolve_bot(example: EnrichedExample) -> Callable[..., Any]:
    """Return the lazily imported bot callable for an example."""
    return _resolve_bot(example["bot"])


def example_module_file(example: EnrichedExample) -> Path:
    """Return the module file path for an example's bot spec without importing it."""
    module_path, _ = _split_bot_spec(example["bot"])
    module_parts = Path(*module_path.split("."))
    module_file = (_SRC_ROOT / module_parts).with_suffix(".py")
    if module_file.is_file():
        return module_file
    package_file = _SRC_ROOT / module_parts / "__init__.py"
    if package_file.is_file():
        return package_file
    raise RuntimeError(f"Example {example['key']!r} bot module was not found: {example['bot']!r}")


def _load_yaml_mapping(path: Path) -> dict:
    """Load a YAML mapping from ``path``; return empty mapping when absent."""
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RuntimeError(f"Failed to load YAML from {path}") from exc
    return data if isinstance(data, dict) else {}


def _normalize_service_catalog(data: dict) -> dict[str, dict]:
    """Normalize a service catalog into ``{category: {key: entry}}``."""
    return {str(category): dict(section) for category, section in data.items() if isinstance(section, dict)}


def _entry_endpoint(entry: dict) -> str:
    return str(entry.get("server") or entry.get("base_url") or "")


def _rewrite_entry_for_host_runtime(entry: dict) -> dict:
    """Convert Compose endpoints to host-accessible endpoints outside Docker."""
    if os.getenv("APP_RUNTIME", "").strip().lower() == "container":
        return dict(entry)
    out = dict(entry)
    for field in ("base_url", "server"):
        value = out.get(field)
        if not isinstance(value, str):
            continue
        if field == "base_url":
            out[field] = (
                value.replace("http://nvidia-llm:8000/v1", "http://localhost:18000/v1")
                .replace("http://nvidia-llm-vllm:8000/v1", "http://localhost:18000/v1")
                .replace("host.docker.internal", "localhost")
            )
        else:
            out[field] = (
                value.replace("tts-service:50051", "localhost:50151")
                .replace("asr-service:50052", "localhost:50152")
                .replace("parakeet-ctc-asr:50052", "localhost:50152")
                .replace("parakeet-rnnt-asr:50052", "localhost:50152")
                .replace("nemotron-speech:50051", "localhost:50051")
                .replace("booking-server:8001", "localhost:8001")
                .replace("host.docker.internal", "localhost")
            )
    return out


def _rewrite_catalog_for_host_runtime(catalog: dict[str, dict]) -> dict[str, dict]:
    """Rewrite every local service endpoint for host-native metadata responses."""
    if os.getenv("APP_RUNTIME", "").strip().lower() == "container":
        return catalog
    return {
        category: {
            key: _rewrite_entry_for_host_runtime(entry) if isinstance(entry, dict) else entry
            for key, entry in section.items()
        }
        for category, section in catalog.items()
    }


def _first_reachable_variant(variants: list[tuple[str, dict]]) -> tuple[str, dict] | None:
    for platform_name, entry in variants:
        if is_endpoint_reachable(_entry_endpoint(_rewrite_entry_for_host_runtime(entry))):
            return platform_name, entry
    return None


def _load_local_service_catalog(example_dir: Path) -> dict[str, dict]:
    """Load platform-scoped local service entries for one example."""
    data = _load_yaml_mapping(example_dir / "services.local.yaml")
    variants: dict[str, dict[str, list[tuple[str, dict]]]] = {}
    for platform_name, platform_data in data.items():
        if not isinstance(platform_data, dict):
            continue
        for category, section in platform_data.items():
            if not isinstance(section, dict):
                continue
            category_variants = variants.setdefault(str(category), {})
            for key, entry in section.items():
                if not isinstance(entry, dict):
                    continue
                category_variants.setdefault(str(key), []).append((str(platform_name), dict(entry)))

    merged: dict[str, dict] = {}
    for category, section in variants.items():
        target = merged.setdefault(category, {})
        for service_key, entries in section.items():
            first_entry = entries[0][1]
            if all(entry == first_entry for _, entry in entries):
                target[service_key] = first_entry
                continue
            active = _first_reachable_variant(entries)
            if active is not None:
                active_platform, active_entry = active
                target[service_key] = active_entry
            else:
                active_platform = ""
            for platform_name, entry in entries:
                if platform_name != active_platform:
                    target[f"{service_key}-{platform_name}"] = entry
    return _rewrite_catalog_for_host_runtime(merged)


def _load_service_catalogs(example_dir: str) -> tuple[dict[str, dict], dict[str, dict]]:
    """Load cloud and local service catalogs for one example directory."""
    base = Path(example_dir)
    cloud = _normalize_service_catalog(_load_yaml_mapping(base / "services.cloud.yaml"))
    local = _load_local_service_catalog(base)
    return cloud, local


def _example_dir(example: EnrichedExample) -> Path:
    """Return the package directory for an example's bot module."""
    return example_module_file(example).resolve().parent


def _service_entry_payload(source: str, key: str, entry: dict) -> ServiceDefault:
    """Match service API entry shape while preserving every catalog param."""
    return {
        "id": f"{source}:{key}",
        "key": key,
        "name": str(entry.get("name") or key),
        "builtIn": True,
        "source": source,
        **{k: v for k, v in entry.items() if k != "name"},
    }


def _resolve_service_default(example: EnrichedExample, category: str, service_id: str) -> ServiceDefault:
    """Resolve one default service id to its full service-catalog payload.

    Prefers the self-hosted variant when it exists, matching the runtime
    ``/api/services`` precedence where reachable local entries shadow their
    cloud namesake. Falls back to the cloud entry when no local definition is
    present (the common cloud-only deployment).
    """
    cloud, local = _load_service_catalogs(str(_example_dir(example)))
    for source, catalog in (("self-hosted", local), ("cloud-nim", cloud)):
        section = catalog.get(category, {})
        if service_id in section and isinstance(section[service_id], dict):
            return _service_entry_payload(source, service_id, section[service_id])
    raise RuntimeError(
        f"Default service {service_id!r} for {example['key']} / {category!r} "
        "was not found in services.cloud.yaml or services.local.yaml"
    )


def _resolve_service_defaults(example: EnrichedExample) -> dict[str, list[ServiceDefault]]:
    """Hydrate example default service ids from the example's service catalog."""
    return {
        category: [_resolve_service_default(example, category, service_id) for service_id in service_ids]
        for category, service_ids in example["defaults"].items()
        if category != "prompt"
    }


def _resolve_prompt_default(example: EnrichedExample, prompt_key: str) -> PromptDefault:
    """Resolve one default prompt key to its prompt-catalog payload."""
    catalog = _load_yaml_mapping(_example_dir(example) / "prompts.yaml")
    entry = catalog.get(prompt_key)
    if not isinstance(entry, dict) or "content" not in entry:
        raise RuntimeError(f"Default prompt {prompt_key!r} for {example['key']} was not found in prompts.yaml")
    return {
        "key": prompt_key,
        "description": str(entry.get("description", "")),
        "content": str(entry.get("content", "")),
        "default": True,
        "builtIn": True,
        "tools": [tool for tool in (entry.get("tools_available") or []) if isinstance(tool, str)],
    }


def _resolve_prompt_defaults(example: EnrichedExample) -> list[PromptDefault]:
    """Hydrate default prompt ids from the example's prompt catalog."""
    return [_resolve_prompt_default(example, prompt_key) for prompt_key in example["defaults"].get("prompt", [])]


def prompt_default_key(example_key: str = "") -> str | None:
    """Return the configured default prompt key for an example, if any."""
    example = find(example_key)
    prompt_keys = example["defaults"].get("prompt", [])
    return prompt_keys[0] if prompt_keys else None


def _load_pipeline_families(data: dict) -> tuple[PipelineFamily, ...]:
    families = data.get("pipeline_families")
    if not isinstance(families, list):
        raise RuntimeError("examples_registry.yaml requires a pipeline_families list")

    result: list[PipelineFamily] = []
    for family in families:
        if not isinstance(family, dict):
            raise RuntimeError("Each pipeline_families item must be a mapping")
        family_id = str(family.get("id") or "").strip()
        label = str(family.get("label") or "").strip()
        if not family_id or not label:
            raise RuntimeError("Each pipeline family requires id and label")
        result.append({"id": family_id, "label": label})
    return tuple(result)


def _load_examples(data: dict) -> dict[str, dict[str, ExampleEntry]]:
    raw_examples = data.get("examples")
    if not isinstance(raw_examples, dict):
        raise RuntimeError("examples_registry.yaml requires an examples mapping")

    examples: dict[str, dict[str, ExampleEntry]] = {}
    for family, family_examples in raw_examples.items():
        if not isinstance(family_examples, dict):
            raise RuntimeError(f"Examples for family {family!r} must be a mapping")
        examples[str(family)] = {}
        for example_id, entry in family_examples.items():
            if not isinstance(entry, dict):
                raise RuntimeError(f"Example {family}/{example_id} must be a mapping")
            label = str(entry.get("label") or "").strip()
            bot_spec = str(entry.get("bot") or "").strip()
            slots = entry.get("slots", [])
            capabilities = entry.get("capabilities", [])
            defaults = entry.get("defaults", {})
            if not label or not bot_spec:
                raise RuntimeError(f"Example {family}/{example_id} requires label and bot")
            if not isinstance(slots, list) or not all(isinstance(slot, str) for slot in slots):
                raise RuntimeError(f"Example {family}/{example_id} slots must be a list of strings")
            if not isinstance(capabilities, list) or not all(
                isinstance(capability, str) for capability in capabilities
            ):
                raise RuntimeError(f"Example {family}/{example_id} capabilities must be a list of strings")
            if not isinstance(defaults, dict):
                raise RuntimeError(f"Example {family}/{example_id} defaults must be a mapping")
            normalized_defaults: dict[str, list[str]] = {}
            for slot, service_ids in defaults.items():
                if not isinstance(service_ids, list) or not all(
                    isinstance(service_id, str) for service_id in service_ids
                ):
                    raise RuntimeError(f"Example {family}/{example_id} defaults[{slot!r}] must be a list of strings")
                normalized_defaults[str(slot)] = list(service_ids)
            examples[str(family)][str(example_id)] = {
                "label": label,
                "slots": list(slots),
                "capabilities": list(capabilities),
                "defaults": normalized_defaults,
                "bot": bot_spec,
            }
    return examples


class Selection(NamedTuple):
    """Resolved ``selection`` field describing what the UI exposes."""

    raw: str
    locked: bool
    families: tuple[str, ...]
    example_keys: tuple[str, ...]
    default_key: str


def _parse_selection(
    raw: str,
    examples: dict[str, dict[str, ExampleEntry]],
) -> Selection:
    """Parse the ``selection`` value into a :class:`Selection`.

    Accepted values:
      * ``all`` — every example across every pipeline family.
      * ``<family>/all`` — every example in that family.
      * ``<family>/<example>`` — lock to one example, no switching.
    """
    cleaned = (raw or "").strip()
    if not cleaned:
        raise RuntimeError("examples_registry.yaml requires a 'selection' value")

    if cleaned == "all":
        families = tuple(examples.keys())
        example_keys = tuple(
            f"{family}/{example_id}" for family, family_examples in examples.items() for example_id in family_examples
        )
        if not example_keys:
            raise RuntimeError("selection 'all' requires at least one example")
        return Selection(cleaned, False, families, example_keys, example_keys[0])

    if "/" not in cleaned:
        raise RuntimeError(f"selection {cleaned!r} must be 'all', '<family>/all', or '<family>/<example>'")

    family, suffix = cleaned.split("/", 1)
    if family not in examples:
        raise RuntimeError(f"selection {cleaned!r}: unknown family {family!r}")

    if suffix == "all":
        example_keys = tuple(f"{family}/{example_id}" for example_id in examples[family])
        if not example_keys:
            raise RuntimeError(f"selection {cleaned!r}: family has no examples")
        return Selection(cleaned, False, (family,), example_keys, example_keys[0])

    if suffix not in examples[family]:
        raise RuntimeError(f"selection {cleaned!r}: unknown example {suffix!r} in family {family!r}")
    key = f"{family}/{suffix}"
    return Selection(cleaned, True, (family,), (key,), key)


_SUPPORTED_TRANSPORTS: tuple[str, ...] = ("webrtc", "websocket")


def _parse_transports(raw: str) -> tuple[str, ...]:
    """Parse the ``transports`` value into an ordered tuple of transport ids.

    Accepted values:
      * ``all`` — every supported transport.
      * a single transport id (e.g., ``webrtc`` or ``websocket``).
    """
    cleaned = (raw or "all").strip().lower()
    if cleaned == "all":
        return _SUPPORTED_TRANSPORTS
    if cleaned in _SUPPORTED_TRANSPORTS:
        return (cleaned,)
    raise RuntimeError(f"transports {cleaned!r} must be 'all' or one of {_SUPPORTED_TRANSPORTS}")


_REGISTRY_DATA = _load_yaml_registry()
PIPELINE_FAMILIES = _load_pipeline_families(_REGISTRY_DATA)
EXAMPLES = _load_examples(_REGISTRY_DATA)
_SELECTION = _parse_selection(
    os.getenv("EXAMPLE_SELECTION", "").strip() or str(_REGISTRY_DATA.get("selection") or ""),
    EXAMPLES,
)
_TRANSPORTS = _parse_transports(
    os.getenv("TRANSPORT_SELECTION", "").strip() or str(_REGISTRY_DATA.get("transports") or "all"),
)


def pipeline_family_ids() -> tuple[str, ...]:
    """Return all pipeline family ids defined in the YAML registry."""
    return tuple(family["id"] for family in PIPELINE_FAMILIES)


def pipeline_options(families: tuple[str, ...] | None = None) -> list[PipelineFamily]:
    """Return client-facing pipeline family metadata."""
    allowed = set(pipeline_family_ids() if families is None else families)
    return [family for family in PIPELINE_FAMILIES if family["id"] in allowed]


def is_locked() -> bool:
    """Return whether the selection pins the session to a single example."""
    return _SELECTION.locked


def visible_families() -> tuple[str, ...]:
    """Return the pipeline families exposed by the current selection."""
    return _SELECTION.families


def visible_example_keys() -> tuple[str, ...]:
    """Return the example keys exposed by the current selection."""
    return _SELECTION.example_keys


def visible_transports() -> tuple[str, ...]:
    """Return the transports exposed by the current selection."""
    return _TRANSPORTS


def _enrich(family: str, example_id: str, entry: ExampleEntry) -> EnrichedExample:
    """Project a registry entry into a flat dict with family/id and a wire ``key``."""
    return {**entry, "family": family, "id": example_id, "key": f"{family}/{example_id}"}


def _lookup_by_key(key: str) -> EnrichedExample:
    """Return the :class:`EnrichedExample` for ``family/id``; raises on miss."""
    family, example_id = key.split("/", 1)
    return _enrich(family, example_id, EXAMPLES[family][example_id])


def find(value: str = "") -> EnrichedExample:
    """Resolve an example.

    Routing rules:
      * Locked selection always wins, regardless of ``value``.
      * Otherwise prefer an explicit ``family/example`` match within the
        visible set, then fall back to the default example.
    """
    if _SELECTION.locked:
        return _lookup_by_key(_SELECTION.default_key)

    cleaned = (value or "").strip().lower()
    if cleaned and "/" in cleaned and cleaned in _SELECTION.example_keys:
        return _lookup_by_key(cleaned)
    return _lookup_by_key(_SELECTION.default_key)


def metadata(example: EnrichedExample) -> dict:
    """Strip internal fields (``bot`` spec) for client payloads."""
    defaults = _resolve_service_defaults(example)
    prompt_defaults = _resolve_prompt_defaults(example)
    if prompt_defaults:
        defaults["prompt"] = prompt_defaults
    return {
        "family": example["family"],
        "id": example["id"],
        "key": example["key"],
        "label": example["label"],
        "slots": example["slots"],
        "capabilities": example["capabilities"],
        "defaults": defaults,
    }


def visible_options() -> list[dict]:
    """Return metadata for every example exposed by the current selection."""
    return [metadata(_lookup_by_key(key)) for key in _SELECTION.example_keys]
