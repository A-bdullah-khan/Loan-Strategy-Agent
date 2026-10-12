import { Lock, MessageCircleQuestion, Sparkles } from 'lucide-react'
import Modal from './Modal'

const SECTIONS = [
  {
    icon: Sparkles,
    title: 'What we do',
    body:
      'Loan Strategy Agent is a conversational AI advisor that turns a plain-language description of your finances ' +
      'into a compared shortlist of real bank offers — conventional and Islamic, personal, home, and auto — pulled ' +
      'from live partner bank policy data rather than generic averages.',
  },
  {
    icon: Lock,
    title: 'Your data, handled carefully',
    body:
      'Your conversation is stored only so you can pick up where you left off — nothing you share is sold or used ' +
      'to market to you. The figures you provide (income, requested amount, tenure) are used solely to match you ' +
      'against bank eligibility rules for that session.',
  },
  {
    icon: MessageCircleQuestion,
    title: 'What the AI can (and can\'t) do',
    body:
      'The agent can compare policies, estimate installments, and explain eligibility criteria in plain language. ' +
      'It cannot submit a loan application on your behalf or guarantee approval — final terms are always set by ' +
      'the bank you choose to apply with.',
  },
]

/**
 * @param {{ isOpen: boolean, onClose: () => void }} props
 */
function AboutUsModal({ isOpen, onClose }) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="About Us">
      <div className="space-y-5">
        {SECTIONS.map(({ icon: Icon, title, body }) => (
          <div key={title} className="flex gap-3">
            <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full border border-emerald/30 bg-emerald/10 text-emerald">
              <Icon className="h-4.5 w-4.5" />
            </span>
            <div>
              <h3 className="text-sm font-semibold text-white">{title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-slate-400">{body}</p>
            </div>
          </div>
        ))}
      </div>
    </Modal>
  )
}

export default AboutUsModal
