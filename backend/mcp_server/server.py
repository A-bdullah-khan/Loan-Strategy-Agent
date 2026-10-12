"""FastMCP server exposing loan-domain tools to the chatbot agent.

Tools defined here are queried in-process by `mcp_server.agent.run_chat_agent`
via the standard `FastMCP.call_tool` / `list_tools` API, so they double as the
authoritative MCP tool contract and the chatbot's data-access layer.
"""

from asgiref.sync import sync_to_async
from banks.models import Bank, LoanPolicy
from django.db.models import Avg, Max
from mcp.server.fastmcp import FastMCP

# Used only when the catalog has zero policies for a loan_type (an
# unsupported/misspelled value) — the average profit_rate query below
# otherwise always wins, so this is a last-resort stand-in, not a tuned
# market rate.
DEFAULT_PROFIT_RATE_PERCENTAGE = 18.0


def _average_profit_rate_sync(loan_type: str) -> float:
    average = LoanPolicy.objects.filter(loan_type=loan_type).aggregate(
        Avg("profit_rate")
    )["profit_rate__avg"]
    return float(average) if average is not None else DEFAULT_PROFIT_RATE_PERCENTAGE


def _estimate_monthly_installment(
    principal: float, annual_profit_rate_pct: float, tenure_years: float
) -> float:
    """Standard reducing-balance loan amortization formula.

    Replaces a naive `principal / months` approximation, which ignores the
    bank's profit rate entirely and therefore understates both the true
    installment and the DTI ratio computed from it.
    """
    months = max(tenure_years, 1) * 12
    monthly_rate = annual_profit_rate_pct / 100 / 12
    if monthly_rate == 0:
        return principal / months
    growth = (1 + monthly_rate) ** months
    return principal * monthly_rate * growth / (growth - 1)


mcp_server = FastMCP(
    name="loan-strategy-agent",
    instructions=(
        "Tools for the Loan Strategy Agent chatbot: search active bank loan "
        "policies, check a borrower's State Bank of Pakistan (SBP) 50% "
        "debt-to-income eligibility, and look up partner bank details. Always "
        "call a tool for live data instead of guessing rates, limits, or URLs."
    ),
)


def _search_loans_sync(
    loan_type: str,
    amount: float,
    is_islamic: bool | None,
    max_dti: float | None,
) -> dict:
    queryset = LoanPolicy.objects.select_related("bank").filter(
        loan_type=loan_type,
        max_loan_amount__gte=amount,
    )
    if is_islamic is not None:
        queryset = queryset.filter(is_islamic=is_islamic)
    if max_dti is not None:
        queryset = queryset.filter(max_dti_percentage__gte=max_dti)

    policies = [
        {
            "id": policy.id,
            "bank_id": policy.bank_id,
            "bank_name": policy.bank.name,
            "loan_type": policy.loan_type,
            "is_islamic": policy.is_islamic,
            "max_loan_amount": float(policy.max_loan_amount),
            "profit_rate": float(policy.profit_rate),
            "max_dti_percentage": float(policy.max_dti_percentage),
            "min_income": float(policy.min_income),
            "min_downpayment_percentage": float(policy.min_downpayment_percentage),
            "max_tenure_years": policy.max_tenure_years,
            "min_age": policy.min_age,
            "max_age": policy.max_age,
            # Carried straight through evaluate_and_rank's `{**policy, ...}`
            # spread so PredictiveBankAgent.build_bank_recommendations always
            # has a concrete `apply_url` to report, never a null one.
            "main_page_url": policy.bank.main_page_url,
        }
        for policy in queryset.order_by("profit_rate")[:20]
    ]

    result = {"count": len(policies), "policies": policies}

    if not policies:
        # Zero matches could be because the requested amount exceeds every
        # policy's ceiling, or because of the DTI/Islamic filters — surface
        # the real catalog ceiling (ignoring amount/max_dti) so the caller
        # can tell which one it is and cite the actual PKR figure instead of
        # a guessed/placeholder one.
        ceiling_queryset = LoanPolicy.objects.filter(loan_type=loan_type)
        if is_islamic is not None:
            ceiling_queryset = ceiling_queryset.filter(is_islamic=is_islamic)
        catalog_max_amount = ceiling_queryset.aggregate(Max("max_loan_amount"))[
            "max_loan_amount__max"
        ]
        result["catalog_max_amount"] = (
            float(catalog_max_amount) if catalog_max_amount is not None else None
        )

    return result


@mcp_server.tool()
async def search_loans(
    loan_type: str,
    amount: float,
    is_islamic: bool | None = None,
    max_dti: float | None = None,
) -> dict:
    """Search active bank loan policies matching a borrower's requirements.

    Args:
        loan_type: One of "Personal", "Vehicle", "Home" (banks.models.LoanCategory).
        amount: Desired loan amount in PKR. Only policies whose max_loan_amount
            can cover this amount are returned.
        is_islamic: Restrict to Islamic (True) or conventional (False) policies.
            Omit to include both.
        max_dti: The borrower's own projected debt-to-income ratio, as a
            percentage (e.g. 35 for 35%). Only policies whose bank-allowed
            max_dti_percentage is at least this value are returned, since a
            lower bank ceiling would reject the borrower.

    Returns:
        A dict with "count" and "policies" (each policy carrying its bank name,
        rate, tenure, and DTI/amount limits), ordered by lowest profit rate first.
        When "policies" is empty, also includes "catalog_max_amount" — the
        highest max_loan_amount offered anywhere in the catalog for this
        loan_type/is_islamic combination (ignoring amount/max_dti), or None if
        no bank offers this loan_type/is_islamic combination at all.
    """
    # Django's ORM refuses sync DB access from inside a running event loop,
    # so the query runs on a worker thread via sync_to_async.
    return await sync_to_async(_search_loans_sync, thread_sensitive=True)(
        loan_type, amount, is_islamic, max_dti
    )


@mcp_server.tool()
def update_loan_state(
    loan_type: str | None = None,
    required_amount: float | None = None,
    monthly_income: float | None = None,
    is_islamic: bool | None = None,
    tenure_years: int | None = None,
) -> dict:
    """Record loan-discovery slot values extracted from the user's latest message.

    Call this as soon as the user states any of these fields, even one at a
    time — you do not need every field at once, and you should not guess a
    value the user did not actually state.

    Args:
        loan_type: One of "Personal", "Home", "Vehicle".
        required_amount: Desired loan amount in PKR (e.g. "10 lakh" -> 1000000).
        monthly_income: Borrower's gross monthly income in PKR.
        is_islamic: True if the user wants a Shariah-compliant (Islamic) loan,
            False if conventional.
        tenure_years: Desired loan tenure in years.

    Returns:
        Only the fields that were actually provided this call (non-null),
        which the caller merges into the running slot-filling state.
    """
    # Normalize any lingering "Auto"/"Car" phrasing the model might still
    # extract to the single canonical "Vehicle" used across the catalog.
    if loan_type in ("Auto", "Car", "Vehicle"):
        loan_type = "Vehicle"

    updates = {
        "loan_type": loan_type,
        "required_amount": required_amount,
        "monthly_income": monthly_income,
        "is_islamic": is_islamic,
        "tenure_years": tenure_years,
    }
    return {key: value for key, value in updates.items() if value is not None}


@mcp_server.tool()
async def calculate_user_eligibility(
    monthly_income: float,
    required_amount: float,
    tenure_years: float,
    loan_type: str,
    existing_loans: float = 0.0,
) -> dict:
    """Validate a borrower's request against the SBP 50% debt-to-income (DTI) rule.

    The State Bank of Pakistan caps a borrower's total monthly debt obligations
    (existing installments plus the new loan's installment) at 50% of gross
    monthly income. The new loan's own monthly installment is computed here
    (reducing-balance amortization against the catalog's average profit_rate
    for loan_type) rather than trusting a caller-supplied estimate, since a
    naive interest-free guess understates both the installment and the DTI
    ratio.

    Args:
        monthly_income: Borrower's gross monthly income, in PKR.
        required_amount: The new loan's requested principal, in PKR.
        tenure_years: The new loan's requested tenure, in years.
        loan_type: One of "Personal", "Vehicle", "Home" — used to look up a
            representative profit_rate for the installment estimate.
        existing_loans: Borrower's total existing monthly loan/debt obligations
            (sum of all current installments), in PKR. Defaults to 0.

    Returns:
        A dict with the computed monthly_installment, profit_rate_used,
        dti_percentage, is_eligible flag, the SBP max_allowed_percentage (50),
        and remaining_capacity (PKR of installment headroom available under
        the cap before the new loan is added). Every numeric field is always
        a concrete float — never null — so a caller never has to
        special-case missing data.
    """
    max_allowed_percentage = 50.0

    profit_rate = await sync_to_async(_average_profit_rate_sync, thread_sensitive=True)(
        loan_type
    )
    monthly_installment = round(
        _estimate_monthly_installment(required_amount, profit_rate, tenure_years), 2
    )

    if monthly_income <= 0:
        return {
            "is_eligible": False,
            "dti_percentage": 0.0,
            "monthly_installment": monthly_installment,
            "profit_rate_used": profit_rate,
            "max_allowed_percentage": max_allowed_percentage,
            "remaining_capacity": 0.0,
            "reason": "Monthly income must be greater than zero.",
        }

    total_obligations = existing_loans + monthly_installment
    dti_percentage = round((total_obligations / monthly_income) * 100, 2)
    remaining_capacity = round(
        max(monthly_income * (max_allowed_percentage / 100) - existing_loans, 0), 2
    )
    is_eligible = dti_percentage <= max_allowed_percentage

    return {
        "is_eligible": is_eligible,
        "dti_percentage": dti_percentage,
        "monthly_installment": monthly_installment,
        "profit_rate_used": profit_rate,
        "max_allowed_percentage": max_allowed_percentage,
        "remaining_capacity": remaining_capacity,
        "reason": (
            "Within the SBP 50% DTI limit."
            if is_eligible
            else "Exceeds the SBP 50% DTI limit."
        ),
    }


def _get_bank_details_sync(bank_id: int) -> dict:
    try:
        bank = Bank.objects.prefetch_related("loan_policies").get(id=bank_id)
    except Bank.DoesNotExist:
        return {"found": False, "bank_id": bank_id}

    return {
        "found": True,
        "id": bank.id,
        "name": bank.name,
        "is_islamic": bank.is_islamic,
        "main_page_url": bank.main_page_url,
        "loan_policies": [
            {
                "id": policy.id,
                "loan_type": policy.loan_type,
                "profit_rate": float(policy.profit_rate),
                "max_loan_amount": float(policy.max_loan_amount),
                "max_tenure_years": policy.max_tenure_years,
            }
            for policy in bank.loan_policies.all()
        ],
    }


@mcp_server.tool()
async def get_bank_details(bank_id: int) -> dict:
    """Fetch a partner bank's profile, including its official website and loan policies.

    Args:
        bank_id: Primary key of the banks.models.Bank record.

    Returns:
        A dict with the bank's name, is_islamic flag, main_page_url, and a
        summary of each of its loan policies. Returns {"found": False} if no
        bank matches bank_id.
    """
    return await sync_to_async(_get_bank_details_sync, thread_sensitive=True)(bank_id)
