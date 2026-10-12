from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from banks.models import Bank, LoanCategory, LoanPolicy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScrapedLoanPolicy:
    """A single loan policy pulled from a data source, ready for persistence."""

    loan_type: str
    min_income: Decimal
    max_dti_percentage: Decimal
    min_age: int
    max_age: int
    max_loan_amount: Decimal
    profit_rate: Decimal
    min_downpayment_percentage: Decimal
    max_tenure_years: int
    is_islamic: bool = False
    raw: dict[str, Any] = field(default_factory=dict)
    policy_details: dict[str, Any] | None = None


@dataclass(frozen=True)
class ScrapedBank:
    """A bank and all of its scraped loan policies."""

    name: str
    is_islamic: bool
    main_page_url: str
    policies: list[ScrapedLoanPolicy]


class BankDataSource(abc.ABC):
    """Interface for anything that can supply bank loan policy data.

    Implement this to plug in a real scraper (BeautifulSoup/Selenium) or
    another origin entirely. `fetch_bank_loan_policies` only depends on
    this interface, so swapping the data origin never requires touching
    the persistence logic.
    """

    @abc.abstractmethod
    def fetch(self) -> list[ScrapedBank]:
        """Return loan policy data for every bank this source covers."""
        raise NotImplementedError


class MockBankDataSource(BankDataSource):
    """Deterministic mock data source for the 13 target Pakistani banks."""

    BANKS: tuple[dict[str, Any], ...] = (
        {"name": "HBL", "is_islamic": False, "main_page_url": "https://www.hbl.com"},
        {"name": "UBL", "is_islamic": False, "main_page_url": "https://www.ubl.com.pk"},
        {"name": "MCB", "is_islamic": False, "main_page_url": "https://www.mcb.com.pk"},
        {"name": "ABL", "is_islamic": False, "main_page_url": "https://www.abl.com"},
        {
            "name": "Meezan Bank",
            "is_islamic": True,
            "main_page_url": "https://www.meezanbank.com",
        },
        {
            "name": "Bank Alfalah",
            "is_islamic": False,
            "main_page_url": "https://www.bankalfalah.com",
        },
        {
            "name": "Faysal Bank",
            "is_islamic": True,
            "main_page_url": "https://www.faysalbank.com",
        },
        {
            "name": "Askari Bank",
            "is_islamic": False,
            "main_page_url": "https://www.askaribank.com",
        },
        {
            "name": "BankIslami",
            "is_islamic": True,
            "main_page_url": "https://www.bankislami.com.pk",
        },
        {
            "name": "Standard Chartered",
            "is_islamic": False,
            "main_page_url": "https://www.sc.com/pk",
        },
        {
            "name": "JS Bank",
            "is_islamic": False,
            "main_page_url": "https://www.jsbl.com",
        },
        {
            "name": "Dubai Islamic Bank",
            "is_islamic": True,
            "main_page_url": "https://www.dibpak.com",
        },
        {"name": "BOP", "is_islamic": False, "main_page_url": "https://www.bop.com.pk"},
    )

    LOAN_TYPE_BASELINES: dict[str, dict[str, Any]] = {
        LoanCategory.PERSONAL: {
            "min_income": Decimal(50000),
            "max_dti_percentage": Decimal("50.00"),
            "max_loan_amount": Decimal(2000000),
            "profit_rate": Decimal("22.00"),
            "min_downpayment_percentage": Decimal("0.00"),
            "max_tenure_years": 5,
        },
        LoanCategory.VEHICLE: {
            "min_income": Decimal(60000),
            "max_dti_percentage": Decimal("50.00"),
            "max_loan_amount": Decimal(6000000),
            "profit_rate": Decimal("16.50"),
            "min_downpayment_percentage": Decimal("15.00"),
            "max_tenure_years": 7,
        },
        LoanCategory.HOME: {
            "min_income": Decimal(100000),
            "max_dti_percentage": Decimal("50.00"),
            "max_loan_amount": Decimal(50000000),
            "profit_rate": Decimal("14.00"),
            "min_downpayment_percentage": Decimal("20.00"),
            "max_tenure_years": 25,
        },
    }

    def fetch(self) -> list[ScrapedBank]:
        scraped_banks = []
        for index, bank_info in enumerate(self.BANKS):
            policies = [
                self._build_policy(loan_type, index, bank_info["is_islamic"])
                for loan_type in LoanCategory.values
            ]
            scraped_banks.append(
                ScrapedBank(
                    name=bank_info["name"],
                    is_islamic=bank_info["is_islamic"],
                    main_page_url=bank_info["main_page_url"],
                    policies=policies,
                )
            )
        return scraped_banks

    def _build_policy(
        self, loan_type: str, bank_index: int, is_islamic: bool
    ) -> ScrapedLoanPolicy:
        baseline = self.LOAN_TYPE_BASELINES[loan_type]
        # Small deterministic per-bank variation so mock data isn't identical
        # across banks, without relying on non-reproducible randomness.
        rate_offset = Decimal(bank_index % 5) * Decimal("0.25")
        income_offset = Decimal(bank_index % 4) * Decimal(2500)

        return ScrapedLoanPolicy(
            loan_type=loan_type,
            min_income=baseline["min_income"] + income_offset,
            max_dti_percentage=baseline["max_dti_percentage"],
            min_age=21,
            max_age=60,
            max_loan_amount=baseline["max_loan_amount"],
            profit_rate=baseline["profit_rate"] + rate_offset,
            min_downpayment_percentage=baseline["min_downpayment_percentage"],
            max_tenure_years=baseline["max_tenure_years"],
            is_islamic=is_islamic,
            raw={
                "loan_type": loan_type,
                "source": "mock",
                "bank_index": bank_index,
            },
        )


def _validate_bank(scraped_bank: ScrapedBank) -> list[str]:
    """Return validation errors for a `ScrapedBank`; empty means it's safe to persist."""
    errors = []
    if not scraped_bank.name or not scraped_bank.name.strip():
        errors.append("name is empty")
    if not scraped_bank.main_page_url or not scraped_bank.main_page_url.strip():
        errors.append("main_page_url is empty")
    return errors


def _validate_policy(policy: ScrapedLoanPolicy) -> list[str]:
    """Return validation errors for a `ScrapedLoanPolicy`; empty means it's
    safe to persist into `LoanPolicy`.

    Guards the database against empty or corrupted payloads reaching it —
    a scraper bug, a malformed page, or a bad parse should never silently
    write a policy a comparison feature can't rely on.
    """
    errors = []
    if policy.loan_type not in LoanCategory.values:
        errors.append(f"loan_type {policy.loan_type!r} is not a valid LoanCategory")
    if policy.min_income is None or policy.min_income <= 0:
        errors.append("min_income must be a positive amount")
    if policy.max_loan_amount is None or policy.max_loan_amount <= 0:
        errors.append("max_loan_amount must be a positive amount")
    if policy.profit_rate is None or not (
        Decimal(0) <= policy.profit_rate <= Decimal(100)
    ):
        errors.append("profit_rate must be between 0 and 100")
    if policy.max_dti_percentage is None or not (
        Decimal(0) < policy.max_dti_percentage <= Decimal(100)
    ):
        errors.append("max_dti_percentage must be between 0 (exclusive) and 100")
    if policy.min_downpayment_percentage is None or not (
        Decimal(0) <= policy.min_downpayment_percentage <= Decimal(100)
    ):
        errors.append("min_downpayment_percentage must be between 0 and 100")
    if policy.max_tenure_years is None or policy.max_tenure_years <= 0:
        errors.append("max_tenure_years must be a positive integer")
    if policy.min_age is None or policy.max_age is None or policy.min_age <= 0:
        errors.append("min_age/max_age must be positive integers")
    elif policy.max_age <= policy.min_age:
        errors.append("max_age must be greater than min_age")
    return errors


def fetch_bank_loan_policies(
    data_source: BankDataSource | None = None,
) -> dict[str, int]:
    """Fetch loan policy data and persist it into the Bank and LoanPolicy models.

    `data_source` defaults to `MockBankDataSource` but accepts any
    `BankDataSource` implementation (a BeautifulSoup scraper or any other
    origin), so the data origin can change later without touching this
    function. Every bank and policy is validated (`_validate_bank` /
    `_validate_policy`) before being written — anything that fails is
    logged and skipped rather than persisted.
    """
    source = data_source or MockBankDataSource()
    scraped_banks = source.fetch()

    banks_processed = 0
    banks_rejected = 0
    policies_created = 0
    policies_updated = 0
    policies_rejected = 0

    for scraped_bank in scraped_banks:
        bank_errors = _validate_bank(scraped_bank)
        if bank_errors:
            logger.error(
                "Rejected bank %r: %s", scraped_bank.name, "; ".join(bank_errors)
            )
            banks_rejected += 1
            continue

        bank, _ = Bank.objects.update_or_create(
            name=scraped_bank.name,
            defaults={
                "is_islamic": scraped_bank.is_islamic,
                "main_page_url": scraped_bank.main_page_url,
            },
        )
        banks_processed += 1

        for policy in scraped_bank.policies:
            policy_errors = _validate_policy(policy)
            if policy_errors:
                logger.error(
                    "Rejected %s policy for %r: %s",
                    policy.loan_type,
                    scraped_bank.name,
                    "; ".join(policy_errors),
                )
                policies_rejected += 1
                continue

            _, created = LoanPolicy.objects.update_or_create(
                bank=bank,
                loan_type=policy.loan_type,
                defaults={
                    "min_income": policy.min_income,
                    "max_dti_percentage": policy.max_dti_percentage,
                    "min_age": policy.min_age,
                    "max_age": policy.max_age,
                    "max_loan_amount": policy.max_loan_amount,
                    "profit_rate": policy.profit_rate,
                    "min_downpayment_percentage": policy.min_downpayment_percentage,
                    "max_tenure_years": policy.max_tenure_years,
                    "is_islamic": policy.is_islamic,
                    "raw_scraped_data": policy.raw,
                    "policy_details": policy.policy_details,
                },
            )
            if created:
                policies_created += 1
            else:
                policies_updated += 1

    logger.info(
        "Loan policy sync complete: %s banks (%s rejected), %s policies created, "
        "%s policies updated, %s policies rejected",
        banks_processed,
        banks_rejected,
        policies_created,
        policies_updated,
        policies_rejected,
    )

    return {
        "banks_processed": banks_processed,
        "banks_rejected": banks_rejected,
        "policies_created": policies_created,
        "policies_updated": policies_updated,
        "policies_rejected": policies_rejected,
    }
