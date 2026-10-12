import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { loginUser, signupUser } from '../services/auth'
import { AUTH_SESSION_EXPIRED_EVENT, clearStoredSession, getStoredSession } from '../services/authStorage'

const AuthContext = createContext(null)

/**
 * Owns the current auth session (the signed-in user and their JWT pair, see
 * `services/authStorage`) and exposes login/signup/logout to the rest of the
 * app. Mounted once at the app root so both the landing page's auth form and
 * the protected workspace route see the same session.
 * @param {{ children: React.ReactNode }} props
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => getStoredSession())

  // The API client clears the stored session when its refresh token is
  // rejected; mirror that here so the protected route redirects to login.
  useEffect(() => {
    function handleSessionExpired() {
      setUser(null)
    }

    window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, handleSessionExpired)
    return () => window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, handleSessionExpired)
  }, [])

  const value = useMemo(
    () => ({
      user,
      isAuthenticated: Boolean(user),
      async login(credentials) {
        const session = await loginUser(credentials)
        setUser(session)
        return session
      },
      async signup(details) {
        const session = await signupUser(details)
        setUser(session)
        return session
      },
      logout() {
        clearStoredSession()
        setUser(null)
      },
    }),
    [user],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within an AuthProvider')
  return context
}
