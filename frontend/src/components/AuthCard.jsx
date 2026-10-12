import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useAuth } from '../context/AuthContext'

const FIELD_CLASSES =
  'w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 focus:border-emerald/40 focus:outline-none'
const LABEL_CLASSES = 'mb-1 block text-xs font-medium text-slate-400'
// Mirrors Django's MinimumLengthValidator default (see AUTH_PASSWORD_VALIDATORS
// in the backend settings), which every new account's password must pass.
const PASSWORD_MIN_LENGTH = 8

/**
 * Sign In / Sign Up tabbed auth form for the landing page. On success it
 * stores the session (via AuthContext) and redirects straight into the
 * protected workspace at `/app`.
 */
function AuthCard() {
  const [mode, setMode] = useState('signin')
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const { login, signup } = useAuth()
  const navigate = useNavigate()

  function switchMode(nextMode) {
    setMode(nextMode)
    setError('')
  }

  async function handleSubmit(event) {
    event.preventDefault()

    if (mode === 'signup' && password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setError('')
    setIsSubmitting(true)
    try {
      if (mode === 'signin') {
        await login({ email, password })
      } else {
        await signup({ fullName, email, password })
      }
      navigate('/app', { replace: true })
    } catch (err) {
      setError(err.message || 'Something went wrong. Please try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/5 p-6 shadow-xl shadow-black/20 backdrop-blur-xl">
      <div className="mb-6 flex rounded-lg border border-white/10 bg-white/5 p-1">
        <button
          type="button"
          onClick={() => switchMode('signin')}
          aria-pressed={mode === 'signin'}
          className={`flex-1 rounded-md py-2 text-sm font-medium transition-colors ${
            mode === 'signin' ? 'bg-emerald text-white' : 'text-slate-300 hover:text-white'
          }`}
        >
          Sign In
        </button>
        <button
          type="button"
          onClick={() => switchMode('signup')}
          aria-pressed={mode === 'signup'}
          className={`flex-1 rounded-md py-2 text-sm font-medium transition-colors ${
            mode === 'signup' ? 'bg-emerald text-white' : 'text-slate-300 hover:text-white'
          }`}
        >
          Sign Up
        </button>
      </div>

      <motion.form
        key={mode}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
        onSubmit={handleSubmit}
        className="space-y-4"
      >
        {mode === 'signup' ? (
          <div>
            <label htmlFor="fullName" className={LABEL_CLASSES}>
              Full Name
            </label>
            <input
              id="fullName"
              type="text"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              required
              className={FIELD_CLASSES}
              placeholder="John Doe"
            />
          </div>
        ) : null}

        <div>
          <label htmlFor="email" className={LABEL_CLASSES}>
            Email
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            className={FIELD_CLASSES}
            placeholder="you@example.com"
          />
        </div>

        <div>
          <label htmlFor="password" className={LABEL_CLASSES}>
            Password
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            minLength={mode === 'signup' ? PASSWORD_MIN_LENGTH : undefined}
            className={FIELD_CLASSES}
            placeholder="••••••••"
          />
        </div>

        {mode === 'signup' ? (
          <div>
            <label htmlFor="confirmPassword" className={LABEL_CLASSES}>
              Confirm Password
            </label>
            <input
              id="confirmPassword"
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              required
              minLength={PASSWORD_MIN_LENGTH}
              className={FIELD_CLASSES}
              placeholder="••••••••"
            />
          </div>
        ) : null}

        {error ? <p className="text-sm text-red-400">{error}</p> : null}

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full rounded-lg bg-emerald py-2.5 text-sm font-semibold text-white shadow-md shadow-emerald/30 transition-opacity hover:bg-emerald/90 disabled:opacity-60"
        >
          {isSubmitting ? 'Please wait…' : mode === 'signin' ? 'Sign In' : 'Create Account'}
        </button>
      </motion.form>
    </div>
  )
}

export default AuthCard
