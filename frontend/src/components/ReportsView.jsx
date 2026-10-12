import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Calendar, FileBarChart2, Loader2, Wallet } from 'lucide-react'
import { Link } from 'react-router-dom'
import { getKnownSessionIds } from '../hooks/useChatSession'
import { fetchAllReports } from '../services/reports'

// The chat agent's `update_loan_state` tool stores loan_type exactly as
// "Personal" / "Home" / "Vehicle" (see backend mcp_server/agent.py) — not
// the lowercase users.models.LoanRequestType values, which only exist once
// a LoanRequest row is created server-side.
const LOAN_TYPE_LABELS = {
  Personal: 'Personal Loan',
  Home: 'Home Loan',
  Vehicle: 'Vehicle Loan',
}

function formatPkr(amount) {
  if (amount === null || amount === undefined) return '—'
  return `PKR ${Number(amount).toLocaleString()}`
}

function formatDate(isoString) {
  try {
    return new Date(isoString).toLocaleString(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    })
  } catch {
    return isoString
  }
}

/**
 * One loan request's audit-log card: loan category badge, requested amount,
 * created date/time, and a CTA into the full-page report view at
 * `/reports/:loanRequestId`.
 * @param {{ report: import('../services/reports').ChatScopedReport }} props
 */
function ReportCard({ report }) {
  const loanTypeLabel = LOAN_TYPE_LABELS[report.loan_type] || report.loan_type || 'Loan'

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4 transition-colors hover:border-emerald/30">
      <div className="flex items-start justify-between gap-2">
        <div>
          <span className="inline-flex items-center rounded-full border border-emerald/30 bg-emerald/10 px-2.5 py-0.5 text-xs font-semibold text-emerald">
            {loanTypeLabel}
          </span>
          <p className="mt-2 flex items-center gap-1.5 text-xs text-slate-500">
            <Calendar className="h-3.5 w-3.5" />
            {formatDate(report.created_at)}
          </p>
        </div>
        <FileBarChart2 className="h-5 w-5 flex-shrink-0 text-slate-500" />
      </div>

      <div className="mt-3 rounded-lg bg-white/5 px-2.5 py-2">
        <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">Requested Amount</p>
        <p className="mt-0.5 truncate text-sm font-bold text-white">{formatPkr(report.kpis?.requested_amount)}</p>
      </div>

      <Link
        to={`/reports/${report.loan_request_id}`}
        className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg bg-emerald/15 px-3 py-1.5 text-xs font-semibold text-emerald transition-colors hover:bg-emerald/25"
      >
        <Wallet className="h-3.5 w-3.5" />
        View Report
      </Link>
    </div>
  )
}

/**
 * Reports tab content: the "All Reports Audit Log" — every completed loan
 * request across every chat session this browser knows about, fetched live
 * from the backend (`GET /api/reports/?chat_id=...`, see
 * `services/reports.fetchAllReports`) rather than a browser-local snapshot,
 * so a session deleted elsewhere (which cascades-purges its reports
 * server-side — see `backend/mcp_server/chat_history.py`) never lingers
 * here: this view re-fetches fresh every time the drawer opens (it remounts
 * on each open — see `components/modals/Modal`, which unmounts its children
 * while closed).
 */
function ReportsView() {
  const [status, setStatus] = useState('loading') // 'loading' | 'ready' | 'error'
  const [reports, setReports] = useState([])

  // Strictly most-recent-first — the backend/service fan-out that produces
  // `reports` makes no ordering guarantee (it's N per-session responses
  // merged together), so sorting is owned here, at render time.
  const sortedReports = useMemo(
    () => [...reports].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)),
    [reports],
  )

  useEffect(() => {
    let cancelled = false

    fetchAllReports(getKnownSessionIds())
      .then((results) => {
        if (cancelled) return
        setReports(results)
        setStatus('ready')
      })
      .catch(() => {
        if (cancelled) return
        setStatus('error')
      })

    return () => {
      cancelled = true
    }
  }, [])

  if (status === 'loading') {
    return (
      <div className="flex items-center justify-center gap-2 px-4 py-10 text-sm text-slate-400">
        <Loader2 className="h-4 w-4 animate-spin text-emerald" />
        Loading your reports…
      </div>
    )
  }

  if (status === 'error') {
    return (
      <div className="rounded-xl border border-dashed border-white/10 px-4 py-10 text-center">
        <AlertTriangle className="mx-auto h-8 w-8 text-slate-600" />
        <p className="mt-3 text-sm text-slate-400">Couldn't load your reports right now. Please try again shortly.</p>
      </div>
    )
  }

  return (
    <div>
      {sortedReports.length === 0 ? (
        <div className="rounded-xl border border-dashed border-white/10 px-4 py-10 text-center">
          <FileBarChart2 className="mx-auto h-8 w-8 text-slate-600" />
          <p className="mt-3 text-sm text-slate-400">
            No loan reports yet. Complete a loan request in the chat to see it here.
          </p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {sortedReports.map((report) => (
            <ReportCard key={report.loan_request_id} report={report} />
          ))}
        </div>
      )}
    </div>
  )
}

export default ReportsView
