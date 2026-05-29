# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

# ruff: noqa: D100, D101, D102

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import hydrate_config_from_catalog


class ServiceCatalogHydrationTests(unittest.TestCase):
    def test_hydrates_selected_builtin_details_from_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cloud_path = Path(tmpdir) / "services.cloud.yaml"
            cloud_path.write_text(
                """
llm:
  nemotron:
    name: Nemotron
    model_id: catalog-model
    base_url: https://catalog.example/v1
    system_prompt: catalog system
    extra_params: '{"extra_body":{"chat_template_kwargs":{"enable_thinking":false}}}'
asr:
  parakeet:
    name: Parakeet
    server: catalog-asr:443
    model: catalog-asr-model
    function_id: catalog-asr-function
tts:
  magpie:
    name: Magpie
    server: catalog-tts:443
    function_id: catalog-tts-function
""",
                encoding="utf-8",
            )

            config = {
                "llm_id": "cloud-nim:nemotron",
                "model_id": "client-model",
                "base_url": "https://client.example/v1",
                "system_prompt": "client system",
                "extra_params": "{}",
                "asr_id": "cloud-nim:parakeet",
                "asr_server": "client-asr:443",
                "asr_model": "client-asr-model",
                "asr_function_id": "client-asr-function",
                "tts_id": "cloud-nim:magpie",
                "tts_server": "client-tts:443",
                "tts_function_id": "client-tts-function",
            }

            with patch.dict(
                os.environ,
                {
                    "SERVICES_CLOUD_PATH": str(cloud_path),
                    "SERVICES_LOCAL_PATH": str(Path(tmpdir) / "missing-services.local.yaml"),
                },
            ):
                hydrate_config_from_catalog(config)

            self.assertEqual(config["model_id"], "catalog-model")
            self.assertEqual(config["base_url"], "https://catalog.example/v1")
            self.assertEqual(config["system_prompt"], "catalog system")
            self.assertEqual(
                config["extra_params"],
                '{"extra_body":{"chat_template_kwargs":{"enable_thinking":false}}}',
            )
            self.assertEqual(config["asr_server"], "catalog-asr:443")
            self.assertEqual(config["asr_model"], "catalog-asr-model")
            self.assertEqual(config["asr_function_id"], "catalog-asr-function")
            self.assertEqual(config["tts_server"], "catalog-tts:443")
            self.assertEqual(config["tts_function_id"], "catalog-tts-function")

    def test_hydrates_raw_catalog_key_for_direct_clients(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cloud_path = Path(tmpdir) / "services.cloud.yaml"
            cloud_path.write_text(
                """
llm:
  nemotron:
    name: Nemotron
    model_id: catalog-model
    base_url: https://catalog.example/v1
    system_prompt: ""
    extra_params: '{"extra_body":{"top_k":1}}'
""",
                encoding="utf-8",
            )
            config = {"llm_id": "nemotron"}

            with patch.dict(
                os.environ,
                {
                    "SERVICES_CLOUD_PATH": str(cloud_path),
                    "SERVICES_LOCAL_PATH": str(Path(tmpdir) / "missing-services.local.yaml"),
                },
            ):
                hydrate_config_from_catalog(config)

            self.assertEqual(config["model_id"], "catalog-model")
            self.assertEqual(config["base_url"], "https://catalog.example/v1")
            self.assertEqual(config["extra_params"], '{"extra_body":{"top_k":1}}')


if __name__ == "__main__":
    unittest.main()
