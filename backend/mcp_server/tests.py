"""Tests for the chat API and the agent's follow-up turn flow.

`ChatApiAuthTests` and `ChatContextPassingTests` patch out MongoDB and the
LLM agent — they cover who may call each endpoint, which `user_id` reaches
the storage layer, and what conversation context reaches the agent.
`FollowUpAdjustmentFlowTests` runs the real agent loop and MCP tools against
the test database, with only the Groq model replaced by a scripted one.
"""

import json
import uuid
from unittest.mock import patch

from banks.models import Bank, LoanCategory, LoanPolicy
from django.contrib.auth import get_user_model
from django.test import TestCase
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken
from users.models import LoanRequest

from .agent import CONFIRMATION_NOTE, FOLLOW_UP_NOTE, run_chat_agent

User = get_user_model()

AGENT_RESULT = {
    "reply": "Hello",
    "tool_calls": [],
    "state": {},
    "loan_request_id": None,
    "report": None,
}


class ChatApiAuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="owner@example.com",
            email="owner@example.com",
            password="pw-12345-xyz",
        )
        self.other = User.objects.create_user(
            username="other@example.com",
            email="other@example.com",
            password="pw-12345-xyz",
        )

    def _authenticate(self, user):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}"
        )

    def test_every_chat_endpoint_rejects_unauthenticated_requests(self):
        responses = [
            self.client.post("/api/chat/", {"message": "hi"}, format="json"),
            self.client.get("/api/chat/history/", {"session_id": "abc"}),
            self.client.delete("/api/chat/history/abc/"),
        ]

        self.assertEqual(
            [response.status_code for response in responses], [401, 401, 401]
        )

    def test_x_user_id_header_alone_is_not_an_identity(self):
        response = self.client.get(
            "/api/chat/history/",
            {"session_id": "abc"},
            HTTP_X_USER_ID="owner@example.com",
        )

        self.assertEqual(response.status_code, 401)

    def test_invalid_token_is_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")

        response = self.client.get("/api/chat/history/", {"session_id": "abc"})

        self.assertEqual(response.status_code, 401)

    @patch("mcp_server.api.get_session_chat_history", return_value=[])
    def test_history_is_fetched_for_the_token_user_not_the_header(self, get_history):
        self._authenticate(self.user)

        response = self.client.get(
            "/api/chat/history/",
            {"session_id": "abc"},
            HTTP_X_USER_ID=str(self.other.id),
        )

        self.assertEqual(response.status_code, 200)
        get_history.assert_called_once_with("abc", self.user.id, limit=20)

    @patch("mcp_server.api.delete_session_chat_history", return_value=3)
    def test_delete_is_scoped_to_the_token_user(self, delete_history):
        self._authenticate(self.user)

        response = self.client.delete("/api/chat/history/abc/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["deleted_count"], 3)
        delete_history.assert_called_once_with("abc", self.user.id)

    @patch("mcp_server.api.run_chat_agent", return_value=AGENT_RESULT)
    @patch("mcp_server.api.save_chat_message")
    @patch("mcp_server.api.get_session_chat_history", return_value=[])
    def test_chat_turn_reads_and_writes_under_the_token_user(
        self, get_history, save_message, run_agent
    ):
        self._authenticate(self.user)

        response = self.client.post(
            "/api/chat/", {"message": "hi", "session_id": "abc"}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        get_history.assert_called_once_with("abc", self.user.id, limit=20)
        self.assertEqual(
            [call.args[1] for call in save_message.call_args_list],
            [self.user.id, self.user.id],
        )
        self.assertEqual(run_agent.call_args.args[3], self.user)


ACTIVE_STATE = {
    "loan_type": "Personal",
    "required_amount": 1_000_000,
    "monthly_income": 200_000,
    "is_islamic": False,
    "tenure_years": 3,
}

STORED_HISTORY = [
    {"role": "user", "content": "I need a personal loan", "slots_captured": {}},
    {
        "role": "assistant",
        "content": "Your top match is Alpha Bank.",
        "slots_captured": {**ACTIVE_STATE, "loan_request_id": 7},
    },
]


class ChatContextPassingTests(TestCase):
    """The agent must receive the stored transcript and the active loan
    request on every turn, whether or not the client re-sent them."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="owner@example.com",
            email="owner@example.com",
            password="pw-12345-xyz",
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.user)}"
        )

    def _post(self, payload):
        with (
            patch(
                "mcp_server.api.get_session_chat_history", return_value=STORED_HISTORY
            ),
            patch("mcp_server.api.save_chat_message"),
            patch(
                "mcp_server.api.run_chat_agent", return_value=AGENT_RESULT
            ) as run_agent,
        ):
            response = self.client.post("/api/chat/", payload, format="json")
        self.assertEqual(response.status_code, 200)
        return run_agent.call_args.args

    def test_follow_up_without_client_state_gets_the_stored_loan_request(self):
        args = self._post({"message": "show me lower price", "session_id": "abc"})

        message, history, state, _user, loan_request_id, _session_id = args
        self.assertEqual(message, "show me lower price")
        self.assertEqual(history, STORED_HISTORY)
        self.assertEqual(state, ACTIVE_STATE)
        self.assertEqual(loan_request_id, 7)

    def test_updated_state_and_loan_request_are_stored_for_the_next_turn(self):
        updated = {**ACTIVE_STATE, "tenure_years": 5}
        agent_result = {**AGENT_RESULT, "state": updated, "loan_request_id": 8}
        with (
            patch(
                "mcp_server.api.get_session_chat_history", return_value=STORED_HISTORY
            ),
            patch("mcp_server.api.save_chat_message") as save_message,
            patch("mcp_server.api.run_chat_agent", return_value=agent_result),
        ):
            response = self.client.post(
                "/api/chat/", {"message": "yes", "session_id": "abc"}, format="json"
            )

        self.assertEqual(response.data["state"], updated)
        self.assertEqual(response.data["loan_request_id"], 8)
        self.assertEqual(
            save_message.call_args_list[-1].kwargs["metadata"],
            {**updated, "loan_request_id": 8},
        )

    def test_values_sent_by_the_client_override_the_stored_ones(self):
        args = self._post(
            {
                "message": "show me lower price",
                "session_id": "abc",
                "state": {"tenure_years": 5, "required_amount": None},
                "loan_request_id": 9,
            }
        )

        self.assertEqual(args[2], {**ACTIVE_STATE, "tenure_years": 5})
        self.assertEqual(args[4], 9)


class ScriptedModel:
    """Stands in for the Groq chat model: replays canned responses in order
    and records the messages each call was given. A response may be a
    callable taking those messages, for replies that quote tool results."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.tools = []

    def bind_tools(self, tools):
        self.tools = tools
        return self

    def invoke(self, messages):
        self.calls.append(list(messages))
        response = self._responses.pop(0)
        return response(messages) if callable(response) else response


def _tool_call(name, args):
    return AIMessage(
        content="", tool_calls=[{"name": name, "args": args, "id": f"call-{name}"}]
    )


class FollowUpFlowTestCase(TestCase):
    """Shared setup for turns that follow a delivered first report: two
    personal-loan policies, the saved first LoanRequest, and a scripted run."""

    FIRST_SUMMARY = "Your top match is Alpha Bank at PKR 36,000 a month."

    def setUp(self):
        for name, profit_rate in (("Alpha Bank", 22.0), ("Beta Bank", 18.0)):
            bank = Bank.objects.create(
                name=name,
                is_islamic=False,
                main_page_url=f"https://{name.split()[0].lower()}.example.com",
            )
            LoanPolicy.objects.create(
                bank=bank,
                loan_type=LoanCategory.PERSONAL,
                min_income=50_000,
                max_dti_percentage=50,
                max_loan_amount=5_000_000,
                profit_rate=profit_rate,
                min_downpayment_percentage=0,
                max_tenure_years=7,
                is_islamic=False,
            )
        self.session_id = str(uuid.uuid4())
        self.history = [
            {"role": "user", "content": "I need a 10 lakh personal loan"},
            {"role": "assistant", "content": self.FIRST_SUMMARY},
        ]
        self.first_request = LoanRequest.objects.create(
            loan_type="personal",
            required_amount=1_000_000,
            monthly_income=200_000,
            is_islamic=False,
            desired_tenure_years=3,
        )

    def _run(self, message, responses):
        model = ScriptedModel(responses)
        with patch("mcp_server.agent.build_tool_calling_model", return_value=model):
            result = run_chat_agent(
                message,
                self.history,
                dict(ACTIVE_STATE),
                None,
                self.first_request.id,
                self.session_id,
            )
        return result, model

    def _eligibility_args(self, tenure_years):
        return {
            "monthly_income": 200_000,
            "required_amount": 1_000_000,
            "tenure_years": tenure_years,
            "loan_type": "Personal",
            "existing_loans": 0,
        }

    def _search_args(self):
        return {"loan_type": "Personal", "amount": 1_000_000, "is_islamic": False}

    def _result_of(self, result, tool_name):
        return next(
            call["result"] for call in result["tool_calls"] if call["name"] == tool_name
        )


class FollowUpAdjustmentFlowTests(FollowUpFlowTestCase):
    """A follow-up after the first report must recalculate from the active
    loan request and be answered in the model's own words."""

    def test_model_receives_history_and_active_loan_request(self):
        _result, model = self._run(
            "it is too much", [AIMessage(content="That is a heavy installment.")]
        )

        system, *turns = model.calls[0]
        self.assertIn('"tenure_years": 3', system.content)
        self.assertIn('"required_amount": 1000000', system.content)
        self.assertIn(FOLLOW_UP_NOTE.strip(), system.content)
        self.assertEqual(
            [(type(turn), turn.content) for turn in turns],
            [
                (HumanMessage, "I need a 10 lakh personal loan"),
                (AIMessage, self.FIRST_SUMMARY),
                (HumanMessage, "it is too much"),
            ],
        )

    def test_feedback_is_answered_with_the_models_own_words(self):
        result, _model = self._run(
            "it is too much", [AIMessage(content="That is a heavy installment.")]
        )

        self.assertEqual(result["reply"], "That is a heavy installment.")
        self.assertEqual(result["tool_calls"], [])
        self.assertEqual(result["loan_request_id"], self.first_request.id)

    def test_longer_tenure_is_recalculated_and_lowers_the_installment(self):
        baseline, _ = self._run(
            "what is my installment again?",
            [
                _tool_call("calculate_user_eligibility", self._eligibility_args(3)),
                AIMessage(content="Same as before."),
            ],
        )
        adjusted_reply = "Over 5 years the installment comes down."

        result, model = self._run(
            "show me lower price",
            [
                _tool_call("update_loan_state", {"tenure_years": 5}),
                _tool_call("calculate_user_eligibility", self._eligibility_args(5)),
                _tool_call("search_loans", self._search_args()),
                AIMessage(content=adjusted_reply),
            ],
        )

        self.assertEqual(result["reply"], adjusted_reply)
        self.assertNotEqual(result["reply"], self.FIRST_SUMMARY)
        self.assertEqual(result["state"]["tenure_years"], 5)
        self.assertLess(
            self._result_of(result, "calculate_user_eligibility")[
                "monthly_installment"
            ],
            self._result_of(baseline, "calculate_user_eligibility")[
                "monthly_installment"
            ],
        )
        self.assertEqual(result["report"]["kpis"]["tenure"], 5)
        # The model wrote its reply with the recalculated results in front of it.
        self.assertIn("predicted_matches", model.calls[-1][-1].content)

    def test_adjustment_is_saved_as_a_new_loan_request(self):
        result, _model = self._run(
            "make it 5 years",
            [
                _tool_call("update_loan_state", {"tenure_years": 5}),
                _tool_call("calculate_user_eligibility", self._eligibility_args(5)),
                _tool_call("search_loans", self._search_args()),
                AIMessage(content="Done."),
            ],
        )

        self.assertNotEqual(result["loan_request_id"], self.first_request.id)
        saved = LoanRequest.objects.get(pk=result["loan_request_id"])
        self.assertEqual(saved.desired_tenure_years, 5)
        self.assertEqual(str(saved.chat_session_id), self.session_id)

    def test_lowest_rate_request_gets_policies_ordered_by_profit_rate(self):
        result, _model = self._run(
            "which bank has the lowest interest?",
            [
                _tool_call("calculate_user_eligibility", self._eligibility_args(3)),
                _tool_call("search_loans", self._search_args()),
                AIMessage(content="Beta Bank has the lowest rate."),
            ],
        )

        policies = self._result_of(result, "search_loans")["policies"]
        self.assertEqual(
            [policy["bank_name"] for policy in policies], ["Beta Bank", "Alpha Bank"]
        )
        self.assertEqual(result["reply"], "Beta Bank has the lowest rate.")


def _search_payload(messages):
    """The search_loans context the model was shown on this call."""
    return next(
        json.loads(message.content)
        for message in reversed(messages)
        if isinstance(message, ToolMessage) and "predicted_matches" in message.content
    )


def _grounded_reply(messages):
    top = _search_payload(messages)["predicted_matches"][0]
    return AIMessage(
        content=(
            f"Good news: {top['bank_name']} is your best fit at "
            f"{top['profit_rate']}% with about PKR {top['estimated_emi']:,.0f} a month."
        )
    )


class FirstEvaluationGroundingTests(TestCase):
    """The first evaluation is written by the model, from the injected
    search_loans payload only — anything else falls back to the fixed summary."""

    def setUp(self):
        for name, profit_rate in (("Alpha Bank", 22.0), ("Beta Bank", 18.0)):
            bank = Bank.objects.create(
                name=name,
                is_islamic=False,
                main_page_url=f"https://{name.split()[0].lower()}.example.com",
            )
            LoanPolicy.objects.create(
                bank=bank,
                loan_type=LoanCategory.PERSONAL,
                min_income=50_000,
                max_dti_percentage=50,
                max_loan_amount=5_000_000,
                profit_rate=profit_rate,
                min_downpayment_percentage=0,
                max_tenure_years=7,
                is_islamic=False,
            )
        self.tool_calls = [
            _tool_call(
                "calculate_user_eligibility",
                {
                    "monthly_income": 200_000,
                    "required_amount": 1_000_000,
                    "tenure_years": 3,
                    "loan_type": "Personal",
                    "existing_loans": 0,
                },
            ),
            _tool_call(
                "search_loans",
                {"loan_type": "Personal", "amount": 1_000_000, "is_islamic": False},
            ),
        ]

    def _run(self, responses):
        model = ScriptedModel(responses)
        with patch("mcp_server.agent.build_tool_calling_model", return_value=model):
            result = run_chat_agent(
                "3 years please",
                [{"role": "user", "content": "I need a 10 lakh personal loan"}],
                dict(ACTIVE_STATE),
                None,
                None,
                str(uuid.uuid4()),
            )
        return result, model

    def _fixed_summary(self):
        """What the app sends when it rejects the model's own reply."""
        result, _model = self._run([*self.tool_calls, AIMessage(content="")])
        return result["reply"]

    def test_grounded_model_reply_is_sent_as_written(self):
        result, model = self._run([*self.tool_calls, _grounded_reply])

        self.assertTrue(result["reply"].startswith("Good news: "))
        self.assertNotEqual(result["reply"], self._fixed_summary())
        self.assertIsNotNone(result["report"])
        self.assertIsNotNone(result["loan_request_id"])
        payload = _search_payload(model.calls[-1])
        self.assertIn("grounding_rule", payload)
        self.assertNotIn("policies", payload)

    def test_fabricated_installment_falls_back_to_the_fixed_summary(self):
        fabricated = "Alpha Bank is your best fit at about PKR 12,345 a month."

        result, _model = self._run([*self.tool_calls, AIMessage(content=fabricated)])

        self.assertEqual(result["reply"], self._fixed_summary())

    def test_fabricated_profit_rate_falls_back_to_the_fixed_summary(self):
        fabricated = "Beta Bank is your best fit at a 9.5% profit rate."

        result, _model = self._run([*self.tool_calls, AIMessage(content=fabricated)])

        self.assertEqual(result["reply"], self._fixed_summary())

    def test_reply_naming_no_matched_bank_falls_back_to_the_fixed_summary(self):
        fabricated = "Gamma Bank is your best fit — a great choice."

        result, _model = self._run([*self.tool_calls, AIMessage(content=fabricated)])

        self.assertEqual(result["reply"], self._fixed_summary())

    def test_model_that_skips_the_tools_is_given_the_real_results(self):
        result, model = self._run(
            [AIMessage(content="I have generated your report!"), _grounded_reply]
        )

        self.assertTrue(result["reply"].startswith("Good news: "))
        self.assertEqual(
            [call["name"] for call in result["tool_calls"]],
            ["calculate_user_eligibility", "search_loans"],
        )
        self.assertNotIn(
            "I have generated your report!",
            [message.content for message in model.calls[-1]],
        )

    def test_system_prompt_forbids_fabricated_banks_and_figures(self):
        _result, model = self._run([*self.tool_calls, _grounded_reply])

        system_prompt = model.calls[0][0].content
        self.assertIn("Never fabricate", system_prompt)
        self.assertIn("only source of truth", system_prompt)


class AmbiguousConfirmationTests(FollowUpFlowTestCase):
    """A brief go-ahead after options were offered must be acted on, with the
    recalculated loan request saved and carried forward."""

    OPTIONS_OFFERED = (
        "That installment is heavy. I would stretch the tenure to 5 years "
        "first; we could also lower the amount. Shall I run it?"
    )

    def setUp(self):
        super().setUp()
        self.history = [
            *self.history,
            {"role": "user", "content": "it is too much"},
            {"role": "assistant", "content": self.OPTIONS_OFFERED},
        ]

    def test_brief_go_aheads_get_the_no_clarifying_question_note(self):
        for message in ("yeh give me", "yes", "do it", "sure", "apply this"):
            with self.subTest(message=message):
                _result, model = self._run(message, [AIMessage(content="On it.")])

                self.assertIn(CONFIRMATION_NOTE.strip(), model.calls[0][0].content)

    def test_a_specific_request_does_not_get_the_confirmation_note(self):
        _result, model = self._run(
            "what documents will the bank want from me for this loan?",
            [AIMessage(content="Your CNIC and salary slips.")],
        )

        self.assertNotIn(CONFIRMATION_NOTE.strip(), model.calls[0][0].content)

    def test_system_prompt_forbids_re_asking_after_a_go_ahead(self):
        _result, model = self._run("yes", [AIMessage(content="On it.")])

        system_prompt = model.calls[0][0].content
        self.assertIn("MUST NOT ask which option they meant", system_prompt)
        self.assertIn("or to 5 years if you gave none", system_prompt)

    def test_confirmed_tenure_extension_is_recalculated_and_saved(self):
        result, _model = self._run(
            "yeh give me",
            [
                _tool_call("update_loan_state", {"tenure_years": 5}),
                _tool_call("calculate_user_eligibility", self._eligibility_args(5)),
                _tool_call("search_loans", self._search_args()),
                AIMessage(content="Done, over 5 years it is lighter with Beta Bank."),
            ],
        )

        self.assertEqual(
            result["reply"], "Done, over 5 years it is lighter with Beta Bank."
        )
        self.assertEqual(result["state"], {**ACTIVE_STATE, "tenure_years": 5})
        self.assertEqual(result["report"]["kpis"]["tenure"], 5)
        self.assertNotEqual(result["loan_request_id"], self.first_request.id)
        self.assertEqual(
            LoanRequest.objects.get(
                pk=result["loan_request_id"]
            ).desired_tenure_years,
            5,
        )

    def test_state_change_without_a_search_is_still_recalculated(self):
        result, model = self._run(
            "yes",
            [
                _tool_call("update_loan_state", {"tenure_years": 5}),
                AIMessage(content="I have updated it for you."),
                AIMessage(content="Over 5 years Beta Bank comes out lighter."),
            ],
        )

        self.assertEqual(result["reply"], "Over 5 years Beta Bank comes out lighter.")
        self.assertEqual(
            [call["name"] for call in result["tool_calls"]],
            ["update_loan_state", "calculate_user_eligibility", "search_loans"],
        )
        self.assertEqual(result["report"]["kpis"]["tenure"], 5)
        self.assertEqual(
            self._result_of(result, "calculate_user_eligibility")["monthly_installment"],
            json.loads(model.calls[-1][-2].content)["monthly_installment"],
        )


class OutOfScopeGuardrailTests(FollowUpFlowTestCase):
    """General-knowledge and other off-topic queries get the model's own
    polite decline — never an answer, a report, or the loan summary."""

    DECLINE = (
        "That one is outside my lane, I'm afraid — I'm specialised as a loan "
        "strategy advisor, so I can't help with politics. Shall we get back "
        "to your PKR 1,000,000 personal loan, or look at something from 2026?"
    )
    OFF_TOPIC_QUERIES = (
        "who is prime minister of Pakistan",
        "write me a python script to sort a list",
        "who won the cricket world cup in 1992?",
    )

    def _decline_script(self):
        return [
            _tool_call("flag_out_of_scope", {"topic": "general knowledge"}),
            AIMessage(content=self.DECLINE),
        ]

    def _run_fresh(self, message, state):
        """A turn on a session with no report delivered yet."""
        model = ScriptedModel(self._decline_script())
        with patch("mcp_server.agent.build_tool_calling_model", return_value=model):
            result = run_chat_agent(
                message, [], dict(state), None, None, str(uuid.uuid4())
            )
        return result, model

    def test_general_knowledge_queries_get_a_polite_decline(self):
        for message in self.OFF_TOPIC_QUERIES:
            with self.subTest(message=message):
                result, _model = self._run(message, self._decline_script())

                self.assertEqual(result["reply"], self.DECLINE)
                self.assertEqual(
                    [call["name"] for call in result["tool_calls"]],
                    ["flag_out_of_scope"],
                )
                self.assertIsNone(result["report"])
                self.assertEqual(result["state"], ACTIVE_STATE)
                self.assertEqual(result["loan_request_id"], self.first_request.id)

    def test_decline_is_not_replaced_by_the_loan_summary_before_a_first_report(self):
        result, model = self._run_fresh(self.OFF_TOPIC_QUERIES[0], ACTIVE_STATE)

        self.assertEqual(result["reply"], self.DECLINE)
        self.assertIsNone(result["report"])
        self.assertEqual(
            [call["name"] for call in result["tool_calls"]], ["flag_out_of_scope"]
        )
        self.assertEqual(len(model.calls), 2)

    def test_decline_on_a_brand_new_session_starts_no_slot_filling(self):
        result, _model = self._run_fresh(self.OFF_TOPIC_QUERIES[0], {})

        self.assertEqual(result["reply"], self.DECLINE)
        self.assertIsNone(result["loan_request_id"])
        self.assertTrue(all(value is None for value in result["state"].values()))

    def test_unflagged_decline_on_a_follow_up_is_sent_as_written(self):
        result, _model = self._run(
            self.OFF_TOPIC_QUERIES[0], [AIMessage(content=self.DECLINE)]
        )

        self.assertEqual(result["reply"], self.DECLINE)
        self.assertEqual(result["tool_calls"], [])

    def test_model_is_given_the_scope_rule_and_the_flag_tool(self):
        _result, model = self._run(self.OFF_TOPIC_QUERIES[0], self._decline_script())

        system_prompt = model.calls[0][0].content
        self.assertIn("EXCLUSIVELY a loan strategy, banking", system_prompt)
        self.assertIn("you MUST politely decline", system_prompt)
        self.assertIn("never reuse a stock refusal line", system_prompt)
        self.assertIn("flag_out_of_scope", [tool["name"] for tool in model.tools])
