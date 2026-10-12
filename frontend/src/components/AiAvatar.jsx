import { Sparkles } from 'lucide-react'

/**
 * The assistant's distinct avatar/badge — a gradient emblem with a live
 * status dot, used everywhere an AI turn needs an avatar (chat bubbles, the
 * typing indicator) so the identity reads consistently across the workspace.
 */
function AiAvatar() {
  return (
    <div className="relative flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-emerald to-teal-600 text-white shadow-md shadow-emerald/30">
      <Sparkles className="h-3.5 w-3.5" />
      <span className="absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full border-2 border-slate-950 bg-emerald" />
    </div>
  )
}

export default AiAvatar
