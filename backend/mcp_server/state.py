"""Structured slot-filling state for the loan discovery chat agent.

`ChatAPIView` is stateless per request, so the caller round-trips this dict
each turn: the previous response's `state` becomes the next request's `state`.
This keeps the slot values machine-readable and authoritative, independent of
whatever the LLM may or may not recall from raw conversation history.
"""

from typing import TypedDict


class LoanDiscoveryState(TypedDict, total=False):
    loan_type: str | None
    required_amount: float | None
    monthly_income: float | None
    is_islamic: bool | None
    tenure_years: int | None


REQUIRED_SLOTS = (
    "loan_type",
    "required_amount",
    "monthly_income",
    "is_islamic",
    "tenure_years",
)


def empty_state() -> LoanDiscoveryState:
    return {slot: None for slot in REQUIRED_SLOTS}


def normalize_state(state: dict | None) -> LoanDiscoveryState:
    """Whitelists a caller-supplied (untrusted) state dict onto the known schema."""
    normalized = empty_state()
    for slot in REQUIRED_SLOTS:
        if state and state.get(slot) is not None:
            normalized[slot] = state[slot]
    return normalized


def missing_slots(state: LoanDiscoveryState) -> list[str]:
    return [slot for slot in REQUIRED_SLOTS if state.get(slot) is None]
