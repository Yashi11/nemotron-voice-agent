"""Dedicated structured ambient analysis for an explicitly shared display."""

from __future__ import annotations

from typing import Any

from loguru import logger
from pipecat.bus.messages import BusJobRequestMessage
from pipecat.pipeline.job_decorator import job
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.workers.base_worker import BaseWorker

from examples.omni_assistant.nvidia_omni_multimodal_service import (
    NvidiaOmniLLMService,
    NvidiaOmniSettings,
    image_message_part,
    text_message_part,
)
from examples.shared.json_parsing import extract_json_object
from webcam_frame_store import latest_webcam_frame

SCREEN_SUMMARY_TASK_NAME = "summarize_shared_screen"
_MAX_TOKENS = 1400
_INITIAL_MAX_TOKENS = 420
_INITIAL_PROMPT = (
    "Give a fast initial overview only. Return the normal JSON object, but keep charts and tables empty. "
    "State the main visible page, application, or content in observation and include only essential "
    "headings in visible_text."
)


class ScreenAgent(BaseWorker):
    """Maintain structured findings from the display explicitly approved by the user."""

    AGENT_NAME = "omni_screen"

    def __init__(
        self,
        name: str | None = None,
        *,
        api_key: str,
        base_url: str,
        model_id: str,
        extra_params: dict[str, Any] | None = None,
        system_prompt: str,
        prompt: str,
        reasoning: str = "off",
    ) -> None:
        """Initialize the dedicated display-analysis worker."""
        super().__init__(name or self.AGENT_NAME, active=True)
        self._system_prompt, self._prompt = system_prompt.strip(), prompt.strip()
        if not self._system_prompt or not self._prompt:
            raise ValueError("Screen prompts must be provided from prompts.yaml")
        extra = dict(extra_params or {})
        # The Speaker can safely answer chart questions only from explicit
        # group/series/value tuples. Enforce JSON mode rather than accepting a
        # prose-only observation that makes it infer associations from reading
        # order.
        extra["response_format"] = {"type": "json_object"}
        body = dict(extra.get("extra_body") or {})
        body["chat_template_kwargs"] = {
            **dict(body.get("chat_template_kwargs") or {}),
            "enable_thinking": reasoning == "on",
        }
        extra["extra_body"] = body
        self._omni = NvidiaOmniLLMService(
            api_key=api_key, base_url=base_url, extra=extra,
            settings=NvidiaOmniSettings(model=model_id, max_tokens=_MAX_TOKENS, temperature=0.0),
        )

    @job(name=SCREEN_SUMMARY_TASK_NAME)
    async def summarize_shared_screen(self, message: BusJobRequestMessage) -> None:
        """Analyze the latest approved display frame and publish structured findings."""
        payload = message.payload or {}
        session_id = str(payload.get("session_id") or "").strip()
        frame_metadata = payload.get("frame") if isinstance(payload.get("frame"), dict) else {}
        detail_level = "fast" if payload.get("detail_level") == "fast" else "full"
        observation = focus = ""
        frame = latest_webcam_frame(session_id, source="screen")
        if frame is not None:
            try:
                context = LLMContext(messages=[
                    {"role": "system", "content": self._system_prompt},
                    {
                        "role": "user",
                        "content": [
                            image_message_part(frame.data, frame.content_type),
                            text_message_part(_INITIAL_PROMPT if detail_level == "fast" else self._prompt),
                        ],
                    },
                ])
                result = await self._omni.run_multimodal_inference(
                    context,
                    max_tokens=_INITIAL_MAX_TOKENS if detail_level == "fast" else _MAX_TOKENS,
                    temperature=0.0,
                    stream=False,
                )
                parsed = extract_json_object(result.text.strip())
                if isinstance(parsed, dict):
                    focus = str(parsed.get("focus") or "").strip()
                    observation = _render_findings(parsed)
                else:
                    logger.warning("Ignoring malformed ScreenAgent response")
            except Exception as exc:
                logger.exception(f"Screen analysis failed: {exc}")
        await self.send_job_response(message.job_id, {
            "mode": "summary", "observation": observation, "focus": focus,
            "visual_control": {"intent": "none", "confidence": 0.0, "reason": ""},
            "frame": frame_metadata, "source": "screen", "detail_level": detail_level,
        })


def _render_findings(payload: dict[str, Any]) -> str:
    parts = [str(payload.get("observation") or "").strip()]
    for label, key in (("Selected text", "selected_text"), ("Visible text", "visible_text")):
        value = str(payload.get(key) or "").strip()
        if value:
            parts.append(f"{label}: {value}")
    charts = payload.get("charts")
    if isinstance(charts, list):
        chart_rows: list[str] = []
        legacy_items = [item.strip() for item in charts if isinstance(item, str) and item.strip()]
        if legacy_items:
            chart_rows.extend(legacy_items)
        for chart in charts:
            if not isinstance(chart, dict):
                continue
            title = str(chart.get("title") or "chart").strip()
            points = chart.get("data_points")
            if not isinstance(points, list):
                continue
            for point in points:
                if not isinstance(point, dict):
                    continue
                group = str(point.get("group") or "").strip()
                series = str(point.get("series") or "").strip()
                value = str(point.get("value") or "").strip()
                if group and series and value:
                    chart_rows.append(f"{title}: group={group}; series={series}; value={value}")
            insights = chart.get("insights")
            if not isinstance(insights, list):
                continue
            for insight in insights:
                if not isinstance(insight, dict):
                    continue
                scope = str(insight.get("scope") or "chart").strip()
                comparison = str(insight.get("comparison") or "").strip()
                best = insight.get("best") if isinstance(insight.get("best"), dict) else {}
                best_group = str(best.get("group") or "").strip()
                best_series = str(best.get("series") or "").strip()
                best_value = str(best.get("value") or "").strip()
                if best_group and best_series and best_value:
                    chart_rows.append(
                        f"{title} insight: scope={scope}; best={best_group} / {best_series} / {best_value}; "
                        f"comparison={comparison}"
                    )
        if chart_rows:
            parts.append(f"Charts: {' | '.join(chart_rows)}")
    tables = payload.get("tables")
    if isinstance(tables, list):
        table_rows: list[str] = []
        for table in tables:
            if not isinstance(table, dict):
                continue
            title = str(table.get("title") or "table").strip()
            rows = table.get("rows")
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                label = str(row.get("row_label") or "row").strip()
                values = row.get("values")
                if not isinstance(values, dict):
                    continue
                cells: list[str] = []
                for group, group_values in values.items():
                    if not isinstance(group_values, dict):
                        continue
                    for column, value in group_values.items():
                        value_text = str(value).strip()
                        if value_text:
                            cells.append(f"{str(group).strip()} / {str(column).strip()}={value_text}")
                if cells:
                    table_rows.append(f"{title}: {label}; {'; '.join(cells)}")
        if table_rows:
            parts.append(f"Tables: {' | '.join(table_rows)}")
    return "\n".join(part for part in parts if part).strip()
