# SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause

"""Fare-change-fee rules keyed on fare basis, cabin, and days-to-departure.

Tables are mock but shaped realistically so EVA scenarios exercise the
full rule surface.  Swap to YAML-loaded tables later without changing the
:func:`change_fee` signature.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

FareBasis = Literal["basic_economy", "nonrefundable", "refundable"]
Cabin = Literal["economy", "premium_economy", "business", "first"]
EliteTier = Literal["none", "silver", "gold", "platinum"]

_POLICY_REF = "FR-CHG-2024-01"

# Days-to-departure buckets, ordered by upper bound (exclusive).
_NONREFUNDABLE_FEE_BUCKETS: list[tuple[int, dict[Cabin, Decimal]]] = [
    (
        8,
        {
            "economy": Decimal("200"),
            "premium_economy": Decimal("250"),
            "business": Decimal("350"),
            "first": Decimal("500"),
        },
    ),
    (
        31,
        {
            "economy": Decimal("100"),
            "premium_economy": Decimal("150"),
            "business": Decimal("200"),
            "first": Decimal("300"),
        },
    ),
    (
        10_000,
        {
            "economy": Decimal("75"),
            "premium_economy": Decimal("100"),
            "business": Decimal("150"),
            "first": Decimal("250"),
        },
    ),
]


@dataclass(slots=True, frozen=True)
class FeeQuote:
    """Outcome of a change-fee lookup. Tool-serializable."""

    allowed: bool
    fee: Decimal
    policy_ref: str
    reason: str = ""


def change_fee(
    fare_basis: FareBasis,
    cabin: Cabin,
    days_to_departure: int,
    elite_tier: EliteTier = "none",
) -> FeeQuote:
    """Quote the change fee for a single ticket.

    ``basic_economy`` tickets are non-changeable (returns ``allowed=False``).
    ``refundable`` tickets always change for free.
    ``nonrefundable`` tickets follow the days-to-departure × cabin table,
    with platinum elites waived, gold elites discounted $100, and silver
    elites discounted $50 (both floored at $0).
    """
    if fare_basis == "basic_economy":
        return FeeQuote(
            allowed=False,
            fee=Decimal("0"),
            policy_ref=_POLICY_REF,
            reason="basic_economy fares are non-changeable",
        )

    if fare_basis == "refundable":
        return FeeQuote(allowed=True, fee=Decimal("0"), policy_ref=_POLICY_REF)

    if elite_tier == "platinum":
        return FeeQuote(allowed=True, fee=Decimal("0"), policy_ref=_POLICY_REF, reason="platinum waiver")

    base = _lookup_nonrefundable(cabin, days_to_departure)
    if elite_tier == "gold":
        base = max(Decimal("0"), base - Decimal("100"))
        return FeeQuote(allowed=True, fee=base, policy_ref=_POLICY_REF, reason="gold discount")
    if elite_tier == "silver":
        base = max(Decimal("0"), base - Decimal("50"))
        return FeeQuote(allowed=True, fee=base, policy_ref=_POLICY_REF, reason="silver discount")
    return FeeQuote(allowed=True, fee=base, policy_ref=_POLICY_REF)


def _lookup_nonrefundable(cabin: Cabin, days_to_departure: int) -> Decimal:
    """Lookup the nonrefundable fee for a cabin at a given days-to-departure bucket."""
    if days_to_departure < 0:
        raise ValueError(f"days_to_departure must be non-negative; got {days_to_departure}")
    for upper, fees in _NONREFUNDABLE_FEE_BUCKETS:
        if days_to_departure < upper:
            return fees[cabin]
    # Upper bound of 10_000 in the final bucket makes this unreachable for real dtd.
    raise ValueError(f"Unhandled days_to_departure={days_to_departure}")
