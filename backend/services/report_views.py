"""GET /api/reports/<loan_request_id>/ — the structured, DB-driven Executive
Financial Report for one saved LoanRequest.

Pure DB-to-JSON, same non-LLM `PredictiveBankAgent` scorer as the PDF export
(`services.pdf_views`) — no Groq/LangGraph call is made anywhere on this
path. This is what makes a report durable: reloading it days later, or on a
different device, returns the exact same KPI cards, policy warnings, and
bank recommendations the chat turn first generated, instead of depending on
a browser's local cache that can be cleared or never synced elsewhere.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from users.models import LoanRequest

from .report_data import (
    accessible_loan_requests,
    build_report_for_loan_request,
    can_access_loan_request,
    display_loan_type,
)


@api_view(["GET"])
@permission_classes([AllowAny])
def get_loan_report(request, loan_request_id: int):
    """Returns the full structured report for one LoanRequest:

        {"loan_request_id": int, "loan_type": str, "is_islamic": bool,
         "kpis": {...}, "policy_warnings": [...],
         "bank_recommendations": [...], "strategic_steps": [...],
         "raw_markdown": str}

    Every field is always concretely populated — see
    `PredictiveBankAgent.build_structured_report`. 404 if the id doesn't
    exist, or belongs to another authenticated user's account (scoped like
    `services.pdf_views.export_policy_report_pdf`).
    """
    try:
        loan_request = LoanRequest.objects.get(id=loan_request_id)
    except LoanRequest.DoesNotExist:
        return Response(
            {"detail": "Loan request not found."}, status=status.HTTP_404_NOT_FOUND
        )

    if not can_access_loan_request(loan_request, request):
        return Response(
            {"detail": "Loan request not found."}, status=status.HTTP_404_NOT_FOUND
        )

    report = build_report_for_loan_request(loan_request)

    return Response(
        {
            "loan_request_id": loan_request.id,
            "loan_type": display_loan_type(loan_request),
            "is_islamic": loan_request.is_islamic,
            **report,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def list_reports(request):
    """GET /api/reports/?chat_id=<session_id> — lists structured reports.

    With `chat_id` (the chat's `session_id`, see `mcp_server.api.ChatAPIView`),
    scoped to ONLY the reports generated inside that one chat session —
    switching chats must never leak another chat's reports into the active
    one. Without it, returns the caller's full historical report list
    (requires authentication — a guest has no other identity to scope an
    unfiltered list to).

    Access is otherwise scoped exactly like `get_loan_report`/
    `can_access_loan_request`: an authenticated caller only ever sees their
    own rows (plus guest rows, which stay open to anyone), never another
    user's.

    Response body (200 OK):
        {"chat_id": str | null, "count": int,
         "results": [{"loan_request_id": int, "session_id": str | null,
                       "loan_type": str, "is_islamic": bool, "status": str,
                       "created_at": str, "kpis": {...}, "policy_warnings": [...],
                       "bank_recommendations": [...], "strategic_steps": [...],
                       "raw_markdown": str}, ...]}
    """
    chat_id = request.query_params.get("chat_id")
    queryset = accessible_loan_requests(request)

    if chat_id:
        queryset = queryset.filter(chat_session_id=chat_id)
    elif not request.user.is_authenticated:
        return Response(
            {"detail": "Authentication required to list reports without a chat_id."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    results = [
        {
            "loan_request_id": loan_request.id,
            "session_id": loan_request.chat_session_id,
            "loan_type": display_loan_type(loan_request),
            "is_islamic": loan_request.is_islamic,
            "status": loan_request.status,
            "created_at": loan_request.created_at,
            **build_report_for_loan_request(loan_request),
        }
        for loan_request in queryset.order_by("-created_at")
    ]

    return Response(
        {"chat_id": chat_id, "count": len(results), "results": results},
        status=status.HTTP_200_OK,
    )
