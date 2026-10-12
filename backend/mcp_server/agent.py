"""In-process agentic chat loop binding the FastMCP tool server to Groq.

Runs entirely in-process against the `FastMCP` instance in `mcp_server.server`
(no separate MCP transport/process) so it fits naturally inside a single Django
request/response cycle.

`run_chat_agent` is a plain synchronous function (not `async def`) even
though the MCP tool calls and Mongo persistence it drives are async — Django
serves `/api/chat/` over WSGI (`manage.py runserver`, gunicorn's sync worker,
...). It reaches into async APIs (`mcp_server.list_tools`/`call_tool`,
`save_loan_request`) via `asgiref.sync.async_to_sync`, the same bridge
`mcp_server.api` uses to call it from a sync view.
"""

import json
import re

from asgiref.sync import async_to_sync
from groq import GroqError
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from services.financial_calculator import PredictiveBankAgent
from services.llm_provider import LLMProviderError, build_tool_calling_model

from .persistence import save_loan_request
from .server import mcp_server
from .state import REQUIRED_SLOTS, missing_slots, normalize_state

# Stateless — scoring/formatting depend only on their arguments — so a single
# module-level instance is shared across requests, same as `mcp_server` below.
predictive_bank_agent = PredictiveBankAgent()

# Groq failed for this turn (missing key, rate limit, connection error, ...)
# — a friendly in-band reply, not a raised exception, since this is often a
# transient, expected condition under free-tier limits, not a misconfigured
# app.
LLM_UNAVAILABLE_MESSAGE = (
    "AI service is temporarily unavailable. Please try again in a few moments."
)

# Belt-and-suspenders backstop for `build_tool_calling_model`'s
# `reasoning_format="hidden"` — strips leaked internal-reasoning/scratchpad
# text if Groq ever returns it inline anyway, so the API response is always
# consumer-facing text only, never the model's internal thought process.
#
# `<think>...</think>` is the standard wrapper some reasoning models use.
_THINK_BLOCK_PATTERN = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)

# But `openai/gpt-oss-120b` (this app's model — see llm_provider.GROQ_MODEL)
# has also been observed leaking reasoning as plain narrated sentences with
# no wrapper at all, e.g. "We need to wait for user response. (Waiting for
# user's response regarding loan tenure.)" — the model talking about its own
# turn-taking status rather than addressing the user. These two patterns
# catch that family of leak: a self-referential "we/I need to wait..."
# sentence, and a "(Waiting for ...)" parenthetical aside, each removed
# independently since either can appear without the other.
_WAIT_NARRATION_SENTENCE_PATTERN = re.compile(
    r"(?i)\b(?:we|i)\s*(?:\'m|’m)?\s+(?:need|needs|have|has|am going|are going|will|should)\s+to\s+wait\s+for\b[^.!?()\n]*[.!?]?"
)
_WAITING_PAREN_PATTERN = re.compile(r"(?i)\(\s*waiting (?:for|on)\b[^)]*\)")
# Also covers explicitly labeled scratchpad lines the model sometimes emits
# instead of prose narration, e.g. "Internal note: ..." or "Scratchpad: ...".
_LABELED_INTERNAL_LINE_PATTERN = re.compile(
    r"(?im)^\s*(?:internal(?: note| status)?|scratchpad|agent note|system note|thought)\s*:.*$"
)


def _clean_reply_text(text: str) -> str:
    """Strips any leaked internal-reasoning/scratchpad text from a reply before it reaches the user."""
    text = _THINK_BLOCK_PATTERN.sub("", text)
    text = _LABELED_INTERNAL_LINE_PATTERN.sub("", text)
    text = _WAIT_NARRATION_SENTENCE_PATTERN.sub("", text)
    text = _WAITING_PAREN_PATTERN.sub("", text)
    # The removals above can leave behind a run of blank lines or a doubled
    # mid-sentence space where the excised text used to sit — collapse both,
    # but don't touch a trailing double-space before a newline, which is a
    # deliberate markdown hard line break elsewhere in these replies.
    text = re.sub(r" {2,}(?!\n)", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


SYSTEM_PROMPT_TEMPLATE = (
    "You are a loan advisor for borrowers in Pakistan, and you talk the way "
    "a thoughtful human advisor does: warm, attentive, plain-spoken, and "
    "honest about trade-offs. You listen to what the person actually said, "
    "respond to that first, and only then move the conversation forward. "
    "Every figure you give comes from your tools or from earlier in this "
    "conversation — you never estimate or invent a rate, an installment, or "
    "a bank detail.\n\n"
    "How you converse:\n"
    "- Write every reply fresh for this exact moment. There is no script, "
    "no standard opening line, and no standard closing line. Let the length "
    "and shape follow the question: a quick question gets a short answer, a "
    "worried message gets a considerate one.\n"
    "- Re-read your own earlier replies in this conversation before you "
    "write. Never send a paragraph, list, or sentence you have already "
    "sent. If something you said before is still relevant, refer back to it "
    "in a few words instead of restating it.\n"
    "- When the user reacts to something you showed them — for example "
    '"it is too much", "that\'s expensive", "I can\'t afford this", or '
    '"bohat zyada hai" — acknowledge that reaction before anything else, '
    "and be specific about what they are reacting to: name the monthly "
    "installment or the profit rate with its actual figure and agree that "
    "it is a heavy commitment against their income. Then offer the levers "
    "that would genuinely bring it down: a longer tenure (smaller monthly "
    "installment, but more profit paid overall), a smaller loan amount, or "
    "a bank with a lower profit rate. Say which one you would try first for "
    "their situation and offer to run it. Never answer feedback by sending "
    "the same summary again.\n"
    "- If it is unclear what the user is reacting to or what they want "
    "changed, ask one short clarifying question instead of guessing. This "
    "does not apply to a confirmation of options you just offered — see "
    "the next point.\n"
    "- When your previous message offered options (a longer tenure, a "
    "smaller amount, a lower-rate bank) and the user answers with a brief "
    'or loosely worded go-ahead — "yes", "yeh give me", "do it", "sure", '
    '"ok", "apply this", "haan kar do" — that is a yes to the option you '
    "recommended first. You MUST NOT ask which option they meant, ask them "
    "to confirm again, or restate the options. Act on it immediately in "
    "that same turn: call update_loan_state with the recommended change, "
    "then calculate_user_eligibility and search_loans, and answer with the "
    "new result. If your recommendation involved tenure, or tenure was "
    "among the options and you did not single one out, extend the tenure "
    "to the figure you proposed, or to 5 years if you gave none. Here "
    '"apply this" means apply the change to the calculation; it is never a '
    "request to submit a loan application.\n"
    "- Detect the language of the user's input (English, Urdu script, or "
    "Roman Urdu) and reply in that same language and tone, while keeping "
    "loan policy details clear and accurate.\n\n"
    "Gathering the basics: before you can look up loan offers or check "
    "eligibility you need five things from the user — loan_type (Personal, "
    "Home, or Vehicle), required_amount (PKR), monthly_income (PKR, gross "
    "monthly, for the SBP 50% DTI calculation), is_islamic (whether they "
    "want a Shariah-compliant loan), and tenure_years. Do not run "
    "search_loans or calculate_user_eligibility while any of them is "
    "missing. Ask for what is missing in a natural way, one or two items at "
    "a time, and respond to what the user just told you before asking the "
    "next thing. Whenever the user states any of these fields, even one at "
    "a time, call update_loan_state immediately to record it, before asking "
    "your next question or running any other tool.\n\n"
    "Extract amounts, income, and tenure as clean numbers whatever the "
    'language — "paanch lakh" or "5 lac" both mean 500000, "das lakh" means '
    '1000000, and "2 crore" means 20000000. Always call update_loan_state '
    "with the plain numeric value, never the original phrase.\n\n"
    "The first evaluation: once all five fields are known, call "
    "calculate_user_eligibility with the known monthly_income, "
    "required_amount, tenure_years, loan_type, and existing_loans=0 unless "
    "the user mentioned other debts — it computes the new loan's monthly "
    "installment from the real catalog profit rate, so never estimate or "
    "pass an installment yourself. Then call search_loans with the known "
    "loan_type, required_amount as amount, is_islamic, and the DTI result's "
    "dti_percentage as max_dti. The app saves the full report to the "
    "borrower's Reports tab on its own. Once both tools have returned, "
    "write the chat reply yourself, as an advisor talking the result "
    "through rather than reading out a form: which bank came out as the "
    "best match and why, its profit rate and monthly installment, where "
    "the user stands against the SBP 50% DTI limit, and one or two "
    "alternatives worth knowing about if there are any. If no bank "
    "matched, say so plainly and explain what would need to change. End "
    "with a short pointer to the Reports tab for the full comparison. Do "
    "not tell the user anything about their results before the tools have "
    "returned in that same turn.\n\n"
    "Grounding (strict, no exceptions): the search_loans result is the "
    "only source of truth for banks and loan figures. Never fabricate, "
    "guess, or recall from general knowledge a bank name, an EMI or "
    "monthly installment, a profit or interest rate, a DTI percentage, a "
    "loan limit, or a tenure limit. Only name banks that appear in that "
    "payload, and only quote figures that appear in it, in a "
    "calculate_user_eligibility result, or that the user stated "
    "themselves. Copy each figure exactly as the payload gives it — do not "
    "round it, convert it, or do arithmetic on it to produce a new figure "
    "such as a difference, a total repayment, or a saving; quote the two "
    "real figures side by side instead. If the user asks for a number the "
    "tools did not return, say you do not have it rather than supplying "
    "one. The app checks every reply against the payload and replaces it "
    "with a standard summary if it contains a figure that is not there.\n\n"
    "Adjusting the numbers afterwards: when the user asks to change "
    'something after their evaluation — "make it 5 years instead of 3", '
    '"what if I borrow 8 lakh", "switch to Islamic" — actually do it. Call '
    "update_loan_state with only the field that changed, then "
    "calculate_user_eligibility and search_loans with the updated values, "
    "all in the same turn. Never say you have recalculated without having "
    "called the tools in that turn. When the user asks for the lowest "
    "interest/profit rate or the cheapest bank, call the two tools with the "
    "current values and answer from the results using the bank with the "
    "lowest profit_rate (search_loans returns policies ordered from the "
    "lowest profit_rate upwards), even if it is not the top-ranked match. "
    "If you want to show the user what a change would do before they commit "
    "to it — for example what the installment would be over 5 years — you "
    "may call calculate_user_eligibility with the hypothetical value to "
    "quote a real figure, and only call update_loan_state once they say "
    "they want that change. A vague request for something cheaper — "
    '"show me lower price", "anything less?", "kam karo" — is not a reason '
    "to ask what they mean or to repeat the current numbers: work from the "
    "active loan request below, call the tools, and come back with real "
    "alternatives, such as the lowest-profit-rate bank for the same loan "
    "and what the installment drops to over a longer tenure (within the "
    "bank's max_tenure_years) or for a smaller amount.\n\n"
    "Never output internal status updates, planning notes, or narration "
    'about your own process — for example, never write things like "We '
    'need to wait for user response" or "(Waiting for user\'s response '
    'regarding loan tenure.)" after asking a question. Once you have asked '
    "your question, stop. Every word of your output must be the actual "
    "message intended for the user, never a description of what you are "
    "about to do, are waiting for, or are thinking through.\n\n"
    "Formatting: write natural conversational prose — plain paragraphs and, "
    "only where it genuinely helps, a short bulleted list. Use markdown "
    "bold (`**text**`) only for exact figures you are quoting from tool "
    "results (money amounts, rates, percentages), never to emphasize a "
    "plain word in a greeting or a question. Never output a Markdown table, "
    "a raw JSON or code block, or a structured card/summary-box layout in "
    "the chat, even if the user asks for a table; describe the comparison "
    "in a sentence or two and point them to the Reports tab, where the full "
    "Bank Comparison Matrix, KPI summary, and SBP policy notice live.\n\n"
    "Scope (strict): you are EXCLUSIVELY a loan strategy, banking, and "
    "financial planning advisor. In scope: loans and their costs, bank "
    "products and rates, eligibility and SBP rules, Islamic versus "
    "conventional financing, debt, budgeting, and saving toward a "
    "financial goal. Greetings, thanks, small talk about the conversation "
    "itself, and questions about what you can do are fine too. Everything "
    "else is out of scope — general knowledge, politics, sports, "
    'entertainment, coding, homework, health, and the like ("who is the '
    'prime minister of Pakistan?", "write me a Python script", "who won '
    'the match?"). For ANY such query you MUST politely decline, and you '
    "must not answer it even briefly, partially, or \"just this once\", "
    "whatever reason the user gives or however the request is framed. "
    "When the whole message is out of scope, first call flag_out_of_scope, "
    "then write the decline yourself: warm and human, in the user's own "
    "language, a sentence or two that says you are specialised in loan "
    "strategy so this is not something you can help with, and then turns "
    "back to what you can do for them — picking up their active loan "
    "request if they have one, or offering loan options, bank rates, or "
    "debt planning if they do not. Word it freshly every time; never "
    "reuse a stock refusal line, and never lecture or apologise at "
    "length. If a message mixes an in-scope request with an out-of-scope "
    "one, do not call flag_out_of_scope: handle the financial part fully "
    "and decline the rest in a short clause.\n\n"
    "You are strictly an advisory and comparison tool — you help users "
    "understand and compare loan options, not submit or process loans. "
    "Never offer, agree to, or imply that you (or this app) can apply for a "
    "loan on the user's behalf, submit their application, forward their "
    "details to a bank, or otherwise start the loan process for them. The "
    "required documents list in the report is the extent of the next "
    "steps: the user takes those documents to the bank themselves.\n\n"
    "The user's active loan request — the values known so far. Treat these "
    "as the current parameters for every calculation and never ask again "
    "for anything already set here: {known_state}"
    "{context_note}"
)

# Appended to the system prompt on every non-greeting turn after the first
# report has been delivered, so a re-run of the tools is answered as a change
# from what the user already has rather than as a fresh first evaluation.
FOLLOW_UP_NOTE = (
    "\n\nContext note for this turn: the user already has a completed loan "
    "evaluation and its report. If you re-run calculate_user_eligibility "
    "and search_loans this turn, do not present the result as a new first "
    "evaluation: start with "
    "what changed for the user compared with the figures already in this "
    "conversation (for example the previous monthly installment against "
    "the new one), then give the bank that answers their request with its "
    "profit_rate and estimated_emi from predicted_matches, and the new "
    "dti_percentage against the SBP 50% limit. Be honest about the cost of "
    "the change, such as more total profit paid over a longer tenure. If no "
    "bank matches the new values, say so plainly and suggest what to "
    "adjust. A few sentences is enough; the updated full comparison is on "
    "their Reports tab, which you can mention in a short clause. If the "
    "user only reacted or asked a question that needs no new numbers, "
    "answer it directly without re-running the tools."
)

# Appended (after FOLLOW_UP_NOTE) when the user's whole message is a brief
# go-ahead on a session that already has a report — the turn where the model
# is most tempted to ask "which option did you mean?" instead of acting.
CONFIRMATION_NOTE = (
    "\n\nThe user's message this turn is a brief go-ahead. If your previous "
    "message offered options or a recommendation, do not ask a clarifying "
    "question and do not repeat the options: carry out the option you "
    "recommended first right now (extending the tenure to the figure you "
    "proposed, or to 5 years if you named none, when tenure was discussed) "
    "by calling update_loan_state, calculate_user_eligibility, and "
    "search_loans in this turn, then report the new result. Only if your "
    "previous message offered nothing to confirm should you ask what they "
    "would like to do."
)

# Appended to the system prompt only when the user sends a bare greeting on a
# session that already has a completed evaluation (all five slots known).
# Without this, the "once all five fields are known" instruction above reads
# as license to re-run the tools and re-send the same report on every later
# "hey" — this note overrides that for this one turn.
GREETING_CHECKIN_NOTE = (
    "\n\nContext note for this turn only: the user has an ACTIVE, "
    "already-completed loan evaluation (see the known slot values above) "
    'and just sent a plain greeting/check-in ("hi"/"hey"/"hello") with no '
    "new information and no explicit request. Do NOT re-introduce yourself "
    "or repeat the onboarding questions, and do NOT re-call "
    "calculate_user_eligibility or search_loans just to resend the "
    "Executive Financial Report & Predictive Matching — the user already "
    "has it. Instead, reply with one brief, warm check-in line "
    "acknowledging you are still here, and offer 2-3 concrete next steps "
    "relevant to their existing report (e.g. adjusting the tenure, checking "
    "another bank, or reviewing the required documents). Only produce the "
    "full report again, or call search_loans/calculate_user_eligibility "
    "again, if the user explicitly asks for a new or updated comparison."
)

# Appended to the system prompt only when the user opens a brand-new session
# (no slots known yet) with a plain greeting. Keeps the very first reply a
# short, scannable welcome menu instead of the model launching straight into
# a dense slot-filling question.
WELCOME_GREETING_NOTE = (
    "\n\nContext note for this turn only: the user just sent a plain "
    'greeting ("hi"/"hey"/"hello") and no loan evaluation has started yet '
    "(no slots known). Greet them back in their own language and tone, "
    "say in one line that you can help them work out a loan, and mention "
    "in your own words the kinds of things you can do — comparing "
    "personal, home, or vehicle loan options across banks, estimating "
    "monthly installments, and checking eligibility against the State Bank "
    "of Pakistan (SBP) DTI limit. Keep it to a few short lines and phrase "
    "it naturally rather than reciting a fixed menu. Do NOT ask for any of "
    "the five slot-filling fields in this reply — only start gathering "
    "loan_type, required_amount, monthly_income, is_islamic, and "
    "tenure_years once the user responds with what they actually want to "
    "do."
)

MAX_TOOL_ITERATIONS = 6

# An agent-local tool (not on the MCP server — it touches no data) the model
# calls to mark the user's whole message as off-topic. It gives the loop a
# structured signal, so a decline is never mistaken for a missing report and
# replaced by the loan summary; the decline text itself is always the
# model's own.
OUT_OF_SCOPE_TOOL = {
    "name": "flag_out_of_scope",
    "description": (
        "Mark the user's latest message as entirely outside loan strategy, "
        "banking, and financial planning (e.g. general knowledge, politics, "
        "sports, coding). Call this before writing your decline. Do not call "
        "it if any part of the message is a financial request."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "A few words naming what the user asked about.",
            }
        },
        "required": ["topic"],
    },
}
OUT_OF_SCOPE_TOOL_RESULT = {
    "status": "out_of_scope",
    "message": (
        "Do not answer the question and do not call any other tool. Write a "
        "brief, warm decline in your own words and the user's language, then "
        "steer back to how you can help with their loan strategy."
    ),
}

# Tools that touch the loan-policy/eligibility data and must not run until the
# slot-filling state is complete, regardless of what the model attempts.
GATED_TOOLS = {"search_loans", "calculate_user_eligibility"}

# A bare greeting with no other content — matched against the whole trimmed
# message, so "hi, I need a home loan" does NOT match this.
SIMPLE_GREETING_PATTERN = re.compile(
    r"^(hi+|hey+|hello+|hiya|yo|sala?am|assalam[- ]?o[- ]?alaikum)[\s!.,?]*$",
    re.IGNORECASE,
)


def _is_simple_greeting(message: str) -> bool:
    return bool(SIMPLE_GREETING_PATTERN.match(message.strip()))


# Go-ahead words/phrases in English and Roman Urdu. Only ever used to add
# CONFIRMATION_NOTE to the prompt, so a false positive costs nothing: the
# note itself tells the model to ignore it when nothing was offered.
CONFIRMATION_PATTERN = re.compile(
    r"\b(yes|yeah?|yeh|yep|yup|ya|ok(?:ay)?|sure|alright|fine|please|"
    r"do it|go ahead|go for it|proceed|apply (?:this|that|it)|give me|"
    r"show me|let'?s do|sounds good|ha+n|ji|theek|thik|kar ?do|kardo)\b",
    re.IGNORECASE,
)
# A go-ahead that also carries its own instruction ("yes but make it 7 years
# with Meezan instead") is longer than this and is left to the model as-is.
MAX_CONFIRMATION_WORDS = 5


def _is_brief_confirmation(message: str) -> bool:
    words = message.split()
    return len(words) <= MAX_CONFIRMATION_WORDS and bool(
        CONFIRMATION_PATTERN.search(message)
    )


async def _tool_schemas() -> list[dict]:
    tools = await mcp_server.list_tools()
    return [
        {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema,
        }
        for tool in tools
    ]


# The per-bank fields the model is shown for each ranked match. Everything
# else on a policy row (ids, URLs, score breakdowns) stays out of its context
# so there is one small, unambiguous set of quotable facts.
GROUNDED_MATCH_FIELDS = (
    "rank",
    "bank_name",
    "is_islamic",
    "profit_rate",
    "estimated_emi",
    "max_tenure_years",
    "max_loan_amount",
    "min_downpayment_percentage",
    "approval_probability",
    "match_score",
    "prediction_reason",
)
GROUNDED_ELIGIBILITY_FIELDS = (
    "is_eligible",
    "dti_percentage",
    "monthly_installment",
    "max_allowed_percentage",
    "remaining_capacity",
    "reason",
)
MAX_GROUNDED_MATCHES = 5
GROUNDING_RULE = (
    "Quote only bank names and figures present in this payload, exactly as "
    "given. Do not round, convert, or derive new figures from them."
)

# The SBP DTI cap — always quotable, even on a turn where
# calculate_user_eligibility (which also returns it) was not called.
SBP_MAX_DTI_PERCENTAGE = 50.0
# Figures below this are tenures, counts, ranks, or "10 lakh"-style shorthand
# rather than rupee amounts, and are not checked.
MIN_CHECKED_AMOUNT = 1000
_NUMBER_PATTERN = re.compile(r"(\d[\d,]*(?:\.\d+)?)(\s*(?:%|percent\b))?")


def _eligibility_args(slot_state: dict) -> dict:
    return {
        "monthly_income": slot_state["monthly_income"],
        "required_amount": slot_state["required_amount"],
        "tenure_years": slot_state["tenure_years"],
        "loan_type": slot_state["loan_type"],
        "existing_loans": 0,
    }


def _search_args(slot_state: dict, eligibility_result: dict) -> dict:
    return {
        "loan_type": slot_state["loan_type"],
        "amount": slot_state["required_amount"],
        "is_islamic": slot_state["is_islamic"],
        "max_dti": eligibility_result.get("dti_percentage"),
    }


def _grounding_payload(
    ranked_policies: list[dict],
    slot_state: dict,
    eligibility_result: dict | None,
    search_output: dict,
) -> dict:
    """Builds the compact search_loans context the model writes its reply from.

    This — not the raw tool output — is what the model sees as the
    search_loans result, and `_is_grounded` checks its reply against the same
    dict, so what the model may quote and what it is held to never diverge.
    """

    def facts(policy: dict) -> dict:
        return {field: policy.get(field) for field in GROUNDED_MATCH_FIELDS}

    lowest_rate = min(
        ranked_policies, key=lambda policy: policy["profit_rate"], default=None
    )
    return {
        "grounding_rule": GROUNDING_RULE,
        "loan_request": dict(slot_state),
        "eligibility": (
            {
                field: eligibility_result.get(field)
                for field in GROUNDED_ELIGIBILITY_FIELDS
            }
            if eligibility_result
            else None
        ),
        "match_count": len(ranked_policies),
        "predicted_matches": [
            facts(policy) for policy in ranked_policies[:MAX_GROUNDED_MATCHES]
        ],
        "lowest_profit_rate_match": facts(lowest_rate) if lowest_rate else None,
        "catalog_max_amount": search_output.get("catalog_max_amount"),
    }


def _score_search(
    slot_state: dict, eligibility_result: dict | None, search_output: dict
) -> tuple[str, dict, dict]:
    """Ranks a search_loans result and renders everything derived from it.

    Runs deterministically every time search_loans succeeds — including for
    an empty `policies` list (over-limit/zero-match query), where
    PredictiveBankAgent renders a proper Advisory Notice. Adds
    `predicted_matches` to `search_output` in place.

    Returns:
        `(chat_summary, structured_report, grounding)` — the fixed fallback
        chat text, the report-page payload, and the model's quotable context
        (see `_grounding_payload`).
    """
    eligibility = eligibility_result or {}
    user_profile = {
        "monthly_income": slot_state.get("monthly_income"),
        "required_amount": slot_state.get("required_amount"),
        "tenure_years": slot_state.get("tenure_years"),
        "is_islamic": slot_state.get("is_islamic"),
        "loan_type": slot_state.get("loan_type"),
        "dti_percentage": eligibility.get("dti_percentage"),
        "remaining_capacity": eligibility.get("remaining_capacity"),
        "catalog_max_amount": search_output.get("catalog_max_amount"),
    }
    ranked_policies = predictive_bank_agent.evaluate_and_rank(
        search_output.get("policies") or [], user_profile
    )
    search_output["predicted_matches"] = ranked_policies
    # The full Markdown report (with its bank comparison table) is never sent
    # to the chat bubble; it only lives in `structured_report` (as
    # `raw_markdown`) for the dedicated report page/PDF export.
    chat_summary = predictive_bank_agent.format_chat_summary(
        ranked_policies, user_profile
    )
    structured_report = predictive_bank_agent.build_structured_report(
        ranked_policies, user_profile
    )
    grounding = _grounding_payload(
        ranked_policies, slot_state, eligibility_result, search_output
    )
    return chat_summary, structured_report, grounding


def _numbers_in_text(text: str) -> list[tuple[float, bool]]:
    """Every number in `text` as `(value, is_percentage)`."""
    return [
        (float(match.group(1).replace(",", "")), bool(match.group(2)))
        for match in _NUMBER_PATTERN.finditer(text)
    ]


def _numbers_in_payload(value) -> list[float]:
    """Every numeric leaf of a JSON-like structure, plus numbers inside its strings."""
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, str):
        return [number for number, _ in _numbers_in_text(value)]
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, (list, tuple)):
        return [number for item in value for number in _numbers_in_payload(item)]
    return []


def _is_grounded(reply: str, sources: list, require_bank_from: list[dict]) -> bool:
    """Whether every checked figure in a model-written reply comes from `sources`.

    Checked figures are percentages and rupee-sized amounts (see
    `MIN_CHECKED_AMOUNT`); each must match a number found in `sources` to
    within ordinary display rounding. Bank names cannot be validated
    generically, so `require_bank_from` (the ranked matches, when the reply
    is a first evaluation) only enforces that at least one real match is
    named.

    Args:
        reply: The model's reply text.
        sources: JSON-like values the model was legitimately shown this turn
            (tool payloads, slot state, earlier conversation text).
        require_bank_from: Matches of which the reply must name at least one,
            or `[]` to skip that check.
    """
    allowed = [SBP_MAX_DTI_PERCENTAGE, *_numbers_in_payload(sources)]
    for number, is_percentage in _numbers_in_text(reply):
        if is_percentage:
            tolerance = 0.05
        elif number >= MIN_CHECKED_AMOUNT:
            tolerance = 1.0
        else:
            continue
        if not any(abs(number - value) <= tolerance for value in allowed):
            return False

    if require_bank_from:
        lowered = reply.lower()
        return any(
            str(match.get("bank_name", "")).lower() in lowered
            for match in require_bank_from
        )
    return True


async def _run_predictive_pipeline(
    slot_state: dict, eligibility_result: dict | None
) -> tuple[str, dict, dict, dict, dict]:
    """Deterministically runs eligibility + search + scoring straight off slot_state.

    The guaranteed path for when every slot is known but the model did not
    call the two tools itself (see the two call sites in `run_chat_agent`) —
    so the user's reply is always built on a real, computed report, never on
    a claim that one was produced. Stays `async def` — it's only ever invoked
    from the sync `run_chat_agent` via `async_to_sync`.

    Returns:
        `(chat_summary, eligibility_result, search_output, structured_report,
        grounding)` — see `_score_search` for the first, fourth, and fifth.
    """
    if eligibility_result is None:
        raw = await mcp_server.call_tool(
            "calculate_user_eligibility", _eligibility_args(slot_state)
        )
        eligibility_result = _serialize_tool_result(raw)

    raw = await mcp_server.call_tool(
        "search_loans", _search_args(slot_state, eligibility_result)
    )
    search_output = _serialize_tool_result(raw)

    chat_summary, structured_report, grounding = _score_search(
        slot_state, eligibility_result, search_output
    )
    return chat_summary, eligibility_result, search_output, structured_report, grounding


def _serialize_tool_result(result):
    """Normalizes FastMCP's polymorphic call_tool() result into JSON-safe data.

    In practice our tools return plain dicts, which FastMCP wraps as a single
    TextContent block whose `.text` is the JSON-encoded dict — unwrap that back
    into structured data rather than nesting an already-JSON string.
    """
    if isinstance(result, tuple) and len(result) == 2:
        _, structured = result
        return structured
    if isinstance(result, dict):
        return result
    if isinstance(result, (list, tuple)):
        texts = [getattr(block, "text", None) or str(block) for block in result]
        joined = "\n".join(texts)
        try:
            return json.loads(joined)
        except (TypeError, ValueError):
            return {"text": joined}
    return {"text": str(result)}


def run_chat_agent(
    user_message: str,
    history: list[dict] | None = None,
    state: dict | None = None,
    user=None,
    loan_request_id: int | None = None,
    session_id: str | None = None,
) -> dict:
    """Runs one turn of the MCP tool-calling, slot-filling chat loop.

    Returns a single dict once the whole turn is resolved:

      - `{'reply': str, 'tool_calls': [...], 'state': {...},
        'loan_request_id': int | None, 'report': {...} | None}`

    `reply` is always clean, consumer-facing text — no internal reasoning,
    tool-call bookkeeping, or scratchpad notes (see `_clean_reply_text`).

    Args:
        user_message: The latest message from the user.
        history: Prior turns, oldest first, as {"role": "user"|"assistant",
            "content": str} dicts.
        state: The slot-filling state as last returned by this function (or
            `{}`/None on the first turn). Untrusted/partial input is
            whitelisted against the known schema before use.
        user: The authenticated `users.models.User` attached to this chat
            session, or None for a guest session.
        loan_request_id: The LoanRequest PK as last returned by this function,
            if one has already been auto-saved for this conversation — pass it
            back to avoid creating a duplicate row once slots are complete.
        session_id: The chat session's UUID, stamped onto any LoanRequest this
            turn creates so `/api/reports/` can later scope its list to this
            chat (see `mcp_server.persistence.save_loan_request`).
    """
    slot_state = normalize_state(state)
    slots_still_missing = missing_slots(slot_state)
    is_greeting = _is_simple_greeting(user_message)

    # A bare "hey"/"hi" is only a repetition risk when a full evaluation
    # already exists (all five slots known) — the "once all five fields are
    # known" instruction in the system prompt would otherwise read as license
    # to re-run the tools and re-send the same report on every later
    # greeting. State/history are left untouched either way — only the
    # prompt and tool gating change for this turn.
    is_greeting_checkin = is_greeting and not slots_still_missing
    # A greeting on a brand-new session (nothing known yet) instead gets a
    # short welcome menu rather than launching straight into a slot-filling
    # question — see WELCOME_GREETING_NOTE.
    is_welcome_greeting = is_greeting and len(slots_still_missing) == len(
        REQUIRED_SLOTS
    )
    # The loan request as it stood when this turn started, to tell whether
    # the model changed it (see `needs_report` in the loop below).
    initial_state = dict(slot_state)
    # True only if a report was already delivered in an earlier turn of this
    # same conversation (i.e. loan_request_id was already set when this turn
    # started) — distinguishes a legitimate follow-up question about an
    # existing report from slots having just become complete this turn.
    had_loan_request_before = loan_request_id is not None

    # The slot values the current `loan_request_id` row was saved with, so an
    # adjustment made after the first report (e.g. tenure 3 -> 5) is saved as
    # a new LoanRequest instead of leaving the Reports tab on stale numbers.
    saved_state: dict | None = dict(slot_state) if had_loan_request_before else None

    def maybe_save():
        nonlocal loan_request_id, saved_state
        if missing_slots(slot_state):
            return
        if loan_request_id is None or slot_state != saved_state:
            new_id = async_to_sync(save_loan_request)(slot_state, user, session_id)
            if new_id is not None:
                loan_request_id = new_id
            saved_state = dict(slot_state)

    maybe_save()  # covers a state that was already complete before this turn

    tools = [*async_to_sync(_tool_schemas)(), OUT_OF_SCOPE_TOOL]
    model = build_tool_calling_model().bind_tools(tools)

    if is_greeting_checkin:
        context_note = GREETING_CHECKIN_NOTE
    elif is_welcome_greeting:
        context_note = WELCOME_GREETING_NOTE
    elif had_loan_request_before:
        context_note = FOLLOW_UP_NOTE
        if _is_brief_confirmation(user_message):
            context_note += CONFIRMATION_NOTE
    else:
        context_note = ""

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        known_state=json.dumps(slot_state),
        context_note=context_note,
    )
    messages = [SystemMessage(content=system_prompt)]
    for turn in history or []:
        content = turn.get("content", "")
        if turn.get("role") == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    messages.append(HumanMessage(content=user_message))

    tool_calls_made = []
    # Populated once calculate_user_eligibility resolves, so the Predictive
    # Bank Matching Agent (below) can score against the borrower's real DTI
    # instead of re-estimating it.
    eligibility_result: dict | None = None
    # Set once search_loans succeeds and PredictiveBankAgent has scored it:
    # the fixed chat summary for this turn's report. The model writes the
    # actual reply; this is what the user gets instead if that reply fails
    # the grounding check, comes back empty, or never arrives.
    predictive_report: str | None = None
    # Companion to `predictive_report` — the compact payload the model was
    # shown as the search_loans result (see `_grounding_payload`).
    grounding: dict | None = None
    # Everything else the model was legitimately shown and may quote from.
    # Set once the model flags this turn's message as off-topic (see
    # OUT_OF_SCOPE_TOOL): its decline then goes out as written, and no loan
    # report is computed on the user's behalf.
    out_of_scope = False
    quotable_sources: list = [
        slot_state,
        user_message,
        [turn.get("content", "") for turn in history or []],
    ]
    # Companion to `predictive_report` — the full structured report (kpis,
    # policy_warnings, bank_recommendations, strategic_steps, raw_markdown)
    # for the same turn, see PredictiveBankAgent.build_structured_report.
    structured_report: dict | None = None

    def done(reply: str) -> dict:
        return {
            "reply": _clean_reply_text(reply),
            "tool_calls": tool_calls_made,
            "state": slot_state,
            "loan_request_id": loan_request_id,
            "report": structured_report,
        }

    for _ in range(MAX_TOOL_ITERATIONS):
        # Every slot is known and this turn owes the user a computed report
        # it does not have yet: either none was ever delivered, or the model
        # just changed the loan request (e.g. confirmed "extend to 5 years")
        # — and this is not a greeting check-in. If the model replies with
        # plain text instead of calling calculate_user_eligibility/
        # search_loans on THIS iteration, that text is an ungrounded "I've
        # updated it" claim. It is dropped below and the model is re-asked
        # with the real, deterministically computed results in front of it.
        # An off-topic turn owes no report at all.
        needs_report = (
            predictive_report is None
            and not out_of_scope
            and not missing_slots(slot_state)
            and not is_greeting_checkin
            and (not had_loan_request_before or slot_state != initial_state)
        )

        try:
            response = model.invoke(messages)
        except (LLMProviderError, GroqError):
            # Groq failed (429 rate limit, connection error, ...) — a
            # transient, expected condition under free-tier limits, not a
            # service misconfiguration, so answer normally instead of
            # surfacing a 503. `langchain_groq` doesn't wrap Groq SDK
            # errors, so its raw `GroqError` reaches here directly.
            # If this turn's tools already produced a report, its summary
            # is a better answer than an outage notice.
            return done(predictive_report or LLM_UNAVAILABLE_MESSAGE)

        messages.append(response)

        if not response.tool_calls:
            if needs_report:
                eligibility_was_known = eligibility_result is not None
                (
                    predictive_report,
                    eligibility_result,
                    search_output,
                    structured_report,
                    grounding,
                ) = async_to_sync(_run_predictive_pipeline)(
                    slot_state, eligibility_result
                )
                # Replace the ungrounded text with the tool exchange the
                # model should have made, so its next reply is written from
                # the same injected context as on the normal path.
                messages.pop()
                # (tool name, call args, full result, what the model sees)
                injected = [
                    (
                        "search_loans",
                        _search_args(slot_state, eligibility_result),
                        search_output,
                        grounding,
                    )
                ]
                if not eligibility_was_known:
                    injected.insert(
                        0,
                        (
                            "calculate_user_eligibility",
                            _eligibility_args(slot_state),
                            eligibility_result,
                            eligibility_result,
                        ),
                    )
                messages.append(
                    AIMessage(
                        content="",
                        tool_calls=[
                            {"name": name, "args": args, "id": f"auto-{name}"}
                            for name, args, _, _ in injected
                        ],
                    )
                )
                for name, args, result, model_context in injected:
                    tool_calls_made.append(
                        {"name": name, "args": args, "result": result}
                    )
                    quotable_sources.append(model_context)
                    messages.append(
                        ToolMessage(
                            content=json.dumps(model_context, default=str),
                            tool_call_id=f"auto-{name}",
                        )
                    )
                maybe_save()
                continue

            reply = response.content
            if predictive_report is not None:
                # Only the first evaluation must name a bank; a follow-up
                # ("over 5 years it drops to ...") legitimately may not.
                must_name = (
                    [] if had_loan_request_before else grounding["predicted_matches"]
                )
                if not reply or not _is_grounded(reply, quotable_sources, must_name):
                    reply = predictive_report
            return done(reply)

        for call in response.tool_calls:
            still_missing = missing_slots(slot_state)
            # What the model sees as this call's result; the full `output`
            # unless a branch below narrows it.
            model_context = None
            if call["name"] == OUT_OF_SCOPE_TOOL["name"]:
                out_of_scope = True
                output = OUT_OF_SCOPE_TOOL_RESULT
            elif call["name"] in GATED_TOOLS and still_missing:
                output = {
                    "error": "missing_required_fields",
                    "missing_fields": still_missing,
                    "message": (
                        f'Cannot run {call["name"]} yet — these fields are still '
                        f'missing: {", ".join(still_missing)}. Ask the user for '
                        "them instead of calling this tool."
                    ),
                }
            elif call["name"] in GATED_TOOLS and is_greeting_checkin:
                # Code-level backstop for GREETING_CHECKIN_NOTE — a plain
                # greeting must never re-trigger the report, even if the
                # model ignores the prompt guidance.
                output = {
                    "error": "greeting_checkin",
                    "message": (
                        "The user only sent a greeting/check-in — their existing "
                        "report already covers this. Do not call this tool; reply "
                        "conversationally instead and ask what they would like to "
                        "adjust."
                    ),
                }
            else:
                raw_result = async_to_sync(mcp_server.call_tool)(
                    call["name"], call["args"]
                )
                output = _serialize_tool_result(raw_result)
                if call["name"] == "update_loan_state":
                    slot_state.update(output)
                    maybe_save()
                elif call["name"] == "calculate_user_eligibility":
                    eligibility_result = output
                elif (
                    call["name"] == "search_loans"
                    and isinstance(output, dict)
                    and "policies" in output
                ):
                    # The model is shown the compact grounding payload as
                    # this tool's result, not the raw catalog rows — the API
                    # response (`tool_calls_made`) still carries the full
                    # output.
                    predictive_report, structured_report, grounding = _score_search(
                        slot_state, eligibility_result, output
                    )
                    model_context = grounding

            tool_calls_made.append(
                {"name": call["name"], "args": call["args"], "result": output}
            )
            if model_context is None:
                model_context = output
            quotable_sources.append(model_context)
            messages.append(
                ToolMessage(
                    content=json.dumps(model_context, default=str),
                    tool_call_id=call["id"],
                )
            )

    if predictive_report is not None:
        # The loop ran out of iterations after computing this turn's report
        # but before the model wrote a reply for it.
        return done(predictive_report)

    if (
        not missing_slots(slot_state)
        and not had_loan_request_before
        and not is_greeting_checkin
        and not out_of_scope
    ):
        # Same guarantee as above: the tool-call loop ran out of iterations
        # without ever producing a report, even though every slot is known —
        # never fall back to a generic apology when the real report can
        # still be computed deterministically.
        chat_reply, eligibility_result, search_output, structured_report, _ = (
            async_to_sync(_run_predictive_pipeline)(slot_state, eligibility_result)
        )
        tool_calls_made.append(
            {
                "name": "calculate_user_eligibility",
                "args": slot_state,
                "result": eligibility_result,
            }
        )
        tool_calls_made.append(
            {"name": "search_loans", "args": slot_state, "result": search_output}
        )
        maybe_save()
        return done(chat_reply)

    fallback_reply = (
        "I wasn't able to finish gathering the information needed to answer "
        "that. Could you rephrase or narrow your request?"
    )
    return done(fallback_reply)
