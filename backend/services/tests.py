"""Tests for Chunk 2 (Backend Data & JSON Response Refinement):

- `PredictiveBankAgent.build_structured_report` always populates every KPI/
  section field, for both a normal match and a zero-match (advisory) profile.
- `GET /api/reports/<id>/` round-trips a saved `LoanRequest` end to end —
  the actual "database save/fetch logic" the report views depend on.
- The chat pipeline's internal-reasoning/scratchpad scrubber never lets
  leaked "waiting for user"/labeled-internal-line text reach a reply.

...and Chunk 1 (Chat-Specific Report Binding):

- `GET /api/reports/?chat_id=...` only returns reports generated in that
  chat session, never another session's or another user's.
- Deleting a chat session's `ChatSession` row cascades (a real DB-level FK
  CASCADE, see `users.models.LoanRequest.chat_session`) to delete every
  `LoanRequest` (report) generated within it.
"""

from banks.models import Bank, LoanCategory, LoanPolicy
from django.contrib.auth import get_user_model
from django.test import TestCase
from mcp_server.agent import _clean_reply_text
from mcp_server.chat_history import _delete_loan_requests_for_session
from rest_framework.test import APIClient
from users.models import ChatSession, LoanRequest, LoanRequestType

from services.financial_calculator import PredictiveBankAgent

User = get_user_model()


class BuildStructuredReportTests(TestCase):
    """`build_structured_report` must never leave a KPI/section field null —
    the exact bug ("Not available" on the frontend's KPI cards) Chunk 2 fixes.
    """

    def setUp(self):
        self.agent = PredictiveBankAgent()
        self.eligible_profile = {
            "monthly_income": 250000.0,
            "required_amount": 2000000.0,
            "tenure_years": 5,
            "is_islamic": False,
            "loan_type": "Personal",
            "dti_percentage": 25.0,
        }
        self.policies = [
            {
                "bank_name": "Test Bank",
                "is_islamic": False,
                "profit_rate": 18.0,
                "min_downpayment_percentage": 10.0,
                "max_tenure_years": 5,
                "main_page_url": "https://testbank.example.com",
            }
        ]

    def test_kpis_always_fully_populated_for_a_match(self):
        ranked = self.agent.evaluate_and_rank(self.policies, self.eligible_profile)
        report = self.agent.build_structured_report(ranked, self.eligible_profile)

        kpis = report["kpis"]
        for field in (
            "requested_amount",
            "monthly_income",
            "tenure",
            "dti_ratio",
            "eligibility_status",
        ):
            self.assertIn(field, kpis)
            self.assertIsNotNone(kpis[field], f"{field} must never be null")

        self.assertEqual(kpis["dti_ratio"], "25.0%")
        self.assertEqual(kpis["eligibility_status"], "Eligible")
        self.assertEqual(kpis["tenure"], 5)
        self.assertIsInstance(report["policy_warnings"], list)
        self.assertIsInstance(report["strategic_steps"], list)
        self.assertTrue(report["strategic_steps"])
        self.assertTrue(report["raw_markdown"])

    def test_kpis_always_fully_populated_on_zero_match_advisory(self):
        """No candidate policies at all (e.g. requested amount over every
        bank's ceiling) must still return concrete KPIs/sections, never a
        blank/None report."""
        over_limit_profile = {
            **self.eligible_profile,
            "required_amount": 999_000_000.0,
            "dti_percentage": 92.3,
            "catalog_max_amount": 50_000_000.0,
        }
        report = self.agent.build_structured_report([], over_limit_profile)

        kpis = report["kpis"]
        for field in (
            "requested_amount",
            "monthly_income",
            "tenure",
            "dti_ratio",
            "eligibility_status",
        ):
            self.assertIsNotNone(kpis[field])

        self.assertEqual(kpis["eligibility_status"], "Not Eligible")
        self.assertEqual(report["bank_recommendations"], [])
        self.assertTrue(
            report["policy_warnings"], "an over-limit DTI must always raise a warning"
        )
        self.assertEqual(report["policy_warnings"][0]["level"], "red")
        self.assertTrue(
            report["strategic_steps"],
            "the advisory case must still offer concrete next steps",
        )
        self.assertTrue(report["raw_markdown"])

    def test_policy_warning_levels(self):
        red = self.agent.build_policy_warnings(
            self.agent._normalize_profile(
                {**self.eligible_profile, "dti_percentage": 55.0}
            )
        )
        amber = self.agent.build_policy_warnings(
            self.agent._normalize_profile(
                {**self.eligible_profile, "dti_percentage": 45.0}
            )
        )
        clear = self.agent.build_policy_warnings(
            self.agent._normalize_profile(
                {**self.eligible_profile, "dti_percentage": 10.0}
            )
        )

        self.assertEqual(red[0]["level"], "red")
        self.assertEqual(amber[0]["level"], "amber")
        self.assertEqual(clear, [])

    def test_bank_recommendations_shape(self):
        ranked = self.agent.evaluate_and_rank(self.policies, self.eligible_profile)
        recommendations = self.agent.build_bank_recommendations(ranked, "Personal Loan")

        self.assertEqual(len(recommendations), 1)
        rec = recommendations[0]
        for field in (
            "bank_name",
            "loan_type",
            "monthly_installment",
            "interest_rate",
            "shariah_compliant",
            "apply_url",
        ):
            self.assertIn(field, rec)
        self.assertEqual(rec["bank_name"], "Test Bank")
        self.assertEqual(rec["loan_type"], "Personal Loan")
        self.assertEqual(rec["apply_url"], "https://testbank.example.com")
        self.assertFalse(rec["shariah_compliant"])


class LoanReportApiTests(TestCase):
    """`GET /api/reports/<id>/` — the database save/fetch path end to end."""

    def setUp(self):
        self.client = APIClient()
        bank = Bank.objects.create(
            name="Meezan Test Bank",
            is_islamic=True,
            main_page_url="https://meezan.example.com",
        )
        LoanPolicy.objects.create(
            bank=bank,
            loan_type=LoanCategory.PERSONAL,
            min_income=50000,
            max_dti_percentage=50,
            max_loan_amount=5_000_000,
            profit_rate=16.5,
            min_downpayment_percentage=0,
            max_tenure_years=5,
            is_islamic=True,
        )
        self.loan_request = LoanRequest.objects.create(
            loan_type=LoanRequestType.PERSONAL,
            required_amount=2_000_000,
            monthly_income=250_000,
            is_islamic=True,
            desired_tenure_years=5,
        )

    def test_report_round_trip_populates_every_field(self):
        response = self.client.get(f"/api/reports/{self.loan_request.id}/")

        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["loan_request_id"], self.loan_request.id)
        self.assertEqual(body["loan_type"], "Personal")
        self.assertTrue(body["is_islamic"])

        kpis = body["kpis"]
        self.assertEqual(kpis["requested_amount"], 2_000_000.0)
        self.assertEqual(kpis["monthly_income"], 250_000.0)
        self.assertEqual(kpis["tenure"], 5)
        self.assertRegex(kpis["dti_ratio"], r"^\d+(\.\d+)?%$")
        self.assertIn(kpis["eligibility_status"], ("Eligible", "Not Eligible"))

        self.assertIsInstance(body["policy_warnings"], list)
        self.assertIsInstance(body["strategic_steps"], list)
        self.assertTrue(body["strategic_steps"])
        self.assertTrue(body["raw_markdown"])

        self.assertEqual(len(body["bank_recommendations"]), 1)
        recommendation = body["bank_recommendations"][0]
        self.assertEqual(recommendation["bank_name"], "Meezan Test Bank")
        self.assertEqual(recommendation["apply_url"], "https://meezan.example.com")
        self.assertTrue(recommendation["shariah_compliant"])

    def test_unknown_loan_request_returns_404(self):
        response = self.client.get("/api/reports/999999/")
        self.assertEqual(response.status_code, 404)

    def test_report_scoped_to_owning_user(self):
        owner = User.objects.create_user(username="owner", password="pw12345")
        other = User.objects.create_user(username="other", password="pw12345")
        owned_request = LoanRequest.objects.create(
            user=owner,
            loan_type=LoanRequestType.HOME,
            required_amount=3_000_000,
            monthly_income=300_000,
            is_islamic=False,
            desired_tenure_years=10,
        )

        self.client.force_authenticate(user=other)
        response = self.client.get(f"/api/reports/{owned_request.id}/")
        self.assertEqual(response.status_code, 404)

        self.client.force_authenticate(user=owner)
        response = self.client.get(f"/api/reports/{owned_request.id}/")
        self.assertEqual(response.status_code, 200)


class ListReportsApiTests(TestCase):
    """`GET /api/reports/?chat_id=...` — Chunk 1's scoped reports filtering."""

    def setUp(self):
        self.client = APIClient()
        bank = Bank.objects.create(
            name="Meezan Test Bank",
            is_islamic=True,
            main_page_url="https://meezan.example.com",
        )
        LoanPolicy.objects.create(
            bank=bank,
            loan_type=LoanCategory.PERSONAL,
            min_income=50000,
            max_dti_percentage=50,
            max_loan_amount=5_000_000,
            profit_rate=16.5,
            min_downpayment_percentage=0,
            max_tenure_years=5,
            is_islamic=True,
        )

    def _make_loan_request(self, session_id=None, user=None):
        chat_session = None
        if session_id:
            chat_session, _ = ChatSession.objects.get_or_create(
                id=session_id, defaults={"user": user}
            )
        return LoanRequest.objects.create(
            user=user,
            chat_session=chat_session,
            loan_type=LoanRequestType.PERSONAL,
            required_amount=2_000_000,
            monthly_income=250_000,
            is_islamic=True,
            desired_tenure_years=5,
        )

    def test_chat_id_scopes_to_only_that_sessions_reports(self):
        in_chat = self._make_loan_request(session_id="chat-a")
        self._make_loan_request(session_id="chat-b")
        self._make_loan_request(session_id=None)

        response = self.client.get("/api/reports/", {"chat_id": "chat-a"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["loan_request_id"], in_chat.id)

    def test_chat_id_never_leaks_another_users_reports(self):
        owner = User.objects.create_user(username="owner2", password="pw12345")
        other = User.objects.create_user(username="other2", password="pw12345")
        self._make_loan_request(session_id="shared-chat-id", user=owner)

        self.client.force_authenticate(user=other)
        response = self.client.get("/api/reports/", {"chat_id": "shared-chat-id"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)

    def test_without_chat_id_requires_authentication(self):
        response = self.client.get("/api/reports/")
        self.assertEqual(response.status_code, 401)

    def test_without_chat_id_returns_full_authenticated_history(self):
        owner = User.objects.create_user(username="owner3", password="pw12345")
        self._make_loan_request(session_id="chat-a", user=owner)
        self._make_loan_request(session_id="chat-b", user=owner)

        self.client.force_authenticate(user=owner)
        response = self.client.get("/api/reports/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 2)


class ChatSessionReportCascadeDeleteTests(TestCase):
    """Deleting a chat session (its `ChatSession` row) must cascade-delete
    every `LoanRequest` (report) FK'd to it — a real DB-level CASCADE, not an
    application-level filter."""

    def test_guest_session_reports_are_purged(self):
        other_session = ChatSession.objects.create(id="other-session")
        guest_session = ChatSession.objects.create(id="guest-session")
        kept = LoanRequest.objects.create(
            chat_session=other_session,
            loan_type=LoanRequestType.PERSONAL,
            required_amount=1_000_000,
            monthly_income=100_000,
            desired_tenure_years=3,
        )
        LoanRequest.objects.create(
            chat_session=guest_session,
            loan_type=LoanRequestType.PERSONAL,
            required_amount=1_000_000,
            monthly_income=100_000,
            desired_tenure_years=3,
        )

        deleted_count = _delete_loan_requests_for_session("guest-session", None)

        self.assertEqual(deleted_count, 1)
        self.assertTrue(LoanRequest.objects.filter(id=kept.id).exists())
        self.assertFalse(ChatSession.objects.filter(id="guest-session").exists())
        self.assertFalse(
            LoanRequest.objects.filter(chat_session_id="guest-session").exists()
        )

    def test_authenticated_session_reports_require_matching_owner(self):
        owner = User.objects.create_user(username="session-owner", password="pw12345")
        intruder = User.objects.create_user(
            username="session-intruder", password="pw12345"
        )
        owned_session = ChatSession.objects.create(id="owned-session", user=owner)
        LoanRequest.objects.create(
            user=owner,
            chat_session=owned_session,
            loan_type=LoanRequestType.PERSONAL,
            required_amount=1_000_000,
            monthly_income=100_000,
            desired_tenure_years=3,
        )

        deleted_count = _delete_loan_requests_for_session("owned-session", intruder.id)
        self.assertEqual(deleted_count, 0)
        self.assertTrue(
            LoanRequest.objects.filter(chat_session_id="owned-session").exists()
        )

        deleted_count = _delete_loan_requests_for_session("owned-session", owner.id)
        self.assertEqual(deleted_count, 1)
        self.assertFalse(
            LoanRequest.objects.filter(chat_session_id="owned-session").exists()
        )


class CleanReplyTextTests(TestCase):
    """`_clean_reply_text` must strip every leaked internal-reasoning/
    scratchpad pattern before a reply is saved or returned (Chunk 2 item 3)."""

    def test_strips_think_blocks(self):
        text = "Hello there.<think>internal plan the user must never see</think> How can I help?"
        cleaned = _clean_reply_text(text)
        self.assertNotIn("<think>", cleaned)
        self.assertNotIn("internal plan", cleaned)

    def test_strips_waiting_narration(self):
        text = "What tenure would you like?\n\nWe need to wait for the user to respond."
        cleaned = _clean_reply_text(text)
        self.assertNotIn("wait for", cleaned)
        self.assertIn("What tenure would you like?", cleaned)

    def test_strips_waiting_parenthetical(self):
        text = "What's your monthly income? (Waiting for user's response regarding income.)"
        cleaned = _clean_reply_text(text)
        self.assertNotIn("Waiting for", cleaned)

    def test_strips_labeled_internal_lines(self):
        text = "Sure, here are your options.\nScratchpad: consider mentioning EMI next.\nLet me know if you want more."
        cleaned = _clean_reply_text(text)
        self.assertNotIn("Scratchpad:", cleaned)

    def test_leaves_clean_text_untouched(self):
        text = "Here is your executive summary. Let me know if you have questions."
        self.assertEqual(_clean_reply_text(text), text)
