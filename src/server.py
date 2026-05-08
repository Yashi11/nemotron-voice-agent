# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""FastAPI server: serves the client UI and handles WebRTC/WebSocket signaling.

Routes:
  POST      /api/start       - WebRTC start (TTS readiness gate + session creation)
  POST      /api/offer       - WebRTC SDP offer
  PATCH     /api/offer       - WebRTC ICE candidate trickle
  WebSocket /api/ws          - WebSocket transport
  GET       /api/deployment  - Active example metadata
  GET       /api/prompts     - Prompt catalog
  GET       /api/services    - Service catalog (LLM, TTS, ASR, S2S)
  GET       /api/tts-config  - TTS voices & languages
  GET       /                - Built client UI (from client/dist/)

Run:
  uv run python src/server.py
  uv run python src/server.py --no-tls
  uv run python src/server.py --bot cascaded.agentic_airline.pipeline:bot
  uv run python src/server.py --tls-cert c --tls-key k
"""

from dotenv import load_dotenv

load_dotenv(override=True)

import argparse
import asyncio
import contextlib
import importlib
import json
import os
import sys
import urllib.request
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

import uvicorn
from fastapi import BackgroundTasks, FastAPI, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from loguru import logger
from pipecat.runner.types import SmallWebRTCRunnerArguments
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)

import config_store
import examples_registry
from cascaded.shared.prewarm import prewarm_tts, warmup_tts_synthesis
from utils import (
    PROJECT_ROOT,
    build_services_api_response,
    filter_session_config,
    is_endpoint_reachable,
    load_service_entry,
    load_yaml_file,
    parse_endpoint,
    set_active_slots,
)

CLIENT_DIST = PROJECT_ROOT / "client" / "dist"
PROMPT_FILE = PROJECT_ROOT / "prompt.yaml"
_session_configs: dict[str, dict] = {}
_CONNECT_PREWARM_TIMEOUT_SECS = 15
_CONNECT_HEALTH_TIMEOUT_SECS = 5
_NIM_READY_PATH = "/v1/health/ready"
_LOCAL_SERVICE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal"})
_SPEECH_READY_ENDPOINTS = {
    "asr": ("asr-service", 50052, 50152, 9001),
    "tts": ("tts-service", 50051, 50151, 9000),
}
_TURN_LISTEN_PORT = 3478
_INDEX_NO_CACHE_HEADERS = {"Cache-Control": "no-store"}


def _deployment_response(
    active: dict,
    forced_bot_fn: Callable[..., Any] | None,
    options: list[dict],
) -> dict:
    """Build the metadata payload consumed by the client selector page."""
    active_deployment = dict(active)
    active_deployment.setdefault("slots", [])

    locked = forced_bot_fn is not None or bool(os.getenv("DEFAULT_PIPELINE_MODE", "").strip())
    return {
        "active": active_deployment,
        "selectable": not locked,
        "options": [active_deployment] if locked else options,
    }


def _sanitize_session_config(data: dict, fallback_example_key: str = "") -> dict:
    """Sanitize request config and drop prompt overrides for the agentic-airline example."""
    example = _activate_example_catalog_by_key(str(data.get("pipeline_mode", "")) or fallback_example_key)
    filtered = filter_session_config(data)
    if example["id"] == "agentic-airline":
        filtered.pop("prompt_key", None)
        filtered.pop("prompt_content", None)
    return filtered


def _activate_example_catalog(module: Any, example: dict) -> None:
    """Use package-local service catalogs and slot filtering for a selected example."""
    module_dir = Path(module.__file__).resolve().parent
    for env_var, candidate in (
        ("SERVICES_CLOUD_PATH", module_dir / "services.cloud.yaml"),
        ("SERVICES_LOCAL_PATH", module_dir / "services.local.yaml"),
    ):
        os.environ[env_var] = str(candidate)
    set_active_slots(example.get("slots") or None)


def _activate_example_catalog_by_key(example_key: str = "") -> dict:
    """Activate the package-local service catalog for a registry example key."""
    selected = examples_registry.find(example_key)
    example = examples_registry.metadata(selected)
    module = importlib.import_module(selected["bot"].__module__)
    _activate_example_catalog(module, example)
    return example


def _load_bot(spec: str) -> tuple[Callable[..., Any], dict]:
    """Resolve ``module.path:attr`` into a bot callable and example metadata."""
    if ":" not in spec:
        raise ValueError(f"--bot must be 'module.path:attr' (got {spec!r})")
    module_path, attr = spec.split(":", 1)
    module = importlib.import_module(module_path)
    bot_fn = getattr(module, attr, None)
    if not callable(bot_fn):
        raise AttributeError(f"{module_path}:{attr} is not callable")

    builtin = next((e for e in examples_registry.iter_all() if e["bot"] is bot_fn), None)
    if builtin is not None:
        example = examples_registry.metadata(builtin)
    else:
        example = getattr(module, "EXAMPLE", None) or {}
        if not isinstance(example, dict) or not example:
            label = module_path.split(".")[-2 if module_path.endswith(".pipeline") else -1]
            example = {
                "family": module_path.split(".", 1)[0],
                "id": label.replace("_", "-"),
                "label": label.replace("_", " ").title(),
            }
        example = dict(example)
        example.setdefault("slots", [])
        example.setdefault("key", f"{example.get('family', module_path.split('.', 1)[0])}/{example.get('id', attr)}")

    _activate_example_catalog(module, example)

    return bot_fn, example


def _resolve_config(session_id: str = "", fallback_example_key: str = "", **query_params: str) -> dict:
    """Merge stored session config with query overrides; sanitize and hydrate from YAML."""
    base = _session_configs.pop(session_id, {}) if session_id else {}
    base.update({k: v for k, v in query_params.items() if v})
    return _sanitize_session_config({k: v for k, v in base.items() if v}, fallback_example_key=fallback_example_key)


def _get_default_tts_selection() -> tuple[str, str]:
    default_tts = load_service_entry("tts", "")
    return (
        default_tts.get("server", "grpc.nvcf.nvidia.com:443"),
        default_tts.get("voice_id", "Magpie-Multilingual.EN-US.Aria"),
    )


def _get_default_asr_selection() -> str:
    default_asr = load_service_entry("asr", "")
    return default_asr.get("server", "grpc.nvcf.nvidia.com:443")


def _get_default_llm_selection() -> tuple[str, str]:
    default_llm = load_service_entry("llm", "")
    return (
        default_llm.get("base_url", "https://integrate.api.nvidia.com/v1"),
        default_llm.get("model_id", "nvidia/nemotron-3-nano-30b-a3b"),
    )


def _store_session_config(data: dict, fallback_example_key: str = "") -> str:
    session_id = uuid.uuid4().hex[:12]
    _session_configs[session_id] = _sanitize_session_config(data, fallback_example_key=fallback_example_key)
    return session_id


def _select_bot(pipeline_mode: str, forced_bot_fn: Callable[..., Any] | None = None):
    """Return the bot for ``pipeline_mode`` (``DEFAULT_PIPELINE_MODE`` env wins; ``forced_bot_fn`` overrides)."""
    return forced_bot_fn if forced_bot_fn is not None else examples_registry.find(pipeline_mode)["bot"]


async def _run_blocking(func, *args, timeout: float | None = None):
    task = asyncio.to_thread(func, *args)
    if timeout is None:
        return await task
    return await asyncio.wait_for(task, timeout=timeout)


def _build_ice_servers(request: Request) -> list[dict]:
    """Build ICE server config for the WebRTC client.

    Coturn (compose `turn` profile) runs with long-term credentials matching
    TURN_USERNAME / TURN_PASSWORD. Set TURN_URL when TURN is hosted separately;
    otherwise derive the host from the request for same-host deployments.
    """
    username = os.environ.get("TURN_USERNAME", "").strip()
    password = os.environ.get("TURN_PASSWORD", "").strip()
    if not username or not password:
        return []

    turn_url = (os.environ.get("TURN_URL") or os.environ.get("TURN_SERVER_URL") or "").strip()
    if turn_url:
        base = turn_url.split("?", 1)[0].rstrip("/")
        if not base.startswith(("turn:", "turns:")):
            base = f"turn:{base}"
    else:
        host = request.headers.get("x-forwarded-host", request.url.hostname or "")
        host = host.split(",")[0].strip().split(":")[0]
        if not host or host in ("localhost", "127.0.0.1", "::1"):
            return []
        base = f"turn:{host}:{_TURN_LISTEN_PORT}"

    return [
        {
            "urls": [f"{base}?transport=udp", f"{base}?transport=tcp"],
            "username": username,
            "credential": password,
        }
    ]


def _should_skip_tts_prewarm(example: dict) -> bool:
    """Return whether TTS warm-up should be skipped for the active example."""
    if example.get("family") != "cascaded":
        return True
    return example.get("id") == "agentic-airline"


def _service_host_port(server: str) -> tuple[str, int]:
    """Parse a service address into host/port, raising on invalid input."""
    parsed = parse_endpoint(server)
    if parsed is None:
        raise RuntimeError(f"Invalid service address: {server or '(empty)'}")
    return parsed


def _check_service_port(label: str, server: str) -> None:
    if not is_endpoint_reachable(server):
        raise RuntimeError(
            f"Selected {label} service is not reachable at {server}. "
            f"Check that the {label} service is running and healthy."
        )


def _http_host(host: str) -> str:
    return f"[{host}]" if ":" in host and not host.startswith("[") else host


def _service_starting_message(label: str, *, ready_json: bool = False) -> str:
    expected_state = "report ready" if ready_json else "become healthy"
    return (
        f"Selected {label} service is still starting. "
        f"Wait for the service health check to {expected_state}, then try again."
    )


def _local_speech_ready_url(label: str, server: str) -> str:
    """Return the NIM HTTP readiness URL for built-in local ASR/TTS endpoints."""
    host, port = _service_host_port(server)
    normalized_host = host.strip("[]").lower()
    service_host, container_port, host_port, http_port = _SPEECH_READY_ENDPOINTS.get(
        label.lower(),
        ("", 0, 0, 0),
    )

    if normalized_host == service_host and port == container_port:
        return f"http://{service_host}:{http_port}{_NIM_READY_PATH}"
    if normalized_host in _LOCAL_SERVICE_HOSTS and port == host_port:
        return f"http://{_http_host(host)}:{http_port}{_NIM_READY_PATH}"

    return ""


def _local_llm_health_url(base_url: str, model_id: str) -> tuple[str, bool]:
    """Return (health_url, expects_ready_json) for built-in local LLM endpoints."""
    parsed = urlparse(base_url)
    host = parsed.hostname or ""
    if not host:
        return "", False

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    scheme = parsed.scheme or "http"
    normalized_host = host.strip("[]").lower()
    http_host = _http_host(host)

    if normalized_host == "nvidia-llm" and port == 8000:
        return f"{scheme}://nvidia-llm:8000{_NIM_READY_PATH}", False
    if normalized_host == "nvidia-llm-vllm" and port == 8000:
        return f"{scheme}://nvidia-llm-vllm:8000/health", False

    if normalized_host in _LOCAL_SERVICE_HOSTS and port == 18000:
        is_vllm = "30b-a3b" in model_id.lower() or "nvfp4" in model_id.lower()
        health_path = "/health" if is_vllm else _NIM_READY_PATH
        return f"{scheme}://{http_host}:18000{health_path}", False

    return "", False


def _check_http_health(label: str, target: str, health_url: str, expects_ready_json: bool = False) -> None:
    try:
        with urllib.request.urlopen(health_url, timeout=_CONNECT_HEALTH_TIMEOUT_SECS) as response:
            body = response.read()
    except Exception as exc:
        logger.warning(f"{label} health check failed for {target} via {health_url}: {exc}")
        raise RuntimeError(_service_starting_message(label)) from exc

    if not expects_ready_json:
        return

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning(f"{label} readiness check for {target} via {health_url} returned invalid JSON")
        raise RuntimeError(_service_starting_message(label, ready_json=True)) from exc

    if payload.get("status") != "ready" and payload.get("ready") is not True:
        logger.warning(f"{label} readiness check for {target} via {health_url} returned {payload}")
        raise RuntimeError(_service_starting_message(label, ready_json=True))


async def _run_http_readiness_check(
    label: str,
    target: str,
    health_url: str,
    expects_ready_json: bool = False,
) -> None:
    try:
        await _run_blocking(
            _check_http_health,
            label,
            target,
            health_url,
            expects_ready_json,
            timeout=_CONNECT_HEALTH_TIMEOUT_SECS + 1,
        )
    except TimeoutError as exc:
        raise RuntimeError(
            f"Selected {label} service is still starting. Health check timed out after {_CONNECT_HEALTH_TIMEOUT_SECS}s."
        ) from exc


async def _ensure_llm_ready_for_connection(config: dict, example: dict) -> None:
    """Run a local LLM readiness check before starting the session."""
    if "llm" not in (example.get("slots") or []):
        return

    default_base_url, default_model_id = _get_default_llm_selection()
    if example.get("id") == "agentic-airline":
        base_url = config.get("base_url", "") or os.getenv("FAST_LLM_BASE_URL", "") or default_base_url
        model_id = config.get("model_id", "") or os.getenv("FAST_LLM_MODEL", "") or default_model_id
    else:
        base_url = config.get("base_url", "") or default_base_url
        model_id = config.get("model_id", "") or default_model_id
    health_url, expects_ready_json = _local_llm_health_url(base_url, model_id)
    if not health_url:
        return

    await _run_http_readiness_check("LLM", base_url, health_url, expects_ready_json)


async def _ensure_asr_ready_for_connection(config: dict, example: dict) -> None:
    """Run an ASR readiness check before starting the session."""
    if example.get("family") != "cascaded":
        return

    asr_server = config.get("asr_server", "") or _get_default_asr_selection()
    ready_url = _local_speech_ready_url("ASR", asr_server)
    if ready_url:
        await _run_http_readiness_check("ASR", asr_server, ready_url, expects_ready_json=True)
        return

    try:
        await _run_blocking(
            _check_service_port,
            "ASR",
            asr_server,
            timeout=_CONNECT_HEALTH_TIMEOUT_SECS + 1,
        )
    except TimeoutError as exc:
        raise RuntimeError(
            f"Selected ASR service is still starting. Health check timed out after {_CONNECT_HEALTH_TIMEOUT_SECS}s."
        ) from exc


async def _ensure_tts_ready_for_connection(config: dict, example: dict) -> None:
    """Warm up TTS unless the selected pipeline handles it internally."""
    if _should_skip_tts_prewarm(example):
        return

    default_tts_server, default_tts_voice = _get_default_tts_selection()
    tts_server = config.get("tts_server", "") or default_tts_server
    voice_id = config.get("tts_voice_id", "") or default_tts_voice

    ready_url = _local_speech_ready_url("TTS", tts_server)
    if ready_url:
        await _run_http_readiness_check("TTS", tts_server, ready_url, expects_ready_json=True)

    try:
        is_ready = await _run_blocking(
            warmup_tts_synthesis,
            tts_server,
            voice_id,
            timeout=_CONNECT_PREWARM_TIMEOUT_SECS,
        )
    except TimeoutError as exc:
        raise RuntimeError(
            f"Selected TTS service is not available at {tts_server}; "
            f"health check timed out after {_CONNECT_PREWARM_TIMEOUT_SECS}s."
        ) from exc

    if not is_ready:
        raise RuntimeError(
            f"Selected TTS service is not available at {tts_server}. Check that the TTS service is running and healthy."
        )


async def _ensure_services_ready_for_connection(config: dict, example: dict) -> None:
    """Verify selected services before the UI starts a session."""
    await _ensure_llm_ready_for_connection(config, example)
    await _ensure_asr_ready_for_connection(config, example)
    await _ensure_tts_ready_for_connection(config, example)


def create_app(
    host: str = "localhost",
    bot_spec: str = "",
    example_key: str = "",
    all_examples: bool = False,
) -> FastAPI:
    """Build and return the FastAPI application with all routes."""
    forced_bot_fn: Callable[..., Any] | None = None
    selected_example = examples_registry.find(example_key)
    deployment = examples_registry.metadata(selected_example)
    fallback_example_key = deployment["key"]
    selector_options = (
        examples_registry.all_selector_options() if all_examples else examples_registry.selector_options()
    )
    if bot_spec:
        forced_bot_fn, deployment = _load_bot(bot_spec)
        fallback_example_key = deployment["key"]
        logger.info(f"Loaded bot override: {bot_spec} -> deployment={deployment}")
    elif example_key:
        forced_bot_fn = selected_example["bot"]
        _activate_example_catalog_by_key(deployment["key"])
        logger.info(f"Loaded example: {deployment['key']} -> deployment={deployment}")

    handler = SmallWebRTCRequestHandler(host=host)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await handler.close()

    app = FastAPI(lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _resolve_example(config: dict) -> dict:
        """Return the active example metadata: pinned for forced bot, else inferred from config."""
        if forced_bot_fn is not None:
            return deployment
        return examples_registry.metadata(examples_registry.find(config.get("pipeline_mode", "")))

    async def _readiness_check_or_503(config: dict, log_label: str) -> JSONResponse | None:
        """Return a 503 response if any selected service is not ready, else ``None``."""
        try:
            await _ensure_services_ready_for_connection(config, _resolve_example(config))
        except RuntimeError as exc:
            logger.warning(f"Rejecting {log_label} during service readiness check: {exc}")
            return JSONResponse(status_code=503, content={"info": str(exc)})
        return None

    @app.get("/api/deployment")
    async def get_deployment():
        return _deployment_response(deployment, forced_bot_fn, selector_options)

    # ---- Session config (avoids long URLs for prompts / system_prompt) ----

    @app.post("/api/session-config")
    async def create_session_config(request: Request):
        """Store pipeline config server-side, return a short session_id."""
        config = _sanitize_session_config(await request.json(), fallback_example_key=fallback_example_key)
        if (failure := await _readiness_check_or_503(config, "session config")) is not None:
            return failure
        return {"session_id": _store_session_config(config, fallback_example_key=fallback_example_key)}

    @app.post("/api/start")
    async def start_bot(request: Request):
        """Run readiness checks before starting a WebRTC session."""
        config = _sanitize_session_config(await request.json(), fallback_example_key=fallback_example_key)
        if (failure := await _readiness_check_or_503(config, "WebRTC start")) is not None:
            return failure
        session_id = _store_session_config(config, fallback_example_key=fallback_example_key)
        return {"webrtcUrl": f"/api/offer?session_id={session_id}"}

    # ---- WebRTC signaling ----

    @app.post("/api/offer")
    async def offer(
        request: SmallWebRTCRequest,
        background_tasks: BackgroundTasks,
        session_id: str = Query(default=""),
        pipeline_mode: str = Query(default=""),
    ):
        config = _resolve_config(session_id, fallback_example_key=fallback_example_key, pipeline_mode=pipeline_mode)
        bot_fn = _select_bot(config.get("pipeline_mode", "cascaded"), forced_bot_fn)
        example = _resolve_example(config)

        async def on_connection(connection: SmallWebRTCConnection):
            body = dict(request.request_data) if isinstance(request.request_data, dict) else {}
            body.update(config)
            _activate_example_catalog_by_key(example["key"])
            runner_args = SmallWebRTCRunnerArguments(webrtc_connection=connection, body=body)
            background_tasks.add_task(bot_fn, runner_args)

        return await handler.handle_web_request(
            request=request,
            webrtc_connection_callback=on_connection,
        )

    @app.patch("/api/offer")
    async def ice_candidate(request: SmallWebRTCPatchRequest):
        await handler.handle_patch_request(request)
        return {"status": "success"}

    # ---- WebSocket transport ----

    @app.websocket("/api/ws")
    async def websocket_endpoint(
        websocket: WebSocket,
        session_id: str = Query(default=""),
        pipeline_mode: str = Query(default=""),
    ):
        stream_id = session_id or "-"
        with logger.contextualize(stream_id=stream_id):
            config = _resolve_config(session_id, fallback_example_key=fallback_example_key, pipeline_mode=pipeline_mode)
            if not session_id:
                try:
                    await _ensure_services_ready_for_connection(config, _resolve_example(config))
                except RuntimeError as exc:
                    logger.warning(f"Rejecting WebSocket start during service readiness check: {exc}")
                    await websocket.close(code=1011, reason=str(exc))
                    return

            await websocket.accept()
            bot_fn = _select_bot(config.get("pipeline_mode", "cascaded"), forced_bot_fn)
            _activate_example_catalog_by_key(_resolve_example(config)["key"])

            runner_args = SimpleNamespace(
                websocket=websocket,
                body=config,
                handle_sigint=False,
                pipeline_idle_timeout_secs=None,
            )
            try:
                await bot_fn(runner_args)
            except Exception as e:
                logger.error(f"WebSocket session error: {e}")
            finally:
                with contextlib.suppress(Exception):
                    await websocket.close()

    # ---- Prompt catalog (read-only, defaults from prompt.yaml) ----

    @app.get("/api/prompts")
    async def get_prompts():
        data = load_yaml_file(PROMPT_FILE)
        return [
            {
                "key": key,
                "description": val.get("description", ""),
                "content": val.get("content", ""),
                "builtIn": True,
            }
            for key, val in data.items()
            if isinstance(val, dict) and "content" in val
        ]

    # ---- Service catalog (services.cloud.yaml or services.local.yaml) ----

    @app.get("/api/services")
    async def get_services(pipeline_mode: str = Query(default="")):
        _activate_example_catalog_by_key(pipeline_mode or fallback_example_key)
        return build_services_api_response()

    # ---- TTS config (voices & languages from the TTS service) ----

    @app.get("/api/tts-config")
    async def tts_config(
        server: str = Query(default=""),
        voice_id: str = Query(default=""),
    ):
        if server:
            _, default_tts_voice = _get_default_tts_selection()
            cached = config_store.get(f"tts:{server}")
            if cached:
                return cached
            return await _run_blocking(prewarm_tts, server, voice_id or default_tts_voice)
        return config_store.get("tts", {"languages": [], "voices": []})

    # ---- WebRTC ICE servers (TURN credentials) ----

    @app.get("/api/ice-servers")
    async def ice_servers(request: Request):
        """Return ICE server config for the WebRTC client.

        Empty list when TURN is not configured (client falls back to host-only
        candidates, which is fine for local/LAN deployments).
        """
        return {"iceServers": _build_ice_servers(request)}

    # ---- Static client UI ----

    if CLIENT_DIST.is_dir():
        logger.info(f"Serving client UI from {CLIENT_DIST}")
        index_path = CLIENT_DIST / "index.html"

        @app.get("/")
        async def root():
            return FileResponse(index_path, headers=_INDEX_NO_CACHE_HEADERS)

        @app.get("/{path:path}")
        async def client_files(path: str = ""):
            if path.startswith("api/"):
                return
            file = CLIENT_DIST / path
            if file.is_file():
                return FileResponse(file)
            return FileResponse(index_path, headers=_INDEX_NO_CACHE_HEADERS)
    else:
        logger.warning(f"Client build not found at {CLIENT_DIST}. Run 'npm run build' in client/ to enable the UI.")

        @app.get("/")
        async def root():
            return {
                "status": "running",
                "hint": "Build the client UI: cd client && npm run build",
            }

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


def main():
    """Parse CLI args and start the uvicorn server."""
    parser = argparse.ArgumentParser(description="Pipeline NVIDIA Server")
    parser.add_argument("--host", type=str, default="localhost")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument(
        "--example",
        type=str,
        default="",
        help="Registry example key to run, for example cascaded/generic or cascaded/agentic-airline",
    )
    parser.add_argument("--all-examples", action="store_true", help="Expose all registered examples in the UI selector")
    parser.add_argument("--bot", type=str, default="", help="Optional bot module path, for example pkg.mod:bot")
    parser.add_argument("--no-tls", action="store_true", help="Disable HTTPS (use plain HTTP)")
    parser.add_argument("--tls-cert", type=str, help="Path to TLS certificate file")
    parser.add_argument("--tls-key", type=str, help="Path to TLS key file")
    parser.add_argument("-v", "--verbose", action="count", default=0)
    args = parser.parse_args()

    logger.remove()
    logger.configure(extra={"stream_id": "-"})
    logger.add(
        sys.stderr,
        level="TRACE" if args.verbose else "DEBUG",
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "{name}:{function}:{line} - "
            "[stream_id={extra[stream_id]}] "
            "<level>{message}</level>"
        ),
    )

    app = create_app(host=args.host, bot_spec=args.bot, example_key=args.example, all_examples=args.all_examples)

    ssl_kwargs: dict = {}
    scheme = "http"
    if not args.no_tls:
        if args.tls_cert and args.tls_key:
            ssl_kwargs = {"ssl_certfile": args.tls_cert, "ssl_keyfile": args.tls_key}
        else:
            cert_dir = Path(__file__).resolve().parent.parent / ".certs"
            from utils import ensure_self_signed_cert

            cert_file, key_file = ensure_self_signed_cert(cert_dir)
            ssl_kwargs = {"ssl_certfile": cert_file, "ssl_keyfile": key_file}
        scheme = "https"

    ui_url = f"{scheme}://{args.host}:{args.port}/"
    if CLIENT_DIST.is_dir():
        logger.info(f"Server ready -> {ui_url}")
    else:
        logger.info(f"Server ready (API only) -> {ui_url}")
        logger.info("Build the client: cd client && npm run build")

    uvicorn.run(app, host=args.host, port=args.port, **ssl_kwargs)


if __name__ == "__main__":
    main()
