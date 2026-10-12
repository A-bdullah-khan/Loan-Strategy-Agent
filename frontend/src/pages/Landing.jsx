import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Banknote, Home as HomeIcon, Landmark, ShieldCheck, Sparkles, TrendingUp, Wallet } from 'lucide-react'
import AuthCard from '../components/AuthCard'
import Footer from '../components/Footer'
import Navbar from '../components/Navbar'
import { useAuth } from '../context/AuthContext'

const FEATURES = [
  {
    icon: Sparkles,
    title: 'AI-Powered Strategy',
    description: 'A conversational agent that asks the right questions and matches you to the loan that actually fits.',
  },
  {
    icon: TrendingUp,
    title: 'Real-Time Bank Comparison',
    description: 'Live policy data across partner banks — profit rates, tenure, and eligibility — compared side by side.',
  },
  {
    icon: ShieldCheck,
    title: 'Shariah-Compliant Options',
    description: 'Islamic financing products are flagged and filtered separately, so you only see what matches your preference.',
  },
]

const SERVICES = [
  { icon: Wallet, title: 'Personal Loans', description: 'Flexible financing for whatever life throws at you.' },
  { icon: HomeIcon, title: 'Home Financing', description: 'Conventional and Islamic home loan strategies, compared.' },
  { icon: Banknote, title: 'Auto Loans', description: 'Find the lowest total cost of ownership across lenders.' },
]

// Mirrors the bank records seeded in the backend (banks.models.Bank) — the
// same partner banks the chat agent actually compares policies across.
const PARTNER_BANKS = [
  'HBL', 'Meezan Bank', 'Bank Alfalah', 'MCB', 'ABL', 'Faysal Bank',
  'Askari Bank', 'BankIslami', 'Standard Chartered', 'JS Bank',
  'Dubai Islamic Bank', 'UBL', 'BOP',
]

function Landing() {
  const { isAuthenticated } = useAuth()
  const navigate = useNavigate()

  // Someone who is already signed in landing on "/" (a bookmark, the logo
  // link, a reload) belongs in the workspace, not back at the login form.
  useEffect(() => {
    if (isAuthenticated) navigate('/app', { replace: true })
  }, [isAuthenticated, navigate])

  if (isAuthenticated) return null

  return (
    <div className="flex min-h-screen flex-col bg-slate-950">
      <Navbar />

      <main className="relative flex-1 overflow-hidden">
        <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute -top-24 left-1/4 h-80 w-80 rounded-full bg-emerald/20 blur-3xl" />
          <div className="absolute bottom-0 right-1/5 h-96 w-96 rounded-full bg-navy blur-3xl" />
        </div>

        <section className="relative z-10 mx-auto flex max-w-6xl flex-col gap-12 px-6 py-16 lg:flex-row lg:items-center lg:py-24">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="flex-1"
          >
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald/30 bg-emerald/10 px-3 py-1 text-xs font-medium text-emerald">
              <Landmark className="h-3.5 w-3.5" />
              Smarter loan strategy, in minutes
            </span>
            <h1 className="mt-4 text-4xl font-bold leading-tight text-white sm:text-5xl">
              Find your best loan offer, before you apply anywhere.
            </h1>
            <p className="mt-4 max-w-xl text-base text-slate-400">
              Loan Strategy Agent talks you through your finances, then compares live policy
              data across Pakistan&apos;s leading banks — conventional and Islamic — to
              recommend the offer that actually fits.
            </p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.1 }}
            className="flex flex-1 justify-center lg:justify-end"
          >
            <AuthCard />
          </motion.div>
        </section>

        <section className="relative z-10 mx-auto max-w-6xl px-6 pb-16">
          <h2 className="text-center text-sm font-semibold uppercase tracking-wide text-slate-500">
            Why Loan Strategy Agent
          </h2>
          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            {FEATURES.map(({ icon: Icon, title, description }) => (
              <div
                key={title}
                className="rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur-xl transition-colors hover:border-emerald/30"
              >
                <span className="flex h-10 w-10 items-center justify-center rounded-full border border-emerald/30 bg-emerald/10 text-emerald">
                  <Icon className="h-5 w-5" />
                </span>
                <h3 className="mt-3 text-sm font-semibold text-white">{title}</h3>
                <p className="mt-1.5 text-sm text-slate-400">{description}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="relative z-10 mx-auto max-w-6xl px-6 pb-16">
          <h2 className="text-center text-sm font-semibold uppercase tracking-wide text-slate-500">
            Services
          </h2>
          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            {SERVICES.map(({ icon: Icon, title, description }) => (
              <div
                key={title}
                className="flex items-start gap-3 rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur-xl"
              >
                <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-gold/15 text-gold">
                  <Icon className="h-4.5 w-4.5" />
                </span>
                <div>
                  <h3 className="text-sm font-semibold text-white">{title}</h3>
                  <p className="mt-1 text-sm text-slate-400">{description}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="relative z-10 mx-auto max-w-6xl px-6 pb-20">
          <h2 className="text-center text-sm font-semibold uppercase tracking-wide text-slate-500">
            Banks
          </h2>
          <div className="mt-6 flex flex-wrap justify-center gap-2.5">
            {PARTNER_BANKS.map((bank) => (
              <span
                key={bank}
                className="rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-xs font-medium text-slate-300"
              >
                {bank}
              </span>
            ))}
          </div>
        </section>
      </main>

      <Footer />
    </div>
  )
}

export default Landing
