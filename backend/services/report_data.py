"""Shared DB-driven report-building logic for a saved `users.models.LoanRequest`.

Both `services.pdf_views` (PDF export) and `services.report_views` (the JSON
`/api/reports/<id>/` endpoint) need to re-rank the same LoanPolicy catalog
rows against the same LoanRequest the same way, and both need to guard
"can this caller see this request" the same way — that logic lives here once
instead of twice so the two views can never quietly drift apart.
"""

from banks.models import LoanCategory, LoanPolicy
from django.db.models import Q, QuerySet
from users.models import LoanRequest

from .financial_calculator import PredictiveBankAgent

# users.models.LoanRequest.loan_type (lowercase choices) -> banks.models.LoanCategory
# (also the capitalized "Personal"/"Home"/"Vehicle" convention PredictiveBankAgent
# and the chat agent's own slot state use — see LoanRequestType/LoanCategory).
_REQUEST_TYPE_TO_CATEGORY = {
    "personal": LoanCategory.PERSONAL,
    "home": LoanCategory.HOME,
    "auto": LoanCategory.VEHICLE,
}

# Max candidate policies fetched per request, matching mcp_server.server's
# own search_loans cap so a DB-only rebuild never balloons past what the chat
# agent itself would ever have shown for one query.
_MAX_POLICIES = 20


def display_loan_type(loan_request: LoanRequest) -> str | None:
    """The capitalized "Personal"/"Home"/"Vehicle" form PredictiveBankAgent
    expects, from a LoanRequest's stored lowercase `loan_type` choice."""
    category = _REQUEST_TYPE_TO_CATEGORY.get(loan_request.loan_type)
    return category.value if category else None


def policies_for_loan_request(loan_request: LoanRequest) -> list[dict]:
    """Candidate LoanPolicy rows for this request, as plain dicts.

    Mirrors `mcp_server.server._search_loans_sync`'s filtering/shape so a
    DB-only rebuild (PDF export, the JSON reports endpoint) always matches
    what the chat agent would have shown, minus the max_dti filter (these
    views show all catalog options for the loan type/amount/preference, not
    just ones that already pass DTI).
    """
    category = _REQUEST_TYPE_TO_CATEGORY.get(loan_request.loan_type)
    if category is None:
        return []

    queryset = LoanPolicy.objects.select_related("bank").filter(
        loan_type=category,
        max_loan_amount__gte=loan_request.required_amount,
    )
    if loan_request.is_islamic:
        queryset = queryset.filter(is_islamic=True)

    return [
        {
            "bank_name": policy.bank.name,
            "is_islamic": policy.is_islamic,
            "profit_rate": float(policy.profit_rate),
            "min_income": float(policy.min_income),
            "max_dti_percentage": float(policy.max_dti_percentage),
            "min_downpayment_percentage": float(policy.min_downpayment_percentage),
            "max_tenure_years": policy.max_tenure_years,
            "main_page_url": policy.bank.main_page_url,
        }
        for policy in queryset.order_by("profit_rate")[:_MAX_POLICIES]
    ]


def can_access_loan_request(loan_request: LoanRequest, request) -> bool:
    """An authenticated caller may only access their own loan request; a
    guest (user-less) request stays open to anyone, matching how guest chat
    sessions work elsewhere in this API (see mcp_server.api)."""
    if loan_request.user_id is None:
        return True
    requester = request.user if request.user.is_authenticated else None
    return requester is not None and requester.id == loan_request.user_id


def accessible_loan_requests(request) -> QuerySet[LoanRequest]:
    """Every `LoanRequest` this caller may see: their own rows plus any
    guest (user-less) ones — the queryset form of `can_access_loan_request`,
    for list endpoints (see `services.report_views.list_reports`)."""
    if request.user.is_authenticated:
        return LoanRequest.objects.filter(
            Q(user_id__isnull=True) | Q(user_id=request.user.id)
        )
    return LoanRequest.objects.filter(user_id__isnull=True)


def build_report_for_loan_request(loan_request: LoanRequest) -> dict:
    """Builds the full structured report (kpis/policy_warnings/
    bank_recommendations/strategic_steps/raw_markdown) purely from durable
    Postgres/SQLite rows — no LLM/Groq call, so it always returns the same
    result for the same request, whether that's seconds or months after the
    chat turn that first generated it (unlike the frontend's old
    browser-local Reports index, which is lost if that browser's storage is
    cleared).
    """
    user_profile = {
        "monthly_income": float(loan_request.monthly_income),
        "required_amount": float(loan_request.required_amount),
        "tenure_years": loan_request.desired_tenure_years,
        "is_islamic": loan_request.is_islamic,
        "loan_type": display_loan_type(loan_request),
    }
    policies = policies_for_loan_request(loan_request)
    agent = PredictiveBankAgent()
    ranked_policies = agent.evaluate_and_rank(policies, user_profile)
    return agent.build_structured_report(ranked_policies, user_profile)
