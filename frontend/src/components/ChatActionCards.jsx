import { Landmark } from 'lucide-react'

function BankDetailsCard({ result }) {
  if (!result.found) return null
  return (
    <div className="min-w-[220px] flex-shrink-0 rounded-xl border border-white/10 bg-white/5 p-4 shadow-lg shadow-black/10 backdrop-blur-xl">
      <p className="flex items-center gap-1.5 text-sm font-semibold text-white">
        <Landmark className="h-4 w-4 text-emerald" />
        {result.name}
      </p>
      <p className="mt-1 text-xs text-slate-400">{result.is_islamic ? 'Islamic bank' : 'Conventional bank'}</p>
      <a
        href={result.main_page_url}
        target="_blank"
        rel="noreferrer"
        className="mt-2 inline-block text-xs font-medium text-emerald hover:underline"
      >
        Visit website
      </a>
    </div>
  )
}

/**
 * Renders the result cards for one assistant turn's tool calls.
 *
 * Deliberately narrow: `search_loans` (the Bank Comparison Matrix) and
 * `calculate_user_eligibility` (the KPI/DTI card) are never rendered here —
 * that structured, report-grade content is confined to the dedicated report
 * page (see `ChatMessage`'s doc comment and `pages/ReportPage.jsx`). Only
 * `get_bank_details` gets an inline card, since it's a lightweight, single-
 * bank identity lookup, not a comparison/KPI structure.
 * @param {{ toolCalls: Array<{ name: string, result: object }> }} props
 */
function ActionCards({ toolCalls }) {
  if (!toolCalls || toolCalls.length === 0) return null

  const cards = toolCalls.flatMap((call) => {
    if (call.name === 'get_bank_details' && call.result) {
      return [<BankDetailsCard key="bank" result={call.result} />]
    }
    return []
  })

  if (cards.length === 0) return null

  return <div className="mt-3 flex gap-3 overflow-x-auto pb-1">{cards}</div>
}

export default ActionCards
