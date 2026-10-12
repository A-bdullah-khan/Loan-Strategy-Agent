import apiClient from './api'

/**
 * @typedef {object} LoanDiscoveryState
 * @property {string | null} loan_type
 * @property {number | null} required_amount
 * @property {number | null} monthly_income
 * @property {boolean | null} is_islamic
 * @property {number | null} tenure_years
 */

/**
 * @typedef {object} ChatTurnKpis
 * @property {number} requested_amount
 * @property {number} monthly_income
 * @property {number} tenure
 * @property {string} dti_ratio - a formatted percentage string, e.g. "42.5%".
 * @property {'Eligible' | 'Not Eligible'} eligibility_status
 */

/**
 * @typedef {object} ChatTurnPolicyWarning
 * @property {string} title
 * @property {string} description
 * @property {'amber' | 'red'} level
 */

/**
 * @typedef {object} ChatTurnBankRecommendation
 * @property {string} bank_name
 * @property {string} loan_type
 * @property {number} monthly_installment
 * @property {number} interest_rate
 * @property {boolean} shariah_compliant
 * @property {string | null} apply_url
 */

/**
 * @typedef {object} ChatTurnReport
 * @property {ChatTurnKpis} kpis
 * @property {ChatTurnPolicyWarning[]} policy_warnings
 * @property {ChatTurnBankRecommendation[]} bank_recommendations
 * @property {string[]} strategic_steps
 * @property {string} raw_markdown - structured fallback text, same content
 *   `format_executive_report` renders as the chat reply itself.
 */

/**
 * @typedef {object} ChatTurnResult
 * @property {string} reply - clean, consumer-facing reply text
 * @property {Array<{ name: string, args: object, result: object }>} tool_calls
 * @property {LoanDiscoveryState} state
 * @property {number | null} loan_request_id
 * @property {string} session_id
 * @property {ChatTurnReport | null} report - only set on the turn the
 *   Executive Financial Report was rendered (see
 *   PredictiveBankAgent.build_structured_report) — every field inside it is
 *   then always concretely populated, never null.
 */

/**
 * Reloads a previous conversation's message history from MongoDB.
 * @param {string} sessionId
 * @param {number} [limit]
 * @returns {Promise<import('axios').AxiosResponse<{ session_id: string, messages: Array<{ role: string, content: string, slots_captured: object, timestamp: string }> }>>}
 */
export function getChatHistory(sessionId, limit = 20) {
  return apiClient.get('/chat/history/', { params: { session_id: sessionId, limit } })
}

/**
 * Permanently deletes a session's transcript from MongoDB (scoped to the
 * current user on the backend).
 * @param {string} sessionId
 * @returns {Promise<import('axios').AxiosResponse<{ success: boolean, session_id: string, deleted_count: number }>>}
 */
export function deleteChatHistory(sessionId) {
  return apiClient.delete(`/chat/history/${sessionId}/`)
}

/**
 * Runs one turn of the MCP-backed, slot-filling chatbot agent via
 * `POST /api/chat/` (see `mcp_server.api.ChatAPIView`) — a single JSON
 * request/response; the full reply is only available once the whole
 * (possibly multi-tool-call) turn has finished on the backend.
 *
 * Conversation history is persisted server-side in MongoDB per session_id —
 * pass back the `state`, `loan_request_id`, and `session_id` from the
 * previous turn's result so the agent remembers prior turns and doesn't
 * create a duplicate LoanRequest once slots are complete. Omit `sessionId`
 * to start a new conversation; the result carries the server-generated one.
 *
 * @param {string} message
 * @param {string | null} sessionId
 * @param {LoanDiscoveryState} state
 * @param {number | null} loanRequestId
 * @param {AbortSignal} [signal] - lets the caller cancel an in-flight request
 * @returns {Promise<import('axios').AxiosResponse<ChatTurnResult>>}
 */
export function sendChatMessage(message, sessionId, state, loanRequestId, signal) {
  return apiClient.post(
    '/chat/',
    { message, session_id: sessionId, state, loan_request_id: loanRequestId },
    { signal },
  )
}
