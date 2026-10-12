import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Calculator, Landmark, Percent, Scale } from 'lucide-react'
import AiAvatar from '../components/AiAvatar'
import ChatInputBar from '../components/ChatInputBar'
import ChatMessage from '../components/ChatMessage'
import TypingIndicator from '../components/TypingIndicator'

const STARTER_PROMPTS = [
  { icon: Calculator, text: 'Analyze my DTI ratio' },
  { icon: Scale, text: 'Compare Auto Loans' },
  { icon: Percent, text: 'Personal Loan Eligibility' },
]

/**
 * @param {{ chatSession: ReturnType<typeof import('../hooks/useChatSession').useChatSession> }} props
 */
function Home({ chatSession }) {
  const { messages, hasStarted, isTyping, sendMessage } = chatSession
  const [input, setInput] = useState('')
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  // A plain effect ref only fires on re-render, but AnimatePresence's
  // `mode="wait"` on the hero/workspace switch below delays mounting this
  // sentinel until the hero's exit transition finishes — after the effect
  // below has already run once against a null ref. The callback ref catches
  // that first, delayed mount; the effect handles every message afterward.
  const setMessagesEndRef = useCallback((node) => {
    messagesEndRef.current = node
    node?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, isTyping])

  function handleSubmit(text) {
    sendMessage(text)
    setInput('')
  }

  function handleStarterClick(text) {
    setInput(text)
    handleSubmit(text)
  }

  return (
    <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden bg-slate-950">
      <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-24 left-1/4 h-80 w-80 rounded-full bg-emerald/20 blur-3xl" />
        <div className="absolute bottom-0 right-1/5 h-96 w-96 rounded-full bg-navy blur-3xl" />
      </div>

      <div className="relative z-10 flex min-h-0 flex-1 flex-col">
        <AnimatePresence mode="wait">
          {!hasStarted ? (
            <motion.div
              key="welcome"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, y: -16 }}
              transition={{ duration: 0.25 }}
              className="flex flex-1 flex-col items-center justify-center px-6 text-center"
            >
              <span className="flex h-12 w-12 items-center justify-center rounded-full border border-emerald/30 bg-emerald/10 text-emerald">
                <Landmark className="h-6 w-6" />
              </span>
              <h1 className="mt-4 bg-gradient-to-r from-emerald via-emerald to-gold bg-clip-text text-4xl font-bold text-transparent sm:text-5xl">
                Loan Strategy Agent
              </h1>
              <p className="mt-3 max-w-xl text-sm text-slate-400 sm:text-base">
                Smart Financial &amp; Loan Strategy Advisor
              </p>

              <motion.button
                type="button"
                onClick={() => inputRef.current?.focus()}
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                transition={{ type: 'spring', stiffness: 400, damping: 20 }}
                className="mt-6 rounded-full bg-emerald px-6 py-2.5 text-sm font-medium text-white shadow-md shadow-emerald/30"
              >
                Start Strategy Chat
              </motion.button>

              <div className="mt-8 grid w-full max-w-2xl grid-cols-1 gap-3 sm:grid-cols-3">
                {STARTER_PROMPTS.map(({ icon: Icon, text }) => (
                  <motion.button
                    key={text}
                    type="button"
                    onClick={() => handleStarterClick(text)}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    transition={{ type: 'spring', stiffness: 400, damping: 20 }}
                    className="flex items-center gap-2.5 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-left text-sm text-slate-300 backdrop-blur-xl transition-colors hover:border-emerald/40 hover:bg-emerald/10 hover:text-white"
                  >
                    <Icon className="h-4 w-4 flex-shrink-0 text-emerald" />
                    <span>{text}</span>
                  </motion.button>
                ))}
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="workspace"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.3, delay: 0.1 }}
              className="mx-auto flex w-full min-h-0 max-w-3xl flex-1 flex-col px-4"
            >
              <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-6">
                {(messages || []).map((message) => (
                  <ChatMessage key={message.id} message={message} />
                ))}

                {isTyping ? (
                  <div className="flex justify-start">
                    <div className="flex items-start gap-2.5">
                      <AiAvatar />
                      <TypingIndicator />
                    </div>
                  </div>
                ) : null}
                <div ref={setMessagesEndRef} />
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <motion.div
          layout
          transition={{ type: 'spring', stiffness: 260, damping: 28 }}
          className={
            hasStarted
              ? 'sticky bottom-0 z-10 mx-auto w-full max-w-3xl border-t border-white/10 bg-slate-950/80 px-4 pb-6 pt-3 backdrop-blur-xl'
              : 'mx-auto w-full max-w-2xl px-6 pb-24'
          }
        >
          <ChatInputBar
            inputRef={inputRef}
            value={input}
            onChange={setInput}
            onSubmit={handleSubmit}
            disabled={isTyping}
            variant={hasStarted ? 'docked' : 'hero'}
          />
        </motion.div>
      </div>
    </div>
  )
}

export default Home
