import apiClient from './api'

/**
 * @typedef {object} StructuredLoanReport
 * @property {number} loan_request_id
 * @property {string | null} loan_type
 * @property {boolean} is_islamic
 * @property {import('./chat').ChatTurnKpis} kpis
 * @property {import('./chat').ChatTurnPolicyWarning[]} policy_warnings
 * @property {import('./chat').ChatTurnBankRecommendation[]} bank_recommendations
 * @property {string[]} strategic_steps
 * @property {string} raw_markdown
 */

/**
 * Fetches the full structured Executive Financial Report for one
 * LoanRequest from `GET /api/reports/<id>/` (see
 * `backend/services/report_views.get_loan_report`) — pure DB-to-JSON, no
 * LLM/Groq call. This is what the full-page report view
 * (`/reports/:loanRequestId`) reads from, so a report stays reachable from
 * any device/session, not just the browser that originally completed the
 * chat turn.
 * @param {number | string} loanRequestId
 * @returns {Promise<import('axios').AxiosResponse<StructuredLoanReport>>}
 */
export function fetchLoanReport(loanRequestId) {
  return apiClient.get(`reports/${loanRequestId}/`)
}

/**
 * @typedef {object} ChatScopedReport
 * @property {number} loan_request_id
 * @property {string | null} session_id
 * @property {string | null} loan_type
 * @property {boolean} is_islamic
 * @property {string} status
 * @property {string} created_at - ISO timestamp.
 * @property {import('./chat').ChatTurnKpis} kpis
 */

/**
 * Fetches the reports generated within one chat session from
 * `GET /api/reports/?chat_id=...` (see `backend/services/report_views.list_reports`).
 * @param {string} chatId
 * @returns {Promise<import('axios').AxiosResponse<{ chat_id: string, count: number, results: ChatScopedReport[] }>>}
 */
export function fetchReportsForChat(chatId) {
  return apiClient.get('reports/', { params: { chat_id: chatId } })
}

/**
 * The Navbar Reports drawer's "All Reports Audit Log": aggregates
 * `fetchReportsForChat` across every chat session this browser knows about
 * (see `useChatSession.getKnownSessionIds`) and merges the results. Order is
 * unspecified here — the caller (see `ReportsView`) is responsible for
 * sorting, most-recent first, before rendering.
 *
 * Per-chat requests are fanned out and merged here, so the drawer shows the
 * reports for exactly the sessions listed in this user's sidebar. A session
 * that fails (e.g. a stale/invalid id) is silently skipped rather than
 * failing the whole list.
 * @param {string[]} chatIds
 * @returns {Promise<ChatScopedReport[]>}
 */
export async function fetchAllReports(chatIds) {
  if (chatIds.length === 0) return []

  const settled = await Promise.allSettled(chatIds.map(fetchReportsForChat))
  return settled.flatMap((outcome) => (outcome.status === 'fulfilled' ? outcome.value.data.results : []))
}

/**
 * Direct-download URL for the pure DB-driven PDF export endpoint — no LLM
 * call is made when this is opened, it just streams a backend-rendered PDF.
 * @param {number} loanRequestId
 */
export function exportPdfUrl(loanRequestId) {
  const base = apiClient.defaults.baseURL.endsWith('/')
    ? apiClient.defaults.baseURL
    : `${apiClient.defaults.baseURL}/`
  return `${base}reports/export-pdf/?loan_request_id=${loanRequestId}`
}
