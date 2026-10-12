"""Predictive Bank Matching Agent.

Dedicated, non-LLM agent component that owns the full predictive-matching
lifecycle end-to-end: normalizing a borrower profile, weighted scoring/
ranking of candidate bank loan policies (as returned by
`mcp_server.server.search_loans`), and rendering the final executive report
as clean, structured Markdown (headings, a bank comparison table, and a
callout for the SBP policy notice). Report structure/compliance is
therefore guaranteed by code, not by an LLM's own formatting discipline.

Weighted scoring model (must sum to 1.0):
    - DTI Safety Margin              40%
    - Profit/Interest Rate Advantage 30%
    - Islamic vs Conventional Match   20%
    - Processing Ease / Flexibility  10%
"""


class PredictiveBankAgent:
    """Scores, ranks, and reports on candidate bank loan policies.

    Usage (see `mcp_server.agent.run_chat_agent`):
        agent = PredictiveBankAgent()
        ranked = agent.evaluate_and_rank(policies, user_profile)
        report = agent.format_executive_report(ranked, user_profile)
    """

    SBP_MAX_DTI_PERCENTAGE = 50.0

    # Below the SBP cap but close enough to flag as a caution rather than a
    # hard failure — see `build_policy_warnings`.
    DTI_CAUTION_THRESHOLD_PERCENTAGE = 40.0

    # Last-resort profit rate for `_normalize_profile`'s dti_percentage
    # fallback — only used on the rare turn a report is built without
    # `mcp_server.server.calculate_user_eligibility` having already run (that
    # tool computes the real, catalog-derived rate itself).
    DEFAULT_PROFIT_RATE_PERCENTAGE = 18.0

    DTI_SAFETY_WEIGHT = 0.40
    PROFIT_RATE_WEIGHT = 0.30
    PREFERENCE_WEIGHT = 0.20
    FLEXIBILITY_WEIGHT = 0.10

    # Match-score cutoffs for the Approval Probability tier.
    HIGH_THRESHOLD = 85.0
    MEDIUM_HIGH_THRESHOLD = 70.0
    MEDIUM_THRESHOLD = 50.0

    # Reference ceiling used to normalize max_tenure_years into a 0-100
    # flexibility score (Home loans in this catalog top out around this range).
    TENURE_FLEXIBILITY_CEILING_YEARS = 25.0

    # A borrower whose Islamic/conventional preference isn't met still gets a
    # non-zero score, since the bank remains a real, usable option.
    PREFERENCE_MISMATCH_SCORE = 30.0

    BASE_REQUIRED_DOCUMENTS = (
        'Copy of valid CNIC',
        'Last 3 months salary slips',
        '6-month bank statement',
    )

    # One additional, generically-expected document per loan type — never a
    # bank-specific requirement, since only search_loans/get_bank_details may
    # cite those.
    LOAN_TYPE_DOCUMENTS = {
        'Vehicle': 'Vehicle registration / sale quotation paperwork',
        'Home': 'Property documents (sale deed / allotment letter)',
        'Personal': 'Personal loan application form / proof of purpose (if required)',
    }

    # Display label for each loan_type code, used in the Advisory Notice.
    LOAN_TYPE_LABELS = {
        'Personal': 'Personal Loan',
        'Home': 'Home Loan',
        'Vehicle': 'Vehicle Loan',
    }

    # Aliases that still mean "Vehicle" — normalized immediately wherever a
    # loan_type is received (e.g. the LLM extracting "Auto" or "Car") so only
    # 'Vehicle' ever reaches the dictionaries/scoring above.
    VEHICLE_LOAN_TYPE_ALIASES = ('Auto', 'Car', 'Vehicle')

    PKR_PER_LAKH = 100_000.0

    # ------------------------------------------------------------------
    # Scoring & ranking
    # ------------------------------------------------------------------

    def evaluate_and_rank(self, policies: list[dict], user_profile: dict) -> list[dict]:
        """Normalizes the borrower profile and scores every candidate policy.

        Args:
            policies: Candidate policies as returned by
                `mcp_server.server.search_loans` (each with at least
                bank_name, is_islamic, profit_rate, min_downpayment_percentage,
                max_tenure_years).
            user_profile: Raw borrower/session data — monthly_income,
                required_amount, tenure_years, is_islamic (preference,
                True/False/None), and optionally dti_percentage/
                remaining_capacity already computed by
                calculate_user_eligibility.

        Returns:
            `policies`, re-ranked highest match_score first, each augmented
            with match_score (0-100), approval_probability (HIGH/
            MEDIUM-HIGH/MEDIUM/LOW), estimated_emi, prediction_reason, rank,
            and is_best_match.
        """
        if not policies:
            return []

        profile = self._normalize_profile(user_profile)
        rates = [policy.get('profit_rate', 0.0) for policy in policies]
        lowest_rate, highest_rate = min(rates), max(rates)

        scored = []
        for policy in policies:
            profit_rate = policy.get('profit_rate', 0.0)
            is_islamic = policy.get('is_islamic', False)

            dti_score = self._dti_safety_score(profile['dti_percentage'])
            rate_score = self._profit_rate_score(profit_rate, lowest_rate, highest_rate)
            preference_score = self._preference_score(is_islamic, profile['prefers_islamic'])
            flexibility_score = self._flexibility_score(
                policy.get('min_downpayment_percentage', 0.0), policy.get('max_tenure_years', 0)
            )

            match_score = (
                dti_score * self.DTI_SAFETY_WEIGHT
                + rate_score * self.PROFIT_RATE_WEIGHT
                + preference_score * self.PREFERENCE_WEIGHT
                + flexibility_score * self.FLEXIBILITY_WEIGHT
            )

            scored.append(
                {
                    **policy,
                    'match_score': round(match_score),
                    'approval_probability': self._approval_probability(match_score),
                    'estimated_emi': round(
                        self._estimate_emi(profile['required_amount'], profit_rate, profile['tenure_years']), 2
                    ),
                    'prediction_reason': self._prediction_reason(
                        is_islamic, dti_score, rate_score, preference_score, flexibility_score,
                        profile['prefers_islamic'],
                    ),
                    'score_breakdown': {
                        'dti_safety_margin': round(dti_score, 1),
                        'profit_rate_advantage': round(rate_score, 1),
                        'preference_match': round(preference_score, 1),
                        'processing_flexibility': round(flexibility_score, 1),
                    },
                }
            )

        scored.sort(key=lambda item: item['match_score'], reverse=True)
        for rank, item in enumerate(scored, start=1):
            item['rank'] = rank
            item['is_best_match'] = rank == 1

        return scored

    # ------------------------------------------------------------------
    # Report rendering
    # ------------------------------------------------------------------

    def format_executive_report(self, ranked_policies: list[dict], user_profile: dict) -> str:
        """Renders the final Executive Financial Report as clean Markdown.

        Structured into exactly four sections — Executive Summary, SBP Rules
        & Policy Notice (a blockquote callout), Recommended Banks & Options
        (a Markdown table), and Strategic Recommendations (a bullet list) —
        with no conversational filler. This is the final user-facing report
        text verbatim; no further LLM reformatting required or expected.

        Args:
            ranked_policies: The output of `evaluate_and_rank`, already
                sorted best match first.
            user_profile: Same borrower/session data passed to
                `evaluate_and_rank`.

        Returns:
            The complete report as a Markdown string, ready to send to the user.
        """
        profile = self._normalize_profile(user_profile)

        if not ranked_policies:
            return self._format_advisory_notice(profile)

        is_eligible = profile['dti_percentage'] <= self.SBP_MAX_DTI_PERCENTAGE

        blocks = ['# Executive Financial Report']

        summary_lines = [
            '## Executive Summary',
            '',
            f"- **Requested Amount:** PKR {self._format_money(profile['required_amount'])}",
            f"- **Monthly Income:** PKR {self._format_money(profile['monthly_income'])}",
            f"- **DTI Ratio:** {profile['dti_percentage']:.1f}%",
            f"- **Eligibility Status:** {'Eligible' if is_eligible else 'Not Eligible'}",
        ]
        if profile['remaining_capacity'] is not None:
            max_eligible_amount = profile['remaining_capacity'] * profile['tenure_years'] * 12
            summary_lines.append(f"- **Max Eligible Amount (est.):** PKR {self._format_money(max_eligible_amount)}")
        blocks.append('\n'.join(summary_lines))

        blocks.append(self._sbp_policy_notice(profile['dti_percentage'], is_eligible))

        table_lines = [
            '## Recommended Banks & Options',
            '',
            '| Rank | Bank | Match Score | Approval Probability | Profit Rate | Est. EMI (PKR/mo) |',
            '|---|---|---|---|---|---|',
        ]
        for policy in ranked_policies:
            bank_label = f"{policy['bank_name']} (Best Match)" if policy.get('is_best_match') else policy['bank_name']
            table_lines.append(
                f"| {policy['rank']} | **{bank_label}** | {policy['match_score']}% | "
                f"{policy['approval_probability']} | {policy['profit_rate']}% p.a. | "
                f"{self._format_money(policy['estimated_emi'])} |"
            )
        blocks.append('\n'.join(table_lines))

        recommendation_lines = ['## Strategic Recommendations', '']
        recommendation_lines.extend(
            f"- **{policy['bank_name']}:** {policy['prediction_reason']}"
            for policy in ranked_policies
            if policy.get('prediction_reason')
        )
        recommendation_lines.append('- **Required documentation:** ' + '; '.join(self._required_documents(profile['loan_type'])) + '.')
        blocks.append('\n'.join(recommendation_lines))

        return '\n\n'.join(blocks).rstrip() + '\n'

    def format_chat_summary(self, ranked_policies: list[dict], user_profile: dict) -> str:
        """Renders the short, natural-language chat reply for one report turn.

        The chat bubble must never carry the Markdown table or KPI block
        that `format_executive_report` renders — the full Bank Comparison
        Matrix stays confined to the dedicated report page/modal, fed by
        `build_structured_report` (see `mcp_server.agent.run_chat_agent`,
        which sends this method's return value as the chat `reply` while
        attaching `build_structured_report`'s output as the `report` field).
        This is short conversational prose plus a one-line SBP compliance
        blockquote, a short bank-recommendation bullet list, and a 2-3 item
        "Next Action Plan" bullet list — the chat-bubble markdown renderer
        (`frontend/src/components/MarkdownMessage.jsx`) turns these into
        inline metric chips, a callout banner, and checkmark list rows, so
        keep each list short and each bullet on its own line rather than
        reaching for a table.

        Args:
            ranked_policies: The output of `evaluate_and_rank`, already
                sorted best match first.
            user_profile: Same borrower/session data passed to
                `evaluate_and_rank`.

        Returns:
            A short, table-free, human-readable chat message.
        """
        profile = self._normalize_profile(user_profile)

        if not ranked_policies:
            return self._chat_advisory_summary(profile)

        is_eligible = profile['dti_percentage'] <= self.SBP_MAX_DTI_PERCENTAGE
        loan_type_label = self._loan_type_label(profile['loan_type']).lower()
        top = ranked_policies[0]
        match_count = len(ranked_policies)

        paragraphs = [
            (
                f"Based on a monthly income of PKR {self._format_money(profile['monthly_income'])} and your "
                f"requested PKR {self._format_money(profile['required_amount'])} {loan_type_label}, your "
                f"estimated debt-to-income ratio comes to {profile['dti_percentage']:.1f}%."
            )
        ]

        compliance_icon = '✅' if is_eligible else '⚠️'
        paragraphs.append(
            f"> {compliance_icon} "
            f"{'Comfortably within' if is_eligible else 'Above'} the State Bank of Pakistan's "
            f"{self.SBP_MAX_DTI_PERCENTAGE:.0f}% limit on total monthly debt obligations."
        )

        top_reason = top['prediction_reason'].rstrip('.')
        top_reason = top_reason[:1].lower() + top_reason[1:]
        rec_lines = [
            f"I compared {match_count} matching {'option' if match_count == 1 else 'options'} in our bank "
            'catalog — here are your top matches:',
            '',
            f"- **{top['bank_name']}** — {top['profit_rate']}% p.a., estimated EMI "
            f"PKR {self._format_money(top['estimated_emi'])}/mo — {top_reason}",
        ]
        if match_count > 1:
            runner_up = ranked_policies[1]
            rec_lines.append(
                f"- **{runner_up['bank_name']}** — {runner_up['profit_rate']}% p.a., estimated EMI "
                f"PKR {self._format_money(runner_up['estimated_emi'])}/mo"
            )
        paragraphs.append('\n'.join(rec_lines))

        paragraphs.append(
            "I've put together the full Bank Comparison Matrix and required documents in your Reports "
            'tab, where you can review or export it anytime.'
        )

        action_items = []
        if not is_eligible:
            action_items.append('Reduce the requested amount or extend the tenure to bring your DTI within the SBP limit')
        action_items.append('Review the full comparison and required documents in your Reports tab')
        action_items.append("Let me know if you'd like to try a different amount, tenure, or Islamic/conventional preference")
        paragraphs.append('**Next Action Plan:**\n\n' + '\n'.join(f'- {item}' for item in action_items[:3]))

        return '\n\n'.join(paragraphs)

    def _chat_advisory_summary(self, profile: dict) -> str:
        """Chat-facing counterpart to `_format_advisory_notice` for the
        zero-eligible-match case — same underlying facts, short conversational
        prose plus an SBP compliance callout and a "Next Action Plan" bullet
        list instead of a full Markdown report.
        """
        loan_type_label = self._loan_type_label(profile['loan_type'])
        requested_amount = profile['required_amount']
        catalog_max_amount = profile['catalog_max_amount']
        dti = profile['dti_percentage']
        is_eligible = dti <= self.SBP_MAX_DTI_PERCENTAGE
        exceeds_ceiling = catalog_max_amount is not None and requested_amount > catalog_max_amount

        compliance_icon = '✅' if is_eligible else '⚠️'
        paragraphs = [
            f"> {compliance_icon} Your estimated DTI ratio comes to {dti:.1f}%, which is "
            f"{'within' if is_eligible else 'above'} the State Bank of Pakistan's "
            f"{self.SBP_MAX_DTI_PERCENTAGE:.0f}% limit."
        ]

        if exceeds_ceiling:
            paragraphs.append(
                f"Unfortunately, I couldn't find a matching {loan_type_label.lower()} in our catalog — the "
                f"highest ceiling currently available is PKR {self._format_money(catalog_max_amount)}, below "
                f"your requested PKR {self._format_money(requested_amount)}."
            )
        elif catalog_max_amount is None:
            paragraphs.append(
                f"Unfortunately, no banks in our current catalog offer "
                f"{self._islamic_preference_label(profile['prefers_islamic'])}{loan_type_label.lower()} "
                'products at all.'
            )
        else:
            paragraphs.append(
                f"{loan_type_label}s up to PKR {self._format_money(catalog_max_amount)} are available in the "
                f"catalog, but none of them fit your current DTI ratio or Islamic/conventional preference."
            )

        recommendations = self._recommendations(
            profile['loan_type'], loan_type_label, catalog_max_amount, exceeds_ceiling
        )
        action_items = list(recommendations)
        action_items.append('Review this in more detail anytime from your Reports tab')
        paragraphs.append('**Next Action Plan:**\n\n' + '\n'.join(f'- {item}' for item in action_items[:3]))

        return '\n\n'.join(paragraphs)

    def build_kpis(self, user_profile: dict) -> dict:
        """Builds the small, frontend-card-ready KPI block for one report.

        Every field is always a concrete, non-null value — `_normalize_profile`
        coerces missing/blank input to safe numeric defaults before this ever
        runs, so a caller never has to special-case a null `dti_ratio` or
        `tenure` (the exact "Not available" KPI-card bug this guards
        against). Kept separate from the Markdown report body so the
        frontend can render dedicated summary cards without parsing prose.
        See `mcp_server.agent._run_predictive_pipeline`, which attaches this
        as `report.kpis` on the turn a report is generated.
        """
        profile = self._normalize_profile(user_profile)
        is_eligible = profile['dti_percentage'] <= self.SBP_MAX_DTI_PERCENTAGE
        return {
            'requested_amount': profile['required_amount'],
            'monthly_income': profile['monthly_income'],
            'tenure': profile['tenure_years'],
            'dti_ratio': f"{profile['dti_percentage']:.1f}%",
            'eligibility_status': 'Eligible' if is_eligible else 'Not Eligible',
        }

    def build_policy_warnings(self, profile: dict) -> list[dict]:
        """Builds the `policy_warnings` list for one report — always a list
        (never null), empty when the borrower is comfortably within the SBP
        DTI cap. `profile` must already be `_normalize_profile`-shaped (every
        call site here goes through `build_structured_report`).
        """
        dti = profile['dti_percentage']
        if dti > self.SBP_MAX_DTI_PERCENTAGE:
            return [
                {
                    'title': 'SBP DTI Limit Exceeded',
                    'description': (
                        f'Your estimated DTI ratio of {dti:.1f}% exceeds the State Bank of '
                        f"Pakistan's {self.SBP_MAX_DTI_PERCENTAGE:.0f}% cap on total monthly debt "
                        'obligations. Reduce the requested amount, extend the tenure, or lower '
                        'existing obligations to qualify.'
                    ),
                    'level': 'red',
                }
            ]
        if dti >= self.DTI_CAUTION_THRESHOLD_PERCENTAGE:
            return [
                {
                    'title': 'Approaching SBP DTI Limit',
                    'description': (
                        f'Your estimated DTI ratio of {dti:.1f}% is within the SBP '
                        f'{self.SBP_MAX_DTI_PERCENTAGE:.0f}% cap but leaves limited headroom for '
                        'any additional debt obligations.'
                    ),
                    'level': 'amber',
                }
            ]
        return []

    def build_bank_recommendations(self, ranked_policies: list[dict], loan_type_label: str) -> list[dict]:
        """Builds the `bank_recommendations` list for one report — always a
        list (never null), one entry per ranked policy, already sorted best
        match first by `evaluate_and_rank`.
        """
        return [
            {
                'bank_name': policy['bank_name'],
                'loan_type': loan_type_label,
                'monthly_installment': policy['estimated_emi'],
                'interest_rate': policy['profit_rate'],
                'shariah_compliant': bool(policy.get('is_islamic', False)),
                'apply_url': policy.get('main_page_url'),
            }
            for policy in ranked_policies
        ]

    def build_strategic_steps(self, ranked_policies: list[dict], profile: dict) -> list[str]:
        """Builds the `strategic_steps` list for one report — always a
        non-empty list of plain strings, the same advisory content as the
        Markdown report's own "Strategic Recommendations" section /
        Advisory Notice, just without Markdown bullet syntax.
        """
        if not ranked_policies:
            loan_type_label = self._loan_type_label(profile['loan_type'])
            exceeds_ceiling = (
                profile['catalog_max_amount'] is not None
                and profile['required_amount'] > profile['catalog_max_amount']
            )
            return self._recommendations(
                profile['loan_type'], loan_type_label, profile['catalog_max_amount'], exceeds_ceiling
            )

        steps = [
            f"{policy['bank_name']}: {policy['prediction_reason']}"
            for policy in ranked_policies
            if policy.get('prediction_reason')
        ]
        steps.append('Required documentation: ' + '; '.join(self._required_documents(profile['loan_type'])) + '.')
        return steps

    def build_structured_report(self, ranked_policies: list[dict], user_profile: dict) -> dict:
        """Builds the full structured report the frontend maps its report UI
        from — `kpis`, `policy_warnings`, `bank_recommendations`,
        `strategic_steps`, and `raw_markdown` (the same Markdown
        `format_executive_report` renders, kept as a structured fallback for
        any consumer not yet reading the structured fields directly).

        Every section is always present and concrete — never null/missing —
        `kpis` and `policy_warnings` in particular, since those are what
        rendered "Not available" on the frontend's KPI cards when they were
        allowed to go missing.
        """
        profile = self._normalize_profile(user_profile)
        loan_type_label = self._loan_type_label(profile['loan_type'])
        return {
            'kpis': self.build_kpis(user_profile),
            'policy_warnings': self.build_policy_warnings(profile),
            'bank_recommendations': self.build_bank_recommendations(ranked_policies, loan_type_label),
            'strategic_steps': self.build_strategic_steps(ranked_policies, profile),
            'raw_markdown': self.format_executive_report(ranked_policies, user_profile),
        }

    def _sbp_policy_notice(self, dti_percentage: float, is_eligible: bool) -> str:
        """Renders the SBP Rules & Policy Notice section as a Markdown blockquote callout."""
        standing = 'within' if is_eligible else 'exceeds'
        return (
            '> **SBP Rules & Policy Notice**\n'
            f'> The State Bank of Pakistan caps total monthly debt obligations '
            f'(existing installments plus the new loan) at '
            f'**{self.SBP_MAX_DTI_PERCENTAGE:.0f}%** of gross monthly income. Your estimated DTI ratio of '
            f'**{dti_percentage:.1f}%** is {standing} this limit.'
        )

    # ------------------------------------------------------------------
    # Advisory notice (zero-match / over-limit report rendering)
    # ------------------------------------------------------------------

    def _format_advisory_notice(self, profile: dict) -> str:
        """Renders the Advisory Notice shown in place of a match table when
        `evaluate_and_rank` found zero eligible policies — e.g. the requested
        amount exceeds every bank's ceiling for this loan type, or no
        catalog policy accepts the borrower's DTI/Islamic-preference
        combination. Always a concrete, data-backed explanation — never a
        blank or generic placeholder. Kept to the same four-section
        structure as `format_executive_report`.
        """
        loan_type_label = self._loan_type_label(profile['loan_type'])
        requested_amount = profile['required_amount']
        catalog_max_amount = profile['catalog_max_amount']
        dti = profile['dti_percentage']
        is_eligible = dti <= self.SBP_MAX_DTI_PERCENTAGE

        blocks = ['# Executive Financial Report']

        summary_lines = [
            '## Executive Summary',
            '',
            f'- **Requested Amount:** PKR {self._format_money(requested_amount)}',
            f'- **Selected Loan Type:** {loan_type_label}',
            f"- **Monthly Income:** PKR {self._format_money(profile['monthly_income'])}",
            f'- **DTI Ratio:** {dti:.1f}%',
            f"- **Eligibility Status:** {'Eligible' if is_eligible else 'Not Eligible'}",
        ]
        blocks.append('\n'.join(summary_lines))

        blocks.append(self._sbp_policy_notice(dti, is_eligible))

        exceeds_ceiling = catalog_max_amount is not None and requested_amount > catalog_max_amount

        banks_lines = ['## Recommended Banks & Options', '']
        if exceeds_ceiling:
            banks_lines.append(
                f'No matching options — {loan_type_label.lower()}s in the current bank catalog have a maximum '
                f'ceiling of PKR {self._format_money(catalog_max_amount)} '
                f'({self._format_lakhs(catalog_max_amount)} Lakhs), below your requested '
                f'PKR {self._format_money(requested_amount)} ({self._format_lakhs(requested_amount)} Lakhs).'
            )
        elif catalog_max_amount is None:
            banks_lines.append(
                f'No banks in the current catalog offer '
                f'{self._islamic_preference_label(profile["prefers_islamic"])}{loan_type_label.lower()} products '
                f'at all.'
            )
        else:
            banks_lines.append(
                f'{loan_type_label}s up to PKR {self._format_money(catalog_max_amount)} are available in the '
                f'catalog, but none of them accept your current DTI ratio of {dti:.1f}% and/or Islamic/'
                f'conventional preference.'
            )
        blocks.append('\n'.join(banks_lines))

        recommendation_lines = ['## Strategic Recommendations', '']
        recommendation_lines.extend(
            f'- {recommendation}'
            for recommendation in self._recommendations(
                profile['loan_type'], loan_type_label, catalog_max_amount, exceeds_ceiling
            )
        )
        blocks.append('\n'.join(recommendation_lines))

        return '\n\n'.join(blocks).rstrip() + '\n'

    @staticmethod
    def _islamic_preference_label(prefers_islamic: bool | None) -> str:
        if prefers_islamic is True:
            return 'Islamic (Shariah-compliant) '
        if prefers_islamic is False:
            return 'conventional '
        return ''

    def _loan_type_label(self, loan_type: str | None) -> str:
        if not loan_type:
            return 'Loan'
        return self.LOAN_TYPE_LABELS.get(loan_type, f'{loan_type} Loan')

    def _recommendations(
        self,
        loan_type: str | None,
        loan_type_label: str,
        catalog_max_amount: float | None,
        exceeds_ceiling: bool,
    ) -> list[str]:
        recommendations = []

        if exceeds_ceiling:
            if loan_type == 'Personal':
                recommendations.append(
                    'Consider a Home / Mortgage Loan or Vehicle Loan if acquiring real estate/vehicle '
                    '(limits up to PKR 50M+).'
                )
            elif loan_type == 'Vehicle':
                recommendations.append(
                    'Consider a Home / Mortgage Loan or Personal Loan depending on what the funds are actually for.'
                )
            elif loan_type == 'Home':
                recommendations.append(
                    'Consider a larger down payment to reduce the financed amount, or discuss a '
                    'top-up/construction finance product directly with the bank.'
                )
            recommendations.append(
                f'Adjust requested {loan_type_label.lower()} amount to '
                f'PKR {self._format_money(catalog_max_amount)} to view eligible bank options.'
            )
        elif catalog_max_amount is None:
            recommendations.append(
                f'Try a different loan type, or adjust your Islamic/conventional preference to view '
                f'{loan_type_label.lower()} options currently in the catalog.'
            )
        else:
            recommendations.append(
                'Increase your desired tenure to lower the estimated monthly installment and reduce your DTI ratio.'
            )
            recommendations.append(
                'Alternatively, reduce the requested loan amount, or switch your Islamic/conventional preference '
                'to see additional catalog options.'
            )

        return recommendations

    @staticmethod
    def _format_lakhs(value: float) -> str:
        lakhs = value / PredictiveBankAgent.PKR_PER_LAKH
        if lakhs == int(lakhs):
            return f'{int(lakhs):,}'
        return f'{lakhs:,.1f}'

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _normalize_profile(self, user_profile: dict) -> dict:
        """Data-normalization step: coerces/validates the raw profile dict.

        Estimates dti_percentage from required_amount/tenure_years when the
        caller hasn't already run calculate_user_eligibility this turn.
        """
        monthly_income = float(user_profile.get('monthly_income') or 0.0)
        required_amount = float(user_profile.get('required_amount') or 0.0)
        tenure_years = float(user_profile.get('tenure_years') or 1)

        dti_percentage = user_profile.get('dti_percentage')
        if dti_percentage is None:
            estimated_installment = self._estimate_emi(
                required_amount, self.DEFAULT_PROFIT_RATE_PERCENTAGE, tenure_years
            )
            dti_percentage = (estimated_installment / monthly_income) * 100 if monthly_income else 0.0

        remaining_capacity = user_profile.get('remaining_capacity')

        loan_type = user_profile.get('loan_type')
        if loan_type in self.VEHICLE_LOAN_TYPE_ALIASES:
            loan_type = 'Vehicle'

        return {
            'monthly_income': monthly_income,
            'required_amount': required_amount,
            'tenure_years': tenure_years,
            'dti_percentage': float(dti_percentage),
            'remaining_capacity': float(remaining_capacity) if remaining_capacity is not None else None,
            # Borrower's stated Islamic (True) / conventional (False) intent,
            # or None if they expressed no preference.
            'prefers_islamic': user_profile.get('is_islamic'),
            'loan_type': loan_type,
            # Highest max_loan_amount available anywhere in the catalog for
            # this loan_type/preference (see mcp_server.server.search_loans),
            # only present when the search came back with zero policies.
            'catalog_max_amount': user_profile.get('catalog_max_amount'),
        }

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
        return max(low, min(high, value))

    def _dti_safety_score(self, dti_percentage: float) -> float:
        """Scores the borrower's safety margin against the SBP 50% DTI limit.

        Higher score = more headroom between the borrower's own projected
        DTI and the regulatory 50% ceiling — a borrower-level figure, the
        same for every candidate bank in one query.
        """
        margin = self.SBP_MAX_DTI_PERCENTAGE - dti_percentage
        return self._clamp((margin / self.SBP_MAX_DTI_PERCENTAGE) * 100)

    def _profit_rate_score(self, profit_rate: float, lowest_rate: float, highest_rate: float) -> float:
        """Scores a policy's profit rate relative to the other candidates (lower is better)."""
        if highest_rate == lowest_rate:
            return 100.0
        return self._clamp(((highest_rate - profit_rate) / (highest_rate - lowest_rate)) * 100)

    def _preference_score(self, policy_is_islamic: bool, prefers_islamic: bool | None) -> float:
        """Scores how well a policy matches the borrower's stated Islamic/conventional preference."""
        if prefers_islamic is None:
            return 100.0
        return 100.0 if policy_is_islamic == prefers_islamic else self.PREFERENCE_MISMATCH_SCORE

    def _flexibility_score(self, min_downpayment_percentage: float, max_tenure_years: float) -> float:
        """Scores processing ease from down-payment burden and tenure flexibility."""
        downpayment_score = self._clamp(100 - (min_downpayment_percentage or 0.0) * 2)
        tenure_score = self._clamp(((max_tenure_years or 0) / self.TENURE_FLEXIBILITY_CEILING_YEARS) * 100)
        return (downpayment_score + tenure_score) / 2

    def _approval_probability(self, match_score: float) -> str:
        if match_score >= self.HIGH_THRESHOLD:
            return 'HIGH'
        if match_score >= self.MEDIUM_HIGH_THRESHOLD:
            return 'MEDIUM-HIGH'
        if match_score >= self.MEDIUM_THRESHOLD:
            return 'MEDIUM'
        return 'LOW'

    @staticmethod
    def _estimate_emi(requested_amount: float, profit_rate: float, tenure_years: float) -> float:
        """Standard reducing-balance EMI — matches
        `mcp_server.server.calculate_user_eligibility`'s own installment
        formula, so a policy's reported EMI and the borrower's DTI ratio are
        always computed the same way.
        """
        if tenure_years <= 0:
            return 0.0
        months = tenure_years * 12
        monthly_rate = profit_rate / 100 / 12
        if monthly_rate == 0:
            return requested_amount / months
        growth = (1 + monthly_rate) ** months
        return requested_amount * monthly_rate * growth / (growth - 1)

    @staticmethod
    def _prediction_reason(
        is_islamic: bool,
        dti_score: float,
        rate_score: float,
        preference_score: float,
        flexibility_score: float,
        prefers_islamic: bool | None,
    ) -> str:
        factors = []
        if rate_score >= 80:
            sector = 'Islamic' if is_islamic else 'conventional'
            factors.append(f'lowest profit rate in the {sector} sector')
        if dti_score >= 80:
            factors.append('ideal DTI capacity')
        if prefers_islamic is not None and preference_score == 100.0:
            factors.append('matches your Shariah/conventional preference')
        if flexibility_score >= 80:
            factors.append('flexible tenure and low down payment terms')
        if not factors:
            factors.append('solid all-round fit against your profile')

        reason = ' + '.join(factors) if len(factors) > 1 else factors[0]
        return reason[0].upper() + reason[1:] + '.'

    @staticmethod
    def _format_money(value: float) -> str:
        return f'{value:,.0f}'

    def _required_documents(self, loan_type: str | None) -> list[str]:
        documents = list(self.BASE_REQUIRED_DOCUMENTS)
        extra = self.LOAN_TYPE_DOCUMENTS.get(loan_type or '')
        if extra:
            documents.append(extra)
        return documents
