import logging
import uuid

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .agent import run_chat_agent
from .chat_history import (
    delete_session_chat_history,
    get_session_chat_history,
    save_chat_message,
)
from .serializers import ChatHistoryQuerySerializer, ChatRequestSerializer

logger = logging.getLogger(__name__)

# How many prior turns to pull from MongoDB as conversation context for the LLM.
CHAT_HISTORY_CONTEXT_LIMIT = 20

# Persisted (and returned) when the agent call fails in a way we didn't
# specifically anticipate — e.g. an unhandled exception from the Groq
# client — so the user gets a graceful reply instead of a raw 500, and the
# transcript still records that the turn happened.
GENERIC_FAILURE_MESSAGE = (
    "The server is experiencing high traffic. Please try again shortly."
)


def _restore_session_context(
    state: dict, loan_request_id: int | None, history: list[dict]
) -> tuple[dict, int | None]:
    """Fills gaps in the client-sent turn context from the stored transcript.

    The client normally round-trips `state` and `loan_request_id` itself, but
    a follow-up sent without them (a fresh tab, another client, a dropped
    field) would otherwise reach the agent with no active loan request and
    restart slot-filling. Every assistant turn is saved with the slot state
    and `loan_request_id` known at that point (see `save_chat_message`), so
    the most recent one is the session's server-side source of truth.

    Args:
        state: The slot-filling state sent by the client (may be empty).
        loan_request_id: The LoanRequest PK sent by the client, if any.
        history: This session's prior turns, oldest first, as returned by
            `get_session_chat_history`.

    Returns:
        `(state, loan_request_id)` — values the client did send always win;
        only slots it left unset are taken from the transcript.
    """
    last_slots = next(
        (
            turn["slots_captured"]
            for turn in reversed(history)
            if turn.get("role") == "assistant" and turn.get("slots_captured")
        ),
        None,
    )
    if not last_slots:
        return state, loan_request_id

    stored_state = {
        key: value for key, value in last_slots.items() if key != "loan_request_id"
    }
    sent_state = {key: value for key, value in state.items() if value is not None}
    if loan_request_id is None:
        loan_request_id = last_slots.get("loan_request_id")
    return {**stored_state, **sent_state}, loan_request_id


class ChatAPIView(APIView):
    """POST /api/chat/ — runs one turn of the MCP-backed chatbot agent loop.

    A single, non-streaming JSON request/response — the full reply is
    computed (including any MCP tool calls) before the response is sent.
    See `mcp_server.agent.run_chat_agent` for the underlying turn contract.

    Conversation history is not sent by the client — it's persisted in
    MongoDB per `session_id` and fetched here before each turn, so it
    survives page reloads and server restarts. The same transcript also
    backfills `state`/`loan_request_id` when the client omits them (see
    `_restore_session_context`), so a follow-up always reaches the agent
    with the session's active loan request.

    Response body (200 OK) on success:
        {"reply": "...",
         "tool_calls": [...],
         "state": {...},
         "loan_request_id": int | null,
         "session_id": "...",
         "report": {"kpis": {"requested_amount": float, "monthly_income": float,
                              "tenure": int, "dti_ratio": str,
                              "eligibility_status": "Eligible"|"Not Eligible"},
                    "policy_warnings": [{"title": str, "description": str,
                                          "level": "amber"|"red"}, ...],
                    "bank_recommendations": [{"bank_name": str, "loan_type": str,
                                               "monthly_installment": float,
                                               "interest_rate": float,
                                               "shariah_compliant": bool,
                                               "apply_url": str}, ...],
                    "strategic_steps": [str, ...],
                    "raw_markdown": str} | null}
        -- report is null unless the Executive Financial Report was
        rendered this turn (see PredictiveBankAgent.build_structured_report).
        Every field inside `report` is always concretely populated (never
        null) on the turn it's present. `reply` is always clean,
        consumer-facing text — see `run_chat_agent`/`_clean_reply_text`.

    On failure, a 503 with {"detail": "..."} instead. Without a valid JWT
    (`Authorization: Bearer <access token>`), a 401.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session_id = serializer.validated_data["session_id"] or str(uuid.uuid4())
        message = serializer.validated_data["message"]
        user = request.user
        chat_user_id = user.id
        state = serializer.validated_data["state"]
        loan_request_id = serializer.validated_data["loan_request_id"]

        # Fetched before the user's turn is saved so it doesn't include this
        # message twice, but the save itself happens immediately — before the
        # Groq call — so the prompt is durably logged even if that call
        # never returns.
        prior_history = get_session_chat_history(
            session_id, chat_user_id, limit=CHAT_HISTORY_CONTEXT_LIMIT
        )
        save_chat_message(session_id, chat_user_id, "user", message)
        state, loan_request_id = _restore_session_context(
            state, loan_request_id, prior_history
        )

        try:
            result = run_chat_agent(
                message, prior_history, state, user, loan_request_id, session_id
            )
        except RuntimeError as exc:
            # Persist the assistant's side of this turn even on failure —
            # every user/assistant pair must land in `chat_logs`, error
            # replies included, or the transcript silently drops a turn.
            error_message = str(exc)
            save_chat_message(session_id, chat_user_id, "assistant", error_message)
            return Response(
                {"detail": error_message}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception:
            # Any other failure (network blip, an unhandled Groq client
            # error, etc.) must still leave a matching assistant row behind
            # instead of dropping the turn on an unhandled 500.
            logger.exception(
                "Unhandled error running chat agent for session %s", session_id
            )
            save_chat_message(
                session_id, chat_user_id, "assistant", GENERIC_FAILURE_MESSAGE
            )
            return Response(
                {"detail": GENERIC_FAILURE_MESSAGE},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # loan_request_id rides along in slots_captured so a reloaded session
        # (see ChatHistoryAPIView) can recover it and avoid a duplicate save.
        assistant_metadata = {
            **result["state"],
            "loan_request_id": result["loan_request_id"],
        }
        save_chat_message(
            session_id,
            chat_user_id,
            "assistant",
            result["reply"],
            metadata=assistant_metadata,
        )

        return Response(
            {
                "reply": result["reply"],
                "tool_calls": result["tool_calls"],
                "state": result["state"],
                "loan_request_id": result["loan_request_id"],
                "session_id": session_id,
                "report": result["report"],
            },
            status=status.HTTP_200_OK,
        )


class ChatHistoryAPIView(APIView):
    """GET /api/chat/history/?session_id=XYZ — reloads a previous conversation.

    Scoped to the authenticated user (`request.user.id`, from the JWT) so a
    session id alone is never enough to read someone else's transcript.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        query = ChatHistoryQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)

        session_id = query.validated_data["session_id"]
        messages = get_session_chat_history(
            session_id, request.user.id, limit=query.validated_data["limit"]
        )

        return Response(
            {"session_id": session_id, "messages": messages}, status=status.HTTP_200_OK
        )


class ChatSessionAPIView(APIView):
    """DELETE /api/chat/history/<session_id>/ — permanently deletes one session's transcript.

    Scoped to the authenticated user (`request.user.id`, from the JWT) so a
    session id alone is never enough to delete someone else's transcript.
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, session_id, *args, **kwargs):
        deleted_count = delete_session_chat_history(session_id, request.user.id)

        return Response(
            {"success": True, "session_id": session_id, "deleted_count": deleted_count},
            status=status.HTTP_200_OK,
        )
