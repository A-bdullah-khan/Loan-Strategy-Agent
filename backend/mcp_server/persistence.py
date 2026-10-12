"""Auto-saves completed chat slot-filling state as a `users.models.LoanRequest`.

This is a deterministic side effect of slot completion, not something the LLM
decides to do — it fires the moment `state.missing_slots()` is empty, so the
chat transcript is always backed by a durable record regardless of whether the
model goes on to call search_loans/calculate_user_eligibility in the same turn.
"""

from asgiref.sync import sync_to_async

from .state import LoanDiscoveryState

_LOAN_TYPE_MAP = {
    "personal": "personal",
    "home": "home",
    "auto": "auto",
    "vehicle": "auto",  # search_loans-facing alias for the same slot value
}


def _create_loan_request_sync(
    state: LoanDiscoveryState, user, session_id: str | None
) -> int | None:
    from users.models import (
        ChatSession,
        LoanRequest,
        LoanRequestStatus,
        LoanRequestType,
    )

    loan_type = _LOAN_TYPE_MAP.get(str(state["loan_type"]).strip().lower())
    if loan_type is None:
        return None

    # Lazily creates the session's Postgres-side anchor row the moment it
    # first needs one — a session that never completes a loan request never
    # gets a ChatSession row at all. get_or_create rather than create: a
    # returning session (loan_request_id already known, e.g. a later
    # update_loan_state edit re-completing the slots) must reuse the same
    # row, not violate the id's primary-key uniqueness.
    chat_session = None
    if session_id:
        chat_session, _ = ChatSession.objects.get_or_create(
            id=session_id, defaults={"user": user}
        )

    loan_request = LoanRequest.objects.create(
        user=user,
        chat_session=chat_session,
        loan_type=LoanRequestType(loan_type),
        required_amount=state["required_amount"],
        monthly_income=state["monthly_income"],
        is_islamic=bool(state["is_islamic"]),
        desired_tenure_years=int(state["tenure_years"]),
        status=LoanRequestStatus.ANALYZED,
    )
    return loan_request.id


async def save_loan_request(
    state: LoanDiscoveryState, user, session_id: str | None = None
) -> int | None:
    """Creates a LoanRequest row from a fully-filled slot state.

    Args:
        state: A slot state with every field already known (caller must check
            `mcp_server.state.missing_slots(state)` is empty before calling).
        user: The authenticated `users.models.User`, or None for a guest
            session — LoanRequest.user is nullable to support that.
        session_id: The chat session's UUID (see `mcp_server.api.ChatAPIView`)
            this turn belongs to — the row is FK'd to (a lazily-created)
            `users.models.ChatSession` with this id, so `/api/reports/` can
            later scope its list to just this chat, and deleting the chat
            session cascades to delete this row too.

    Returns:
        The new LoanRequest's primary key, or None if loan_type didn't match
        a recognized value.
    """
    return await sync_to_async(_create_loan_request_sync, thread_sensitive=True)(
        state, user, session_id
    )
