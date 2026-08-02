"""Plan feature flags — STORED on restaurants; plan is a write-time PRESET only.

Read path: always return the four stored booleans. Never recompute from plan
on read (overrides must survive).

Write path: apply_plan_preset(plan) returns the four defaults for that plan.
Used only when a superadmin assigns a plan (see superadmin_service.update_restaurant
precedence: plan preset first, then explicit bool overrides in the same request).

Presets:
  basic   -> order off, call-waiter off, ar off, qr off
  starter -> order on,  call-waiter on,  ar off, qr off
  custom  -> order on,  call-waiter on,  ar on,  qr on
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from fastapi import HTTPException, status

from app.models.enums import RestaurantPlan
from app.models.restaurant import Restaurant
from app.services.order_state import OrderError


@dataclass(frozen=True, slots=True)
class FeatureFlags:
    """The four STORED restaurant feature flags (source of truth)."""

    order_enabled: bool
    call_waiter_enabled: bool
    ar_enabled: bool
    qr_pay_enabled: bool


class PlanPreset(TypedDict):
    order_enabled: bool
    call_waiter_enabled: bool
    ar_enabled: bool
    qr_pay_enabled: bool


def apply_plan_preset(plan: RestaurantPlan | str) -> PlanPreset:
    """Defaults written when a plan is assigned. Never used on read."""
    value = plan.value if isinstance(plan, RestaurantPlan) else plan
    if value == RestaurantPlan.BASIC.value:
        return {
            "order_enabled": False,
            "call_waiter_enabled": False,
            "ar_enabled": False,
            "qr_pay_enabled": False,
        }
    if value == RestaurantPlan.STARTER.value:
        return {
            "order_enabled": True,
            "call_waiter_enabled": True,
            "ar_enabled": False,
            "qr_pay_enabled": False,
        }
    # custom (and any unknown → treat as full)
    return {
        "order_enabled": True,
        "call_waiter_enabled": True,
        "ar_enabled": True,
        "qr_pay_enabled": True,
    }


def stored_features(restaurant: Restaurant) -> FeatureFlags:
    """Read the four STORED columns. Do not consult plan."""
    return FeatureFlags(
        order_enabled=bool(restaurant.order_enabled),
        call_waiter_enabled=bool(restaurant.call_waiter_enabled),
        ar_enabled=bool(restaurant.ar_enabled),
        qr_pay_enabled=bool(restaurant.qr_pay_enabled),
    )


# Back-compat alias used during the refactor; prefer stored_features.
def effective_features(restaurant: Restaurant) -> FeatureFlags:
    return stored_features(restaurant)


def require_order_enabled(restaurant: Restaurant) -> None:
    if not restaurant.order_enabled:
        raise OrderError(
            "Ordering is not enabled for this restaurant",
            status_code=403,
        )


def require_call_waiter_enabled(restaurant: Restaurant) -> None:
    if not restaurant.call_waiter_enabled:
        raise OrderError(
            "Call waiter is not enabled for this restaurant",
            status_code=403,
        )


def require_ar_enabled(restaurant: Restaurant) -> None:
    if not restaurant.ar_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AR is not enabled for this restaurant",
        )


def require_qr_pay_enabled(restaurant: Restaurant) -> None:
    if not restaurant.qr_pay_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="QR gateway payment is not enabled for this restaurant",
        )
