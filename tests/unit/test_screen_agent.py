# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

# ruff: noqa: D100, D103

from examples.omni_assistant_subagents.subagents.screen.agent import _render_findings


def test_render_findings_preserves_each_chart_data_point_association() -> None:
    rendered = _render_findings(
        {
            "charts": [
                {
                    "title": "chart",
                    "data_points": [
                        {"group": "configuration one", "series": "repeated series", "value": "value one"},
                        {"group": "configuration two", "series": "repeated series", "value": "value two"},
                    ],
                }
            ]
        }
    )

    assert "chart: group=configuration one; series=repeated series; value=value one" in rendered
    assert "chart: group=configuration two; series=repeated series; value=value two" in rendered


def test_render_findings_includes_grounded_chart_insight() -> None:
    rendered = _render_findings(
        {
            "charts": [
                {
                    "title": "chart",
                    "data_points": [],
                    "insights": [
                        {
                            "scope": "all visible entries",
                            "best": {"group": "configuration two", "series": "series two", "value": "value two"},
                            "comparison": "series two is higher than series one.",
                        }
                    ],
                }
            ]
        }
    )

    assert "chart insight: scope=all visible entries; best=configuration two / series two / value two" in rendered
