"""Autonomous Financial Policy Extraction Agent.

`PolicyCrawlerAgent` reads raw, unstructured page content (HTML or plain
text) for a single bank/loan-type pair and extracts the exact numerical
loan policy figures found in it — tables, FAQs, or plain prose. It is
called by `scrapers.bank_scraper._agent_parse`, once per bank/loan-type
pair, to fill a `ScrapedLoanPolicy`; anything it can't extract falls back
to that module's `FALLBACK_BASELINES`.

This module has no dependency on `scrapers.*` itself — only the reverse —
so it stays usable standalone (e.g. for ad-hoc extraction or tests) without
pulling in the scraping/persistence pipeline.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from django.conf import settings
from services.llm_provider import GROQ_ERROR_MESSAGE, LLMProviderError, call_llm

logger = logging.getLogger(__name__)

# The exact keys `extract_policy` guarantees in its return value (when it
# returns non-empty) — a strict contract so callers never need to branch on
# which fields happen to be present.
EXPECTED_KEYS = (
    "min_income",
    "max_dti_percentage",
    "max_loan_amount",
    "profit_rate",
    "min_downpayment_percentage",
    "max_tenure_years",
    "policy_notes",
)

# Raw page content is truncated before being sent to the model — comparison
# accuracy only ever needs the figures themselves, not an entire page's
# markup, and this keeps prompts well inside context/token limits.
MAX_CONTENT_CHARS = 20000

SYSTEM_PROMPT = (
    "You are an Autonomous Financial Policy Extraction Agent, a specialist "
    "sub-system inside a bank loan comparison platform. You are not a "
    "conversational assistant — you never greet, explain, or add commentary "
    "outside the single JSON object described below.\n\n"
    "You will be given the raw, unstructured content of a bank's web page "
    "(HTML markup or extracted text) together with the bank's name and the "
    "loan type it should describe (Personal, Home, or Vehicle). Your job is "
    "to carefully read the ENTIRE content — including HTML tables, FAQ "
    "question/answer pairs, and ordinary prose — and extract the exact "
    "numerical loan policy values for that specific bank and loan type.\n\n"
    "Rules you must follow exactly:\n"
    "1. Only extract values that are explicitly stated or unambiguously "
    "computable from the content. Never guess, estimate, or invent a "
    "number that is not grounded in the text.\n"
    "2. If a field is not present in the content, its value must be JSON "
    "null — never a placeholder, never zero, never a market-average guess.\n"
    "3. All monetary and percentage fields must be plain numbers (no "
    "currency symbols, no thousands separators, no '%' sign, no text like "
    "'PKR' or 'approx').\n"
    "4. Normalize units: monetary figures must be numeric (e.g. 'PKR 5 "
    "lac' -> 500000, '2 crore' -> 20000000); percentages must be a plain "
    "number out of 100 (e.g. '18%' -> 18); tenure must be a whole number "
    "of years.\n"
    "5. If the content clearly does not concern the requested bank or loan "
    "type, return all numeric fields as null and explain why in "
    "policy_notes.\n"
    "6. profit_rate must be the full annual rate the customer pays. A "
    "spread over a benchmark (e.g. 'KIBOR + 1.19%') is not a rate on its "
    "own — return null for profit_rate and quote the spread in "
    "policy_notes instead.\n"
    "7. Respond with ONLY a single, strictly valid JSON object — no "
    "markdown code fences, no leading/trailing prose, no explanations "
    "outside the JSON.\n\n"
    "The JSON object must have exactly these keys:\n"
    '  "min_income": number or null — minimum monthly gross income required\n'
    '  "max_dti_percentage": number or null — maximum debt-to-income ratio allowed, as a percentage\n'
    '  "max_loan_amount": number or null — maximum loan/financing amount offered\n'
    '  "profit_rate": number or null — the profit/markup/interest rate, as a percentage\n'
    '  "min_downpayment_percentage": number or null — minimum down payment required, as a percentage\n'
    '  "max_tenure_years": number or null — maximum repayment tenure, in years\n'
    '  "policy_notes": string — a short note on what was found, what was '
    "missing, and how confident you are in the extraction (e.g. 'Rate and "
    "tenure found in the FAQ table; income and DTI figures not present on "
    "this page.')"
)

_JSON_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class PolicyCrawlerAgent:
    """LLM-backed extractor that turns raw bank page content into structured
    loan policy figures.

    Wraps `services.llm_provider.call_llm` (Groq) behind a single
    `extract_policy` method. Every failure mode — no `GROQ_API_KEY`
    configured, a Groq API error, or a response that isn't valid JSON — is
    caught and logged; the caller always gets a dict back, `{}` on any
    failure, and never an exception.
    """

    def __init__(self, temperature: float = 0.0) -> None:
        if not settings.GROQ_API_KEY:
            raise RuntimeError(GROQ_ERROR_MESSAGE)
        self._temperature = temperature

    def extract_policy(
        self, html_text: str, bank_name: str, loan_type: str
    ) -> dict[str, Any]:
        """Extract loan policy figures for `bank_name`/`loan_type` from `html_text`.

        Args:
            html_text: Raw HTML or plain text content of a page believed to
                describe this bank's loan policies.
            bank_name: The bank the content belongs to (e.g. "HBL").
            loan_type: The loan category to extract (e.g. "Personal", "Home",
                "Vehicle").

        Returns:
            A dict with exactly the keys in `EXPECTED_KEYS` on success, or
            `{}` if the content was empty, the Groq call failed, or the
            response could not be parsed as the expected JSON object. This
            method never raises.
        """
        if not html_text or not html_text.strip():
            logger.warning(
                "PolicyCrawlerAgent: no content provided for %s / %s",
                bank_name,
                loan_type,
            )
            return {}

        try:
            reply = call_llm(
                SYSTEM_PROMPT,
                self._build_user_prompt(html_text, bank_name, loan_type),
                response_format_json=True,
                temperature=self._temperature,
            )
        except LLMProviderError:
            logger.exception(
                "PolicyCrawlerAgent: Groq call failed for %s / %s", bank_name, loan_type
            )
            return {}

        return self._parse_response(reply, bank_name, loan_type)

    @staticmethod
    def _build_user_prompt(html_text: str, bank_name: str, loan_type: str) -> str:
        trimmed = html_text[:MAX_CONTENT_CHARS]
        return (
            f"Bank: {bank_name}\n"
            f"Loan type: {loan_type}\n\n"
            "Raw page content follows between the markers. Extract the "
            "policy figures for this bank and loan type only, following "
            "the rules and JSON schema from your instructions.\n\n"
            "--- CONTENT START ---\n"
            f"{trimmed}\n"
            "--- CONTENT END ---"
        )

    def _parse_response(
        self, content: Any, bank_name: str, loan_type: str
    ) -> dict[str, Any]:
        """Best-effort parse of the model's reply into the expected dict shape.

        Tolerates a fenced ```json ...``` block in case the model ignores
        the "no markdown" instruction; any other shape (missing JSON,
        malformed JSON, a non-object JSON value) is treated as a failed
        extraction and logged, never raised.
        """
        text = content if isinstance(content, str) else str(content)

        json_text = self._extract_json_object(text)
        if json_text is None:
            logger.error(
                "PolicyCrawlerAgent: no JSON object found in response for %s / %s",
                bank_name,
                loan_type,
            )
            return {}

        try:
            data = json.loads(json_text)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.error(
                "PolicyCrawlerAgent: failed to decode JSON for %s / %s: %s",
                bank_name,
                loan_type,
                exc,
            )
            return {}

        if not isinstance(data, dict):
            logger.error(
                "PolicyCrawlerAgent: decoded JSON was not an object for %s / %s",
                bank_name,
                loan_type,
            )
            return {}

        return {key: data.get(key) for key in EXPECTED_KEYS}

    @staticmethod
    def _extract_json_object(text: str) -> str | None:
        """Pulls the JSON object out of `text`, tolerating a fenced code block."""
        fence_match = _JSON_FENCE_PATTERN.search(text)
        if fence_match:
            return fence_match.group(1)

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]
        return None
