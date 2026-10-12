from decimal import Decimal
from unittest import mock

from banks.models import Bank, LoanCategory, LoanPolicy
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from scrapers import bank_scraper
from scrapers.bank_scraper import (
    FALLBACK_BASELINES,
    POLICY_FIELDS,
    _agent_parse,
    _build_policy,
    run_all_scrapers,
    scrape_bank,
)
from scrapers.scraper_service import (
    MockBankDataSource,
    _validate_policy,
    fetch_bank_loan_policies,
)


class BuildPolicyTests(SimpleTestCase):
    def test_no_extracted_fields_is_fully_estimated(self):
        policy = _build_policy(LoanCategory.HOME, {}, "https://bank.example")

        baseline = FALLBACK_BASELINES[LoanCategory.HOME]
        for name in POLICY_FIELDS:
            self.assertEqual(getattr(policy, name), baseline[name])
        self.assertTrue(policy.policy_details["is_estimated"])
        self.assertEqual(policy.policy_details["fallback_fields"], list(POLICY_FIELDS))
        self.assertEqual(policy.raw["source"], "live_scrape_with_fallback")
        self.assertEqual(_validate_policy(policy), [])

    def test_partial_extraction_keeps_agent_values_and_notes(self):
        fields = {"profit_rate": Decimal("19.5"), "policy_notes": "Rate found in FAQ."}

        policy = _build_policy(LoanCategory.PERSONAL, fields, "https://bank.example")

        self.assertEqual(policy.profit_rate, Decimal("19.5"))
        self.assertTrue(policy.policy_details["is_estimated"])
        self.assertEqual(
            policy.policy_details["agent_extracted_fields"], ["profit_rate"]
        )
        self.assertNotIn("profit_rate", policy.policy_details["fallback_fields"])
        self.assertEqual(policy.policy_details["policy_notes"], "Rate found in FAQ.")

    def test_full_extraction_is_not_estimated(self):
        fields = dict(FALLBACK_BASELINES[LoanCategory.VEHICLE])

        policy = _build_policy(LoanCategory.VEHICLE, fields, "https://bank.example")

        self.assertFalse(policy.policy_details["is_estimated"])
        self.assertNotIn("fallback_fields", policy.policy_details)
        self.assertNotIn("policy_notes", policy.policy_details)


class AgentParseTests(SimpleTestCase):
    def test_policy_notes_returned_even_without_figures(self):
        agent = mock.Mock()
        agent.extract_policy.return_value = {
            "profit_rate": None,
            "max_tenure_years": None,
            "policy_notes": "  No loan figures on this page.  ",
        }

        with mock.patch.object(
            bank_scraper, "_get_policy_crawler_agent", return_value=agent
        ):
            fields = _agent_parse("<p>Welcome</p>", "HBL", LoanCategory.PERSONAL)

        self.assertEqual(fields, {"policy_notes": "No loan figures on this page."})


class ScrapeBankTests(SimpleTestCase):
    def test_blocked_bank_still_gets_estimated_policies(self):
        bank = Bank(
            name="BOP", is_islamic=False, main_page_url="https://www.bop.com.pk"
        )

        with mock.patch.object(
            bank_scraper, "_fetch_raw_html", return_value=None
        ), mock.patch.object(bank_scraper, "_agent_parse") as agent_parse:
            scraped = scrape_bank(bank, session=mock.Mock())

        agent_parse.assert_not_called()
        self._assert_blocked_and_estimated(scraped)

    def test_challenge_page_served_with_200_is_treated_as_blocked(self):
        bank = Bank(
            name="BOP", is_islamic=False, main_page_url="https://www.bop.com.pk"
        )
        challenge = (
            '<html><head><script src="/_Incapsula_Resource?x=1"></script></head>'
            '<body><iframe src="/_Incapsula_Resource?y=2">Request unsuccessful. '
            "Incapsula incident ID: 123</iframe></body></html>"
        )

        with mock.patch.object(
            bank_scraper, "_fetch_raw_html", return_value=challenge
        ), mock.patch.object(bank_scraper, "_agent_parse") as agent_parse:
            scraped = scrape_bank(bank, session=mock.Mock())

        agent_parse.assert_not_called()
        self._assert_blocked_and_estimated(scraped)

    def _assert_blocked_and_estimated(self, scraped):
        self.assertEqual(
            {p.loan_type for p in scraped.policies}, set(LoanCategory.values)
        )
        for policy in scraped.policies:
            self.assertEqual(
                policy.policy_details["fetch_status"], "blocked_or_unreachable"
            )
            self.assertTrue(policy.policy_details["is_estimated"])
            self.assertEqual(policy.raw["source"], "live_scrape_with_fallback")
            self.assertEqual(_validate_policy(policy), [])


class PersistenceTests(TestCase):
    def test_repeated_runs_update_rows_instead_of_duplicating(self):
        first = fetch_bank_loan_policies(MockBankDataSource())
        second = fetch_bank_loan_policies(MockBankDataSource())

        self.assertEqual(first["policies_created"], 39)
        self.assertEqual(second["policies_created"], 0)
        self.assertEqual(second["policies_updated"], 39)
        self.assertEqual(Bank.objects.count(), 13)
        self.assertEqual(LoanPolicy.objects.count(), 39)

    def test_database_rejects_duplicate_bank_and_loan_type(self):
        fetch_bank_loan_policies(MockBankDataSource())
        existing = LoanPolicy.objects.first()
        existing.pk = None

        with self.assertRaises(IntegrityError), transaction.atomic():
            existing.save()

    def test_standard_chartered_vehicle_policy_is_never_saved(self):
        Bank.objects.create(
            name="Standard Chartered",
            is_islamic=False,
            main_page_url="https://www.sc.com/pk",
        )

        with mock.patch.object(bank_scraper, "_fetch_raw_html", return_value=None):
            result = run_all_scrapers()

        saved = set(
            LoanPolicy.objects.filter(bank__name="Standard Chartered").values_list(
                "loan_type", flat=True
            )
        )
        self.assertEqual(result["policies_created"], 2)
        self.assertEqual(saved, {LoanCategory.PERSONAL, LoanCategory.HOME})
