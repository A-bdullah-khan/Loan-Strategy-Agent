import { motion } from 'framer-motion'

const SKELETON_LINE_WIDTHS = ['w-40', 'w-52', 'w-28']

/**
 * Branded skeleton shimmer shown while the assistant composes a reply —
 * pulsing bars standing in for the lines of the reply about to stream in.
 * Replaces the old three-dot "typing" indicator with something that reads
 * as "drafting your report" rather than just "waiting".
 */
function TypingIndicator() {
  return (
    <div className="space-y-2 rounded-2xl rounded-bl-sm border border-slate-800 bg-slate-900/90 px-4 py-3 shadow-lg shadow-black/20">
      {SKELETON_LINE_WIDTHS.map((width, i) => (
        <motion.div
          key={width}
          className={`h-2.5 ${width} rounded-full bg-gradient-to-r from-emerald/50 via-emerald/15 to-transparent`}
          animate={{ opacity: [0.35, 1, 0.35] }}
          transition={{ duration: 1.4, repeat: Infinity, delay: i * 0.15, ease: 'easeInOut' }}
        />
      ))}
    </div>
  )
}

export default TypingIndicator
