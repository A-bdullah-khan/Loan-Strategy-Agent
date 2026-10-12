"""MongoDB-backed persistent chat history for the loan strategy chatbot.

Complements `mcp_server.state.LoanDiscoveryState` (the structured slot-filling
state, which round-trips through the API each turn) with a durable transcript
per session, keyed by `session_id`, so a returning user's conversation
survives across requests, page reloads, and server restarts — something the
stateless Django view alone cannot provide.

Document schema (collection `chat_logs`):
    session_id: str (UUID)
    user_id: int — the Django PK of the authenticated user who owns the
        session (see mcp_server.api). Documents written before JWT auth may
        instead hold an email string or None; those match no user's queries.
    role: 'user' | 'assistant'
    content: str
    slots_captured: dict     — the slot-filling state known as of this message
    timestamp: datetime (UTC, ISODate in Mongo)
"""

from datetime import UTC, datetime

from config.mongodb import get_mongo_db

COLLECTION_NAME = "chat_logs"

# Fields returned to callers; excludes Mongo's own `_id` (not JSON-safe by default).
_PROJECTION = {
    "_id": 0,
    "session_id": 1,
    "user_id": 1,
    "role": 1,
    "content": 1,
    "slots_captured": 1,
    "timestamp": 1,
}


def _collection():
    return get_mongo_db()[COLLECTION_NAME]


def save_chat_message(
    session_id: str,
    user_id: int,
    sender: str,
    message: str,
    metadata: dict | None = None,
) -> None:
    """Persists one chat turn.

    Args:
        session_id: The conversation's session id (string UUID).
        user_id: The authenticated user's PK.
        sender: 'user' or 'assistant' — stored as the `role` field.
        message: The message text — stored as the `content` field.
        metadata: The slot-filling state known as of this message, stored as
            `slots_captured` (e.g. {"monthly_income": 150000, ...}).
    """
    _collection().insert_one(
        {
            "session_id": session_id,
            "user_id": user_id,
            "role": sender,
            "content": message,
            "slots_captured": metadata or {},
            "timestamp": datetime.now(UTC),
        }
    )


def get_session_chat_history(
    session_id: str, user_id: int, limit: int = 20
) -> list[dict]:
    """Returns up to `limit` most recent messages for one session, oldest first.

    Scoped to `user_id` (matching the `user_id` each message was saved under
    — see `save_chat_message`) so one user can never read another user's
    transcript by guessing/reusing a `session_id`.
    """
    # Sorted by _id, not timestamp: BSON datetimes only have millisecond
    # precision, so a user/assistant pair saved back-to-back can tie on
    # timestamp — ObjectId is monotonically increasing per insert and doesn't.
    docs = list(
        _collection()
        .find({"session_id": session_id, "user_id": user_id}, _PROJECTION)
        .sort("_id", -1)
        .limit(limit)
    )
    docs.reverse()
    return docs


def _delete_loan_requests_for_session(
    session_id: str, user_id: int | str | None
) -> int:
    """Purges every `users.models.LoanRequest` (i.e. report) generated in one
    chat session, alongside its Mongo transcript — a chat session and its
    reports must not outlive each other.

    Deletes the session's `ChatSession` row itself; every `LoanRequest` FK'd
    to it (`LoanRequest.chat_session`, `on_delete=CASCADE`) is removed by the
    database as part of the same delete, not by an application-level filter —
    a session with no completed report simply has no `ChatSession` row to
    begin with (see `mcp_server.persistence.save_loan_request`), so this is a
    no-op for it.

    `ChatSession.user` is a real Django user PK, or None on rows created
    before the chat API required authentication. An int `user_id` must match
    the row's owner; anything else only matches such a user-less session.
    """
    from users.models import ChatSession, LoanRequest

    queryset = ChatSession.objects.filter(id=session_id)
    queryset = (
        queryset.filter(user_id=user_id)
        if isinstance(user_id, int)
        else queryset.filter(user_id__isnull=True)
    )
    _, deletions_by_model = queryset.delete()
    return deletions_by_model.get(
        f"{LoanRequest._meta.app_label}.{LoanRequest.__name__}", 0
    )


def delete_session_chat_history(session_id: str, user_id: int) -> int:
    """Permanently deletes every message for one session, and every report
    (`LoanRequest`) generated within it. Returns the count of chat messages removed.

    Scoped to `user_id` (matching the `user_id` each message was saved under
    — see `save_chat_message`) so one user can never delete another user's
    transcript by guessing/reusing a `session_id`.
    """
    _delete_loan_requests_for_session(session_id, user_id)
    return (
        _collection()
        .delete_many({"session_id": session_id, "user_id": user_id})
        .deleted_count
    )


def get_user_chat_history(user_id: int, limit: int = 20) -> list[dict]:
    """Returns up to `limit` most recent messages across all of a user's sessions, oldest first."""
    docs = list(
        _collection()
        .find({"user_id": user_id}, _PROJECTION)
        .sort("_id", -1)
        .limit(limit)
    )
    docs.reverse()
    return docs
