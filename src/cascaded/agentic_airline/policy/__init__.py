# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Deterministic airline policy.

Fare rules live in code here — never in prompts.  Tools call into this
package; the LLM never free-forms a fare or change fee.
"""
