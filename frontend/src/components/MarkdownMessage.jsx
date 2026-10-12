import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// Chat replies are generated as short, natural-language prose plus a one-line
// SBP blockquote and a couple of short bullet lists (see
// `services.financial_calculator.PredictiveBankAgent.format_chat_summary` /
// `mcp_server.agent.run_chat_agent`) and should never contain a Markdown
// table or a fenced JSON/code block — the full Bank Comparison Matrix and KPI
// cards live only on the dedicated report page (`/reports/:id`). This is a
// client-side backstop in case a reply ever slips through with one anyway:
// strip it before rendering rather than let it render as a full table/code
// block inside the chat bubble.
const TABLE_BLOCK_REGEX = /^ {0,3}\|.*\|[ \t]*\n {0,3}\|?[ \t:|-]+\|[ \t:|-]*\n(?: {0,3}\|.*\|[ \t]*\n?)*/gm
const FENCED_CODE_BLOCK_REGEX = /```[\s\S]*?```/g
const REDIRECT_NOTE = '_The full breakdown is available anytime in your Reports tab._'

function stripHeavyStructures(content) {
  if (typeof content !== 'string' || content.length === 0) return content

  let stripped = false
  let result = content.replace(TABLE_BLOCK_REGEX, () => {
    stripped = true
    return ''
  })
  result = result.replace(FENCED_CODE_BLOCK_REGEX, () => {
    stripped = true
    return ''
  })

  if (!stripped) return content
  const cleaned = result.replace(/\n{3,}/g, '\n\n').trim()
  return cleaned ? `${cleaned}\n\n${REDIRECT_NOTE}` : REDIRECT_NOTE
}

/**
 * Plain-text redirect shown in place of any table that still reaches
 * ReactMarkdown (e.g. malformed pipe syntax the regex above didn't catch) —
 * a hard backstop so a real `<table>` never renders inside a chat bubble.
 */
function TableFallback() {
  return (
    <p className="mb-2 rounded-lg border border-dashed border-white/10 px-3 py-2 text-xs italic text-slate-400 last:mb-0">
      {REDIRECT_NOTE.replaceAll('_', '')}
    </p>
  )
}

// Marks a matched financial figure (currency amount or percentage, plus an
// optional trailing label like "DTI"/"EMI"/"p.a.") so it survives the trip
// through ReactMarkdown as an inline-code node the `code` component below
// can recognize and re-render as a metric chip, instead of literal code.
const METRIC_SENTINEL = ''
const METRIC_REGEX =
  /\*{0,2}((?:PKR\s?[\d,]+(?:\.\d+)?)|(?:\d+(?:\.\d+)?%))(\s+(?:DTI|EMI|APR|LTV|markup|p\.a\.))?\*{0,2}/g

function highlightMetrics(content) {
  if (typeof content !== 'string' || content.length === 0) return content
  return content.replace(METRIC_REGEX, (_match, amount, label) => `\`${METRIC_SENTINEL}${amount}${label ?? ''}\``)
}

/**
 * Executive-grade Tailwind styling for conversational chat replies:
 * financial figures as emerald metric chips, the SBP compliance line as a
 * left-accent callout banner, bank-recommendation/next-step bullets as
 * checkmark rows, and bold/link/paragraph treatment for everything else. No
 * Markdown tables or JSON/code blocks ever render here — those stay on the
 * dedicated report page.
 */
const markdownComponents = {
  h1: ({ children }) => <p className="mb-2 text-sm font-bold text-white first:mt-0">{children}</p>,
  h2: ({ children }) => <p className="mb-2 text-sm font-bold text-white first:mt-0">{children}</p>,
  h3: ({ children }) => <p className="mb-2 text-sm font-bold text-white first:mt-0">{children}</p>,
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-emerald-400">{children}</strong>,
  em: ({ children }) => <em className="italic text-slate-200">{children}</em>,
  ul: ({ children }) => (
    <ul
      className={
        'my-2 list-none space-y-1.5 pl-0 last:mb-0 ' +
        "[&>li]:relative [&>li]:pl-5 [&>li]:before:absolute [&>li]:before:left-0 [&>li]:before:top-px " +
        "[&>li]:before:font-bold [&>li]:before:text-emerald-500 [&>li]:before:content-['✓']"
      }
    >
      {children}
    </ul>
  ),
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5 marker:text-emerald-400 last:mb-0">{children}</ol>,
  li: ({ children }) => <li className="leading-snug">{children}</li>,
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="font-medium text-emerald-400 underline underline-offset-2 hover:text-emerald-300"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <div className="my-2 rounded-r-lg border-l-4 border-emerald-500 bg-slate-800/50 p-3 text-slate-200">
      {children}
    </div>
  ),
  code: ({ children }) => {
    const text = String(children)
    if (text.startsWith(METRIC_SENTINEL)) {
      return (
        <span className="inline-flex items-center rounded-md border border-emerald-800/50 bg-emerald-950/40 px-2 py-0.5 font-mono text-[0.85em] text-emerald-400">
          {text.slice(1)}
        </span>
      )
    }
    return <code className="rounded bg-white/10 px-1 py-0.5 font-mono text-[0.8em] text-emerald-400">{children}</code>
  },
  pre: TableFallback,
  hr: () => <hr className="my-3 border-white/10" />,
  table: TableFallback,
  thead: () => null,
  tbody: () => null,
  tr: () => null,
  th: () => null,
  td: () => null,
}

/**
 * Renders assistant/user chat content as polished, conversational Markdown —
 * metric chips, a compliance callout banner, checkmark bullet lists, bold
 * highlights, and links. No Markdown tables, raw JSON/code blocks, or
 * dashboard-style structured cards ever render here; those heavier
 * structures are confined to the dedicated report page/modal.
 * @param {{ content: string }} props
 */
function MarkdownMessage({ content }) {
  return (
    <div className="space-y-1">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {highlightMetrics(stripHeavyStructures(content))}
      </ReactMarkdown>
    </div>
  )
}

export default MarkdownMessage
