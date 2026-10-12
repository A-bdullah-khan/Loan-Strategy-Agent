const AUTH_STORAGE_KEY = 'loan_agent_auth_session'

/**
 * Dispatched on `window` when the stored session can no longer be used (the
 * refresh token was rejected — see `services/api`), so `AuthContext` can drop
 * the user out of the protected workspace.
 */
export const AUTH_SESSION_EXPIRED_EVENT = 'loan-agent:auth-session-expired'

/**
 * The signed-in user plus their JWT pair, as persisted in this browser.
 * @typedef {object} AuthSession
 * @property {string} access - short-lived JWT sent as `Authorization: Bearer`.
 * @property {string} refresh - long-lived JWT exchanged for a new `access`.
 * @property {number} id - the Django user's primary key.
 * @property {string} email
 * @property {string} fullName
 */

/**
 * @returns {AuthSession | null} null when nobody is signed in. A session
 *   saved before real JWT auth (no `access` token or user `id`) counts as
 *   signed out, so that browser is sent back through the login form.
 */
export function getStoredSession() {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY)
    const session = raw ? JSON.parse(raw) : null
    return session?.access && session?.id != null ? session : null
  } catch {
    return null
  }
}

/** @param {AuthSession} session */
export function storeSession(session) {
  try {
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session))
  } catch {
    // Ignore storage errors (private browsing, quota, etc.) — the session
    // still works for the current tab, it just won't survive a reload.
  }
}

export function clearStoredSession() {
  try {
    localStorage.removeItem(AUTH_STORAGE_KEY)
  } catch {
    // Ignore — worst case a stale session lingers until overwritten.
  }
}
