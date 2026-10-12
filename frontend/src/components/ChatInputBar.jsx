import { motion } from 'framer-motion'
import { Send } from 'lucide-react'

/**
 * The single chat input bar shared by the landing hero and the docked chat
 * workspace — its parent animates its position/size via Framer Motion's
 * `layout` prop so starting a chat feels like one continuous element moving,
 * not two different inputs swapping out.
 * @param {{
 *   value: string,
 *   onChange: (value: string) => void,
 *   onSubmit: (value: string) => void,
 *   disabled?: boolean,
 *   variant?: 'hero' | 'docked',
 *   inputRef?: import('react').Ref<HTMLInputElement>,
 * }} props
 */
function ChatInputBar({ value, onChange, onSubmit, disabled = false, variant = 'hero', inputRef }) {
  function handleSubmit(event) {
    event.preventDefault()
    onSubmit(value)
  }

  const isHero = variant === 'hero'

  return (
    <form
      onSubmit={handleSubmit}
      className={`flex w-full items-center gap-2 rounded-full border border-white/10 bg-white/5 shadow-lg shadow-black/20 backdrop-blur-xl transition-colors focus-within:border-emerald/40 ${
        isHero ? 'p-2 pl-5' : 'p-1.5 pl-4'
      }`}
    >
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Type a message..."
        className={`flex-1 bg-transparent text-slate-100 placeholder:text-slate-500 focus:outline-none ${
          isHero ? 'py-2.5 text-base' : 'py-2 text-sm'
        }`}
      />
      <motion.button
        type="submit"
        disabled={!value.trim() || disabled}
        aria-label="Send message"
        whileHover={value.trim() && !disabled ? { scale: 1.08 } : undefined}
        whileTap={value.trim() && !disabled ? { scale: 0.9 } : undefined}
        transition={{ type: 'spring', stiffness: 400, damping: 20 }}
        className={`flex flex-shrink-0 items-center justify-center rounded-full bg-emerald text-white shadow-md shadow-emerald/30 transition-opacity disabled:opacity-30 disabled:shadow-none ${
          isHero ? 'h-11 w-11' : 'h-9 w-9'
        }`}
      >
        <Send className={isHero ? 'h-5 w-5' : 'h-4 w-4'} />
      </motion.button>
    </form>
  )
}

export default ChatInputBar
