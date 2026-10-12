import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { Landmark, LogOut } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import AboutUsModal from './modals/AboutUsModal'
import BanksModal from './modals/BanksModal'
import ReportsModal from './modals/ReportsModal'
import ServicesModal from './modals/ServicesModal'

const NAV_LINKS = [
  { key: 'services', label: 'Services' },
  { key: 'banks', label: 'Banks' },
  { key: 'reports', label: 'Reports' },
  { key: 'about', label: 'About Us' },
]

function Navbar() {
  const { isAuthenticated, logout } = useAuth()
  const navigate = useNavigate()
  // Which informational modal is open, if any — purely local UI state. It
  // never touches chat/session state, so opening one over the workspace
  // can't break or reset an in-progress conversation.
  const [activeModal, setActiveModal] = useState(null)

  function handleLogout() {
    logout()
    navigate('/', { replace: true })
  }

  return (
    <header className="sticky top-0 z-20 border-b border-white/10 bg-navy/95 text-white backdrop-blur-sm">
      <nav className="mx-auto flex max-w-6xl items-center px-6 py-4">
        <NavLink to="/" className="flex items-center gap-2 font-semibold text-lg">
          <Landmark className="h-6 w-6 text-emerald" />
          Loan Strategy Agent
        </NavLink>

        <div className="hidden flex-1 items-center justify-center gap-1 sm:flex">
          {NAV_LINKS.map((link) => (
            <button
              key={link.key}
              type="button"
              onClick={() => setActiveModal(link.key)}
              className="rounded-lg px-3 py-1.5 text-sm text-slate-300 transition-colors hover:bg-white/10 hover:text-white"
            >
              {link.label}
            </button>
          ))}
        </div>

        {isAuthenticated ? (
          <button
            type="button"
            onClick={handleLogout}
            className="ml-auto flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-slate-300 transition-colors hover:bg-white/10 hover:text-white"
          >
            <LogOut className="h-4 w-4" />
            Log out
          </button>
        ) : null}
      </nav>

      <ServicesModal isOpen={activeModal === 'services'} onClose={() => setActiveModal(null)} />
      <BanksModal isOpen={activeModal === 'banks'} onClose={() => setActiveModal(null)} />
      <ReportsModal isOpen={activeModal === 'reports'} onClose={() => setActiveModal(null)} />
      <AboutUsModal isOpen={activeModal === 'about'} onClose={() => setActiveModal(null)} />
    </header>
  )
}

export default Navbar
