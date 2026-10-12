import { motion } from 'framer-motion'
import { User } from 'lucide-react'
import AiAvatar from './AiAvatar'
import ActionCards from './ChatActionCards'
import MarkdownMessage from './MarkdownMessage'

/**
 * One turn in the chat stream: avatar plus the message bubble. The AI's
 * bubble is short, natural-language conversational text — rendered via
 * `MarkdownMessage` as metric chips, an SBP compliance callout, and
 * checkmark bullet lists — but never a Markdown table, fenced JSON/code
 * block, or full KPI dashboard; the full Bank Comparison Matrix stays
 * confined to the dedicated report page, reachable only from the Navbar's
 * Reports drawer (see `ReportsView`) at `/reports/:id`.
 * @param {{ message: { id: string, role: 'user' | 'assistant', content: string, extras?: object | null, toolCalls: Array } }} props
 */
function ChatMessage({ message }) {
  const isUser = message.role === 'user'

  // Defensive guard: content should already be a plain string by the time it
  // reaches state, but never render a raw object as a React child if a
  // backend response shape slips through unnormalized.
  const bodyText =
    typeof message.content === 'object' && message.content !== null
      ? (message.content.text ?? '')
      : (message.content ?? '')

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={isUser ? 'flex justify-end' : 'flex justify-start'}
    >
      <div className={`flex max-w-[85%] items-start gap-2.5 ${isUser ? 'flex-row-reverse' : ''}`}>
        {isUser ? (
          <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-emerald to-emerald/70 text-white shadow-md shadow-emerald/20">
            <User className="h-3.5 w-3.5" />
          </div>
        ) : (
          <AiAvatar />
        )}
        <div className="min-w-0">
          <div
            className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
              isUser
                ? 'rounded-br-md bg-gradient-to-br from-emerald via-emerald to-teal-600 text-white shadow-md shadow-emerald/30'
                : 'rounded-bl-sm border border-slate-800 bg-slate-900/90 text-slate-100 shadow-lg shadow-black/20'
            }`}
          >
            {isUser ? (
              // The rich Markdown treatment (metric pills, alert banners)
              // is tuned for AI-generated financial analysis; on the
              // user's own gradient bubble a currency pill's emerald text
              // disappears against the emerald background, so raw input
              // renders as plain text instead.
              <p className="whitespace-pre-wrap">{bodyText}</p>
            ) : (
              <MarkdownMessage content={bodyText} />
            )}
          </div>
          {message.extras && typeof message.extras === 'string' ? (
            <p className="mt-1.5 text-xs text-slate-400">{message.extras}</p>
          ) : null}
          <ActionCards toolCalls={message.toolCalls} />
        </div>
      </div>
    </motion.div>
  )
}

export default ChatMessage
