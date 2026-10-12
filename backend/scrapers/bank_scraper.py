"""Live scraper for every bank stored in the database.

Every bank's loan-policy data is derived from a single fetch of its
`Bank.main_page_url` — no per-category product-page URL is hardcoded
anywhere in this module, and no bank list is hardcoded either; banks come
from whatever `Bank` rows exist in the database, keyed by `main_page_url`.

Loan-policy figures are extracted entirely by
`agents.policy_crawler_agent.PolicyCrawlerAgent`, an LLM-driven extractor
run once per bank/loan-type pair against the page's visible text. Homepages
rarely publish granular loan figures directly (those normally live on
dedicated product pages), so in practice most fields still resolve to the
`FALLBACK_BASELINES` market estimate rather than a bank-confirmed number;
whatever the agent can extract takes precedence. The agent is entirely
best-effort — if it's unavailable (no Groq API key configured) or a call
fails, extraction silently falls back to `FALLBACK_BASELINES`.

Every fetch goes through a `requests.Session` with automatic retries
(`build_session`) so transient failures (rate-limiting, brief 5xx blips,
dropped connections) don't sink a bank outright, and every failure mode —
timeout, connection error, a failed agent call — is logged with enough
detail to tell them apart later. Extracted payloads are still validated
before persistence (see `scraper_service._validate_policy`) so a bad parse
never silently reaches the database.

This module only depends on the `BankDataSource` interface from
`scrapers.scraper_service`, so it plugs into `fetch_bank_loan_policies`
exactly like `MockBankDataSource` does.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

import requests
from agents.policy_crawler_agent import PolicyCrawlerAgent
from banks.models import Bank, LoanCategory
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from scrapers.scraper_service import (
    BankDataSource,
    MockBankDataSource,
    ScrapedBank,
    ScrapedLoanPolicy,
    fetch_bank_loan_policies,
)

logger = logging.getLogger(__name__)

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
REQUEST_TIMEOUT = 20

# Transient failures (rate-limiting, brief 5xx blips, dropped connections)
# are retried with backoff before a fetch is treated as failed; a 4xx other
# than 429 means the page itself is gone/forbidden and retrying won't help.
RETRY_CONFIG = Retry(
    total=3,
    backoff_factor=0.5,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=("GET",),
)


def build_session() -> requests.Session:
    """A `requests.Session` with automatic retries mounted for both schemes."""
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=RETRY_CONFIG)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# Every field a comparison tool needs. Any of these PolicyCrawlerAgent
# doesn't extract is filled from FALLBACK_BASELINES rather than leaving the
# bank/category out of the database.
POLICY_FIELDS = (
    "min_income",
    "max_loan_amount",
    "profit_rate",
    "max_tenure_years",
    "max_dti_percentage",
    "min_downpayment_percentage",
)

# Reuse the same representative per-category baselines MockBankDataSource
# seeds banks with, so a fallback figure here means the same thing
# everywhere in the database rather than introducing a second set of
# assumptions.
FALLBACK_BASELINES = MockBankDataSource.LOAN_TYPE_BASELINES

# Banks that don't offer a given loan category at all — the fallback
# generator must never invent a policy for these, no matter what the
# homepage does or doesn't say. Standard Chartered Pakistan has no auto/
# vehicle financing product, so it's excluded from LoanCategory.VEHICLE.
BANK_PRODUCT_OMISSIONS: dict[str, set[str]] = {
    "Standard Chartered": {LoanCategory.VEHICLE},
}


def _fetch_raw_html(url: str | None, session: requests.Session) -> str | None:
    """GET a page (with automatic retries via `session`) and return its raw
    HTML, tags and attributes intact.
    """
    if not url:
        logger.warning("Skipping fetch: no URL provided")
        return None
    try:
        response = session.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.Timeout:
        logger.error(
            "Timed out fetching %s after %ss (including retries)", url, REQUEST_TIMEOUT
        )
        return None
    except requests.ConnectionError as exc:
        logger.error("Connection failed while traversing to %s: %s", url, exc)
        return None
    except requests.RequestException as exc:
        logger.warning("Failed link traversal for %s: %s", url, exc)
        return None
    logger.debug("Fetched %s (%d bytes)", url, len(response.text))
    return response.text


def _visible_text(html: str) -> str:
    """The page's visible text, scripts/styles stripped."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(separator="\n")


# A real bank homepage carries thousands of characters of visible text. A
# bot-challenge interstitial served with HTTP 200 (e.g. BOP's Incapsula
# "Request unsuccessful" page) or an empty client-rendered shell carries
# next to none, so anything under this is treated as blocked rather than
# sent to the agent as if it were the bank's content.
MIN_VISIBLE_TEXT_CHARS = 200


def _has_readable_content(html: str) -> bool:
    """Whether `html` carries enough visible text to be a real page."""
    try:
        return len(_visible_text(html).strip()) >= MIN_VISIBLE_TEXT_CHARS
    except Exception as exc:
        logger.error("Could not extract visible text: %s", exc)
        return False


# Numeric fields PolicyCrawlerAgent may return, decimal-valued ones and the
# one int-valued one (`max_tenure_years`) coerced separately in `_agent_parse`.
_AGENT_DECIMAL_FIELDS = tuple(
    name for name in POLICY_FIELDS if name != "max_tenure_years"
)

# Lazily built, module-level so the Groq client isn't reconstructed for
# every bank/loan-type pair. `None` means "not built yet"; a bare `False`
# sentinel (distinct from a real agent instance) means construction already
# failed once (e.g. no GROQ_API_KEY configured) and shouldn't be retried
# for the rest of this process.
_policy_crawler_agent: PolicyCrawlerAgent | None | bool = None


def _get_policy_crawler_agent() -> PolicyCrawlerAgent | None:
    """Returns the shared `PolicyCrawlerAgent`, building it on first use.

    Construction fails when `GROQ_API_KEY` isn't configured; that's
    expected in some environments (local dev, CI) and is not fatal to
    scraping — it's logged once and every subsequent call returns `None` so
    `_agent_parse` transparently no-ops instead of raising per bank.
    """
    global _policy_crawler_agent
    if _policy_crawler_agent is False:
        return None
    if _policy_crawler_agent is None:
        try:
            _policy_crawler_agent = PolicyCrawlerAgent()
        except Exception:
            logger.exception(
                "PolicyCrawlerAgent unavailable — falling back to baselines only"
            )
            _policy_crawler_agent = False
            return None
    return _policy_crawler_agent


def _agent_parse(html: str, bank_name: str, loan_type: str) -> dict:
    """Runs `PolicyCrawlerAgent` over a bank's page content for one loan type.

    Called once per loan category — the agent is told which one to extract
    so it doesn't conflate, say, a Vehicle rate with a Personal one when a
    page mentions both.

    Returns only the non-null numeric fields the agent actually extracted,
    already converted to the types `_build_policy`/`ScrapedLoanPolicy`
    expect (`Decimal` for money/percentage fields, `int` for tenure), plus
    the agent's free-text `policy_notes` when it supplied one.
    Everything here is best-effort: an unavailable agent, a failed model
    call, or a non-numeric value in its response is logged and treated as
    "nothing extracted" rather than raised, so a live scrape never fails
    because the LLM extraction step did.
    """
    agent = _get_policy_crawler_agent()
    if agent is None:
        return {}

    try:
        text = _visible_text(html)
    except Exception as exc:
        logger.error(
            "Could not extract visible text for %s / %s: %s", bank_name, loan_type, exc
        )
        return {}

    extracted = agent.extract_policy(text, bank_name, loan_type)
    if not extracted:
        return {}

    fields: dict = {}
    for name in _AGENT_DECIMAL_FIELDS:
        value = extracted.get(name)
        if value is None:
            continue
        try:
            fields[name] = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            logger.warning(
                "PolicyCrawlerAgent returned non-numeric %s=%r for %s / %s; ignoring",
                name,
                value,
                bank_name,
                loan_type,
            )

    tenure = extracted.get("max_tenure_years")
    if tenure is not None:
        try:
            fields["max_tenure_years"] = int(tenure)
        except (ValueError, TypeError):
            logger.warning(
                "PolicyCrawlerAgent returned non-numeric max_tenure_years=%r for %s / %s; ignoring",
                tenure,
                bank_name,
                loan_type,
            )

    if fields:
        logger.info(
            "PolicyCrawlerAgent extracted %s for %s / %s",
            ", ".join(sorted(fields)),
            bank_name,
            loan_type,
        )

    # Kept even when no figure was extracted — the note is where the agent
    # says why (e.g. "homepage lists products but no rates").
    policy_notes = extracted.get("policy_notes")
    if isinstance(policy_notes, str) and policy_notes.strip():
        fields["policy_notes"] = policy_notes.strip()

    return fields


def _build_policy(
    loan_type: str,
    fields: dict,
    source_url: str | None,
    notes: dict | None = None,
    is_islamic: bool = False,
) -> ScrapedLoanPolicy:
    """Assemble a `ScrapedLoanPolicy` from PolicyCrawlerAgent's output,
    filling any gap from `FALLBACK_BASELINES`.

    `fields` holds only what the agent actually extracted (see
    `_agent_parse`) — there's no other source for these values, so any
    `POLICY_FIELDS` entry present in it is, by definition, agent-extracted;
    anything missing falls back to `FALLBACK_BASELINES`. No separate
    "which fields came from the agent" bookkeeping is needed as a result.

    Always returns a policy — a bank/category is never dropped from the
    database just because its homepage was blocked, unreachable,
    JS-rendered, or the agent couldn't extract anything from it.
    """
    baseline = FALLBACK_BASELINES[loan_type]
    agent_fields = [name for name in POLICY_FIELDS if fields.get(name) is not None]
    fallback_fields = [name for name in POLICY_FIELDS if fields.get(name) is None]
    resolved = {name: fields.get(name, baseline[name]) for name in POLICY_FIELDS}

    if fallback_fields:
        logger.warning(
            "%s policy from %s: fallback baseline for %s",
            loan_type,
            source_url,
            ", ".join(fallback_fields),
        )

    # `is_estimated` is the single flag consumers check: True whenever at
    # least one figure is a market baseline rather than bank-confirmed
    # (`fallback_fields` says which).
    policy_details = {"source_url": source_url, "is_estimated": bool(fallback_fields)}
    if fields.get("policy_notes"):
        policy_details["policy_notes"] = fields["policy_notes"]
    if fallback_fields:
        policy_details["fallback_fields"] = fallback_fields
        policy_details["fallback_note"] = (
            "Not extracted by PolicyCrawlerAgent (homepage unreachable, "
            "blocked, rendered client-side, or simply silent on this "
            "figure) — filled with a representative market-baseline "
            "estimate. Treat as an estimate, not a bank-confirmed figure."
        )
    if agent_fields:
        policy_details["source"] = "llm_agent_extracted"
        policy_details["agent_extracted_fields"] = agent_fields
    if notes:
        policy_details.update(notes)

    if agent_fields:
        raw_source = "llm_agent_extracted"
    elif fallback_fields:
        raw_source = "live_scrape_with_fallback"
    else:
        raw_source = "live_scrape"

    return ScrapedLoanPolicy(
        loan_type=loan_type,
        min_income=resolved["min_income"],
        max_dti_percentage=resolved["max_dti_percentage"],
        min_age=fields.get("min_age", 21),
        max_age=fields.get("max_age", 60),
        max_loan_amount=resolved["max_loan_amount"],
        profit_rate=resolved["profit_rate"],
        min_downpayment_percentage=resolved["min_downpayment_percentage"],
        max_tenure_years=resolved["max_tenure_years"],
        is_islamic=is_islamic,
        raw={
            "source": raw_source,
            "source_url": source_url,
        },
        policy_details=policy_details,
    )


def scrape_bank(bank: Bank, session: requests.Session | None = None) -> ScrapedBank:
    """Fetch and parse a single bank's `main_page_url`.

    The only URL used anywhere in this module — no per-category product
    page is hardcoded. A policy is still generated for every loan category
    the bank actually offers (see `BANK_PRODUCT_OMISSIONS`), even when the
    homepage yields nothing parseable, so a bank is never dropped from the
    database just because its homepage is blocked, unreachable, or the
    agent couldn't extract anything from it.

    Loan-policy figures come entirely from `PolicyCrawlerAgent`
    (`_agent_parse`), called once per loan category; whatever it can't
    extract falls back to `FALLBACK_BASELINES` inside `_build_policy`.
    """
    session = session or build_session()
    html = _fetch_raw_html(bank.main_page_url, session)
    if html is not None and not _has_readable_content(html):
        logger.warning(
            "%s returned no readable content (bot challenge or client-rendered shell); treating as blocked",
            bank.main_page_url,
        )
        html = None

    notes = {}
    if not bank.main_page_url:
        notes["fetch_status"] = "no_main_page_url_on_record"
    elif html is None:
        notes["fetch_status"] = "blocked_or_unreachable"

    omitted_types = BANK_PRODUCT_OMISSIONS.get(bank.name, set())
    policies = [
        _build_policy(
            loan_type,
            _agent_parse(html, bank.name, loan_type) if html is not None else {},
            bank.main_page_url,
            notes,
            bank.is_islamic,
        )
        for loan_type in LoanCategory.values
        if loan_type not in omitted_types
    ]

    return ScrapedBank(
        name=bank.name,
        is_islamic=bank.is_islamic,
        main_page_url=bank.main_page_url,
        policies=policies,
    )


class LiveBankDataSource(BankDataSource):
    """Scrapes every bank stored in the database via its `main_page_url`.

    Banks come from the database, not a hardcoded list — seed/update `Bank`
    rows (`name`, `is_islamic`, `main_page_url`) and this source picks them
    up automatically. A failure scraping one bank is logged and does not
    prevent the other banks from being fetched and returned.
    """

    def fetch(self) -> list[ScrapedBank]:
        session = build_session()
        results = []
        for bank in Bank.objects.all():
            try:
                results.append(scrape_bank(bank, session))
            except Exception:
                logger.exception("Live scrape of %s failed unexpectedly", bank.name)
        return results


def run_all_scrapers() -> dict:
    """Run the live scraper for every bank in the database and persist results.

    Returns the same summary dict as `fetch_bank_loan_policies`: counts of
    banks processed and policies created/updated.
    """
    return fetch_bank_loan_policies(data_source=LiveBankDataSource())
