import { useEffect, useState } from 'react'
import {
  AlertTriangle,
  ArrowLeft,
  CalendarClock,
  CheckCircle2,
  Download,
  ExternalLink,
  FileText,
  Gauge,
  Landmark,
  Lightbulb,
  Loader2,
  Printer,
  ShieldCheck,
  Wallet,
} from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { exportPdfUrl, fetchLoanReport } from '../services/reports'
import { formatPkr, LOAN_TYPE_LABELS } from '../utils/loanFormatting'

function bankingPreferenceLabel(isIslamic) {
  if (isIslamic === true) return 'Islamic (Shariah-compliant)'
  if (isIslamic === false) return 'Conventional'
  return 'No preference stated'
}

/**
 * One top-level KPI tile for the report header dashboard.
 * @param {{ icon: React.ComponentType, label: string, value: string, tone?: 'neutral'|'positive'|'negative', badge?: string }} props
 */
function KpiCard({ icon: Icon, label, value, tone = 'neutral', badge }) {
  const toneClasses = {
    // Bare `emerald` resolves to this project's brand shade (tailwind.config.js
    // DEFAULT) and already reads fine on print's white page, so no separate
    // print color is needed here, just a border to keep the chip visible
    // against the white card.
    neutral: 'bg-emerald/10 text-emerald print:border print:border-emerald/30',
    positive: 'bg-emerald/10 text-emerald print:border print:border-emerald/30',
    negative: 'bg-red-500/10 text-red-400 print:border print:border-red-200 print:bg-red-50 print:text-red-700',
  }
  const badgeToneClasses = {
    positive: 'border-emerald/30 bg-emerald/15 text-emerald',
    negative: 'border-red-500/30 bg-red-500/15 text-red-400 print:border-red-300 print:bg-red-50 print:text-red-700',
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4 shadow-sm shadow-black/10 print:border-slate-200 print:bg-white print:shadow-none">
      <div className={`mb-3 inline-flex h-9 w-9 items-center justify-center rounded-lg ${toneClasses[tone]}`}>
        <Icon className="h-4.5 w-4.5" />
      </div>
      <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 print:text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-bold text-white print:text-slate-900">{value}</p>
      {badge ? (
        <span
          className={`mt-2 inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${badgeToneClasses[tone] ?? badgeToneClasses.positive}`}
        >
          {badge}
        </span>
      ) : null}
    </div>
  )
}

/**
 * High-visibility banner for one entry of the structured `policy_warnings`
 * array (see `PredictiveBankAgent.build_policy_warnings`) — amber for
 * "approaching the SBP DTI cap", red for "exceeds it outright". Distinct
 * left-border + tinted-background treatment so it reads as a regulatory
 * notice, not just another card.
 * @param {{ warning: { title: string, description: string, level: 'amber'|'red' } }} props
 */
function PolicyWarningBanner({ warning }) {
  const isRed = warning.level === 'red'
  const containerTone = isRed
    ? 'border-l-4 border-red-500 bg-red-950/20 print:border-l-4 print:border-red-400 print:bg-red-50'
    : 'border-l-4 border-amber-500 bg-amber-950/20 print:border-l-4 print:border-amber-400 print:bg-amber-50'
  const iconTone = isRed ? 'text-red-400 print:text-red-600' : 'text-amber-400 print:text-amber-600'
  const titleTone = isRed ? 'text-red-200 print:text-red-900' : 'text-amber-200 print:text-amber-900'
  const bodyTone = isRed ? 'text-red-100/90 print:text-red-800' : 'text-amber-100/90 print:text-amber-800'

  return (
    <div className={`flex items-start gap-3 rounded-lg px-5 py-4 ${containerTone}`}>
      <AlertTriangle className={`mt-0.5 h-5 w-5 flex-shrink-0 ${iconTone}`} />
      <div>
        <p className={`text-sm font-extrabold uppercase tracking-wide ${titleTone}`}>{warning.title}</p>
        <p className={`mt-1 text-sm leading-relaxed ${bodyTone}`}>{warning.description}</p>
      </div>
    </div>
  )
}

/**
 * Bank Comparison Matrix — one row per entry in the structured
 * `bank_recommendations` array (see `PredictiveBankAgent.build_bank_recommendations`).
 * @param {{ banks: import('../services/chat').ChatTurnBankRecommendation[] }} props
 */
function BankComparisonTable({ banks }) {
  if (banks.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-white/10 px-4 py-6 text-center text-sm text-slate-400 print:border-slate-300 print:text-slate-500">
        No matching bank policies found in the catalog for this request.
      </p>
    )
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-white/10 print:border-slate-300">
      <table className="w-full min-w-[720px] border-collapse text-left text-xs">
        <thead className="bg-emerald/10">
          <tr>
            <th className="whitespace-nowrap px-4 py-2.5 text-[11px] font-bold uppercase tracking-wide text-emerald">Bank Name</th>
            <th className="whitespace-nowrap px-4 py-2.5 text-[11px] font-bold uppercase tracking-wide text-emerald">Loan Category</th>
            <th className="whitespace-nowrap px-4 py-2.5 text-[11px] font-bold uppercase tracking-wide text-emerald">Est. Monthly EMI</th>
            <th className="whitespace-nowrap px-4 py-2.5 text-[11px] font-bold uppercase tracking-wide text-emerald">Profit / Interest Rate</th>
            <th className="whitespace-nowrap px-4 py-2.5 text-[11px] font-bold uppercase tracking-wide text-emerald">Shariah Compliance</th>
            <th className="whitespace-nowrap px-4 py-2.5 text-[11px] font-bold uppercase tracking-wide text-emerald print:hidden">Action</th>
          </tr>
        </thead>
        <tbody>
          {banks.map((bank, index) => (
            <tr
              key={`${bank.bank_name}-${index}`}
              className="border-b border-white/5 last:border-b-0 odd:bg-white/[0.03] print:border-slate-200 print:odd:bg-slate-50"
            >
              <td className="px-4 py-3 align-middle font-semibold text-white print:text-slate-900">{bank.bank_name}</td>
              <td className="px-4 py-3 align-middle text-slate-300 print:text-slate-700">{bank.loan_type}</td>
              <td className="px-4 py-3 align-middle text-slate-200 print:text-slate-800">{formatPkr(bank.monthly_installment)}</td>
              <td className="px-4 py-3 align-middle text-slate-200 print:text-slate-800">{bank.interest_rate}% p.a.</td>
              <td className="px-4 py-3 align-middle">
                {bank.shariah_compliant ? (
                  <span className="inline-flex items-center gap-1 rounded-full border border-emerald/30 bg-emerald/15 px-2.5 py-0.5 text-[11px] font-semibold text-emerald">
                    <ShieldCheck className="h-3 w-3" />
                    Shariah Compliant
                  </span>
                ) : (
                  <span className="inline-block rounded-full border border-white/10 bg-white/5 px-2.5 py-0.5 text-[11px] font-semibold text-slate-300 print:border-slate-300 print:bg-slate-100 print:text-slate-600">
                    Conventional
                  </span>
                )}
              </td>
              <td className="px-4 py-3 align-middle print:hidden">
                {bank.apply_url ? (
                  <a
                    href={bank.apply_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 rounded-lg bg-emerald/15 px-2.5 py-1 text-[11px] font-semibold text-emerald transition-colors hover:bg-emerald/25"
                  >
                    Apply
                    <ExternalLink className="h-3 w-3" />
                  </a>
                ) : (
                  <span className="text-[11px] text-slate-500">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * Strategic Actionable Next Steps — one entry per plain string in the
 * structured `strategic_steps` array (see `PredictiveBankAgent.build_strategic_steps`).
 * @param {{ steps: string[] }} props
 */
function StrategicStepsCard({ steps }) {
  return (
    <section className="rounded-xl border border-white/10 bg-white/5 p-5 print:border-slate-200 print:bg-white sm:p-6">
      <h2 className="mb-4 flex items-center gap-2 text-base font-bold text-white print:text-slate-900">
        <Lightbulb className="h-5 w-5 text-emerald" />
        Strategic Actionable Next Steps
      </h2>
      <ol className="space-y-3">
        {steps.map((step, index) => (
          <li key={index} className="flex items-start gap-3">
            <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-emerald/15 text-xs font-bold text-emerald print:border print:border-emerald/30">
              {index + 1}
            </span>
            <span className="flex items-start gap-2 text-sm leading-relaxed text-slate-300 print:text-slate-700">
              <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-emerald" />
              {step}
            </span>
          </li>
        ))}
      </ol>
    </section>
  )
}

function CenteredMessage({ icon: Icon, title, description, children }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-navy px-6 text-center text-white">
      <Icon className="h-10 w-10 text-slate-600" />
      <p className="text-lg font-semibold">{title}</p>
      {description ? <p className="max-w-sm text-sm text-slate-400">{description}</p> : null}
      {children}
    </div>
  )
}

/**
 * Full-page Executive Financial Report view, at `/reports/:loanRequestId`.
 *
 * Styled as an executive-level Fintech Dashboard: a top KPI grid (Requested
 * Amount, Tenure, Monthly Income, DTI Ratio & Eligibility), the SBP policy
 * warning(s) as high-visibility amber/red banners, the bank comparison
 * matrix, and a Strategic Actionable Next Steps card — all mapped straight
 * from the structured report payload (`kpis`, `policy_warnings`,
 * `bank_recommendations`, `strategic_steps`) returned by
 * `GET /api/reports/:loanRequestId/` (see `backend/services/report_views.py`
 * and `report_data.build_report_for_loan_request`). Pure DB-to-JSON on the
 * backend — no LLM/Groq call happens from opening this page, and unlike the
 * old browser-local-only render, it works from any device/session since the
 * source of truth is the saved `LoanRequest` row, not localStorage.
 *
 * `print:` utility classes throughout switch the page from its dark theme to
 * a light, ink-friendly one for Print/Export to PDF.
 */
function ReportPage() {
  const { loanRequestId } = useParams()
  // Remounts (fresh 'loading' state, no stale report) whenever the route
  // param itself changes — e.g. navigating from one report straight to
  // another — instead of resetting state imperatively inside the effect.
  return <ReportPageContent key={loanRequestId} loanRequestId={loanRequestId} />
}

function ReportPageContent({ loanRequestId }) {
  const [report, setReport] = useState(null)
  const [status, setStatus] = useState('loading') // 'loading' | 'ready' | 'not-found' | 'error'

  useEffect(() => {
    let cancelled = false

    fetchLoanReport(loanRequestId)
      .then(({ data }) => {
        if (cancelled) return
        setReport(data)
        setStatus('ready')
      })
      .catch((err) => {
        if (cancelled) return
        setStatus(err?.response?.status === 404 ? 'not-found' : 'error')
      })

    return () => {
      cancelled = true
    }
  }, [loanRequestId])

  if (status === 'loading') {
    return (
      <CenteredMessage icon={Loader2} title="Loading report…">
        <Loader2 className="h-6 w-6 animate-spin text-emerald" />
      </CenteredMessage>
    )
  }

  if (status === 'error') {
    return (
      <CenteredMessage
        icon={AlertTriangle}
        title="Couldn't load this report"
        description="Something went wrong reaching the loan strategy service. Please try again shortly."
      >
        <Link
          to="/app"
          className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-emerald px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald/90"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Workspace
        </Link>
      </CenteredMessage>
    )
  }

  if (status === 'not-found' || !report) {
    return (
      <CenteredMessage
        icon={FileText}
        title="Report not found"
        description="This loan request doesn't exist, or you don't have access to it."
      >
        <Link
          to="/app"
          className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-emerald px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald/90"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Workspace
        </Link>
      </CenteredMessage>
    )
  }

  const loanTypeLabel = LOAN_TYPE_LABELS[report.loan_type] || report.loan_type || 'Loan'
  const isEligible = report.kpis.eligibility_status === 'Eligible'

  return (
    <div className="min-h-screen bg-navy text-white print:bg-white print:text-slate-900">
      <header className="sticky top-0 z-10 border-b border-white/10 bg-navy/95 backdrop-blur-sm print:hidden">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-3 px-4 py-4 sm:px-6">
          <Link
            to="/app"
            className="flex flex-shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm text-slate-300 transition-colors hover:bg-white/10 hover:text-white"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="hidden sm:inline">Back</span>
          </Link>
          <h1 className="truncate text-sm font-semibold text-white sm:text-base">Executive Financial Report</h1>
          <div className="flex flex-shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() => window.print()}
              className="flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-sm font-medium text-slate-200 transition-colors hover:bg-white/10"
            >
              <Printer className="h-4 w-4" />
              <span className="hidden sm:inline">Print</span>
            </button>
            <a
              href={exportPdfUrl(report.loan_request_id)}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 rounded-lg bg-emerald px-2.5 py-1.5 text-sm font-semibold text-white shadow-md shadow-emerald/20 transition-colors hover:bg-emerald/90"
            >
              <Download className="h-4 w-4" />
              <span className="hidden sm:inline">Export PDF</span>
            </a>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center rounded-full border border-emerald/30 bg-emerald/10 px-3 py-1 text-xs font-semibold text-emerald">
              {loanTypeLabel}
            </span>
            <span className="text-xs text-slate-400 print:text-slate-500">
              Preferred Banking: {bankingPreferenceLabel(report.is_islamic)}
            </span>
          </div>
          <p className="text-xs text-slate-500">Loan Request #{report.loan_request_id}</p>
        </div>

        {/* 1. Top KPI Grid — mapped straight from `report.kpis` */}
        <section className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <KpiCard icon={Wallet} label="Requested Loan Amount" value={formatPkr(report.kpis.requested_amount)} />
          <KpiCard icon={CalendarClock} label="Loan Tenure" value={`${report.kpis.tenure} Yrs`} />
          <KpiCard icon={Landmark} label="Monthly Income" value={formatPkr(report.kpis.monthly_income)} />
          <KpiCard
            icon={Gauge}
            label="DTI Ratio & Eligibility"
            value={report.kpis.dti_ratio}
            tone={isEligible ? 'positive' : 'negative'}
            badge={report.kpis.eligibility_status}
          />
        </section>

        {/* 2. Policy Ceiling & SBP Warning Banner(s) */}
        {report.policy_warnings.length > 0 ? (
          <section className="mb-8 space-y-3">
            {report.policy_warnings.map((warning, index) => (
              <PolicyWarningBanner key={index} warning={warning} />
            ))}
          </section>
        ) : null}

        {/* 3. Bank Comparison Matrix */}
        <section className="mb-8">
          <h2 className="mb-3 flex items-center gap-2 text-base font-bold text-white print:text-slate-900">
            <Landmark className="h-5 w-5 text-emerald" />
            Bank Comparison Matrix
          </h2>
          <BankComparisonTable banks={report.bank_recommendations} />
        </section>

        {/* 4. Strategic Actionable Next Steps */}
        <StrategicStepsCard steps={report.strategic_steps} />

        <p className="mt-6 flex items-center justify-center gap-1.5 text-[11px] text-slate-500 print:hidden">
          <FileText className="h-3.5 w-3.5" />
          Rendered directly from the database — no AI call involved.
        </p>
      </main>
    </div>
  )
}

export default ReportPage
