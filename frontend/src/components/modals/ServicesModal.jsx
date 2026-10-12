import { useState } from 'react'
import { Calculator, Car, ShieldCheck, Wallet } from 'lucide-react'
import Modal from './Modal'

const SERVICES = [
  {
    icon: Wallet,
    title: 'Personal Loans',
    description:
      'Unsecured financing for any purpose — compared across every partner bank\'s income, tenure, and DTI rules.',
  },
  {
    icon: Car,
    title: 'Auto Loans',
    description: 'Vehicle financing with the lowest total cost of ownership, conventional or Islamic.',
  },
  {
    icon: ShieldCheck,
    title: 'Islamic Financing',
    description: 'Shariah-compliant profit-rate products, filtered separately so conventional interest never mixes in.',
  },
]

// General personal-finance DTI guidance (not a specific bank's policy) — see
// backend LoanPolicy.max_dti_percentage for how partner banks actually gate
// eligibility once a real application is compared.
const DTI_BANDS = [
  { max: 20, label: 'Excellent', tone: 'text-emerald' },
  { max: 36, label: 'Good', tone: 'text-emerald' },
  { max: 43, label: 'Borderline', tone: 'text-gold' },
  { max: Infinity, label: 'High risk', tone: 'text-red-400' },
]

function dtiVerdict(dti) {
  return DTI_BANDS.find((band) => dti <= band.max)
}

function DtiCalculatorCard() {
  const [income, setIncome] = useState('')
  const [debt, setDebt] = useState('')

  const incomeNum = Number(income)
  const debtNum = Number(debt)
  const hasValidInput = incomeNum > 0 && debtNum >= 0
  const dti = hasValidInput ? (debtNum / incomeNum) * 100 : null
  const verdict = dti !== null ? dtiVerdict(dti) : null

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <span className="flex h-9 w-9 items-center justify-center rounded-full bg-gold/15 text-gold">
        <Calculator className="h-4.5 w-4.5" />
      </span>
      <h3 className="mt-3 text-sm font-semibold text-white">DTI Calculator</h3>
      <p className="mt-1 text-sm text-slate-400">
        Your debt-to-income ratio — the single biggest factor banks weigh for eligibility.
      </p>

      <div className="mt-3 grid grid-cols-2 gap-2">
        <div>
          <label htmlFor="dti-income" className="mb-1 block text-[11px] font-medium text-slate-500">
            Monthly Income (PKR)
          </label>
          <input
            id="dti-income"
            type="number"
            min="0"
            inputMode="decimal"
            value={income}
            onChange={(event) => setIncome(event.target.value)}
            placeholder="150000"
            className="w-full rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-sm text-slate-100 placeholder:text-slate-600 focus:border-emerald/40 focus:outline-none"
          />
        </div>
        <div>
          <label htmlFor="dti-debt" className="mb-1 block text-[11px] font-medium text-slate-500">
            Monthly Debt (PKR)
          </label>
          <input
            id="dti-debt"
            type="number"
            min="0"
            inputMode="decimal"
            value={debt}
            onChange={(event) => setDebt(event.target.value)}
            placeholder="30000"
            className="w-full rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-sm text-slate-100 placeholder:text-slate-600 focus:border-emerald/40 focus:outline-none"
          />
        </div>
      </div>

      {dti !== null ? (
        <p className="mt-3 text-sm">
          <span className="font-semibold text-white">{dti.toFixed(1)}% DTI</span>{' '}
          <span className={verdict.tone}>· {verdict.label}</span>
        </p>
      ) : (
        <p className="mt-3 text-xs text-slate-500">Enter both figures to see your ratio.</p>
      )}
    </div>
  )
}

/**
 * @param {{ isOpen: boolean, onClose: () => void }} props
 */
function ServicesModal({ isOpen, onClose }) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Key Services">
      <div className="grid gap-3 sm:grid-cols-2">
        {SERVICES.map(({ icon: Icon, title, description }) => (
          <div key={title} className="rounded-xl border border-white/10 bg-white/5 p-4">
            <span className="flex h-9 w-9 items-center justify-center rounded-full border border-emerald/30 bg-emerald/10 text-emerald">
              <Icon className="h-4.5 w-4.5" />
            </span>
            <h3 className="mt-3 text-sm font-semibold text-white">{title}</h3>
            <p className="mt-1 text-sm text-slate-400">{description}</p>
          </div>
        ))}
        <DtiCalculatorCard />
      </div>
    </Modal>
  )
}

export default ServicesModal
