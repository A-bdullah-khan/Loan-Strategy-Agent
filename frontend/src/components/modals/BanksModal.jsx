import Modal from './Modal'

// Mirrors the bank + LoanPolicy records seeded in the backend
// (banks.models.Bank / LoanPolicy) — the same partner banks and personal
// loan profit rates the chat agent actually compares. Standard Chartered and
// Dubai Islamic Bank are the international-group entries in that data;
// everything else is a domestic Pakistani bank.
const BANKS = [
  { name: 'HBL', origin: 'Pakistani', islamic: false, rate: 35.99 },
  { name: 'UBL', origin: 'Pakistani', islamic: false, rate: 22.0 },
  { name: 'MCB', origin: 'Pakistani', islamic: false, rate: 22.0 },
  { name: 'ABL', origin: 'Pakistani', islamic: false, rate: 22.0 },
  { name: 'Bank Alfalah', origin: 'Pakistani', islamic: false, rate: 22.0 },
  { name: 'Askari Bank', origin: 'Pakistani', islamic: false, rate: 22.0 },
  { name: 'JS Bank', origin: 'Pakistani', islamic: false, rate: 22.0 },
  { name: 'BOP', origin: 'Pakistani', islamic: false, rate: 22.0 },
  { name: 'Meezan Bank', origin: 'Pakistani', islamic: true, rate: 22.0 },
  { name: 'BankIslami', origin: 'Pakistani', islamic: true, rate: 22.0 },
  { name: 'Faysal Bank', origin: 'Pakistani', islamic: true, rate: 22.0 },
  { name: 'Standard Chartered', origin: 'International', islamic: false, rate: 22.0 },
  { name: 'Dubai Islamic Bank', origin: 'International', islamic: true, rate: 14.7 },
]

function initialsFor(name) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join('')
}

/**
 * @param {{ isOpen: boolean, onClose: () => void }} props
 */
function BanksModal({ isOpen, onClose }) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Banks">
      <p className="mb-4 text-sm text-slate-400">
        Live policy data across {BANKS.length} conventional and Islamic banks, Pakistani and international. Rates
        shown are each bank&apos;s personal loan profit rate — home and auto rates vary and are compared live in
        chat.
      </p>
      <div className="grid gap-2.5 sm:grid-cols-2">
        {BANKS.map((bank) => (
          <div
            key={bank.name}
            className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 p-3 transition-colors hover:border-emerald/30"
          >
            <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-emerald/15 text-sm font-semibold text-emerald">
              {initialsFor(bank.name)}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-white">{bank.name}</p>
              <div className="mt-0.5 flex flex-wrap items-center gap-1">
                <span
                  className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
                    bank.islamic ? 'bg-emerald/15 text-emerald' : 'bg-white/10 text-slate-300'
                  }`}
                >
                  {bank.islamic ? 'Islamic' : 'Conventional'}
                </span>
                {bank.origin === 'International' ? (
                  <span className="rounded-full bg-gold/15 px-1.5 py-0.5 text-[10px] font-medium text-gold">
                    International
                  </span>
                ) : null}
              </div>
            </div>
            <span className="flex-shrink-0 text-right text-sm font-bold text-white">
              {bank.rate}%<span className="block text-[10px] font-normal text-slate-500">p.a.</span>
            </span>
          </div>
        ))}
      </div>
    </Modal>
  )
}

export default BanksModal
