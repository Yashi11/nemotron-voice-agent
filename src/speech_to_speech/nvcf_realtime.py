# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""NVCF-compatible OpenAI Realtime LLM service.

Workaround for Pipecat's OpenAIRealtimeLLMService which does not support
custom WebSocket headers or opting out of the ``?model=`` query parameter.

NVIDIA Cloud Functions (NVCF) endpoints require:
  - ``function-id`` header for routing
  - No ``?model=`` query parameter (function_id selects the model)

This follows the same pattern as Pipecat's ``AzureRealtimeLLMService``.

TODO: Remove once Pipecat adds native NVCF support or an
``additional_headers`` parameter to ``OpenAIRealtimeLLMService``.
"""

from loguru import logger
from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService


class NVCFRealtimeLLMService(OpenAIRealtimeLLMService):
    """OpenAI Realtime-compatible service for NVIDIA Cloud Function endpoints.

    Subclasses ``OpenAIRealtimeLLMService`` to:
      1. Inject the ``function-id`` header required by NVCF.
      2. Strip the ``?model=`` query parameter that Pipecat appends
         (NVCF uses the function_id for model routing instead).

    When ``function_id`` is empty, behaves identically to the base class
    (safe for non-NVCF endpoints like local servers or OpenAI).
    """

    def __init__(self, *, function_id: str = "", **kwargs):
        """Initialize with optional NVCF function_id for model routing."""
        super().__init__(**kwargs)
        self._function_id = function_id
        if function_id:
            self.base_url = self.base_url.split("?")[0]
            logger.debug(f"NVCF mode: function_id={function_id}, url={self.base_url}")

    async def _connect(self):
        if self._websocket:
            return
        try:
            from websockets.asyncio.client import connect as websocket_connect

            headers = {"authorization": f"Bearer {self.api_key}"}
            if self._function_id:
                headers["function-id"] = self._function_id
            self._websocket = await websocket_connect(
                uri=self.base_url,
                additional_headers=headers,
            )
            self._receive_task = self.create_task(self._receive_task_handler())
        except Exception as e:
            await self.push_error(error_msg=f"Error connecting: {e}", exception=e)
            self._websocket = None
