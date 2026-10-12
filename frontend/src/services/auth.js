import apiClient from './api'
import { storeSession } from './authStorage'

const NETWORK_ERROR_MESSAGE = "Couldn't reach the server. Please try again shortly."
const GENERIC_ERROR_MESSAGE = 'Something went wrong. Please try again.'

/**
 * Turns a failed auth request into an Error whose message is safe to show in
 * the form. The backend answers with either `{"detail": "..."}` (wrong
 * credentials) or per-field error lists (`{"email": ["..."], ...}`).
 * @param {unknown} err
 * @returns {Error}
 */
function toAuthError(err) {
  if (!err?.response) return new Error(NETWORK_ERROR_MESSAGE)

  const data = err.response.data
  if (typeof data?.detail === 'string') return new Error(data.detail)
  if (data && typeof data === 'object') {
    const firstFieldError = Object.values(data)
      .flat()
      .find((message) => typeof message === 'string')
    if (firstFieldError) return new Error(firstFieldError)
  }
  return new Error(GENERIC_ERROR_MESSAGE)
}

/**
 * @param {{ access: string, refresh: string, user: { id: number, email: string, full_name: string } }} payload
 * @returns {import('./authStorage').AuthSession}
 */
function toSession({ access, refresh, user }) {
  return { access, refresh, id: user.id, email: user.email, fullName: user.full_name }
}

/**
 * Posts to one of the token-issuing endpoints (see `users.views`) and
 * persists the resulting session.
 * @param {string} path
 * @param {object} body
 * @returns {Promise<import('./authStorage').AuthSession>}
 */
async function requestSession(path, body) {
  try {
    const { data } = await apiClient.post(path, body)
    const session = toSession(data)
    storeSession(session)
    return session
  } catch (err) {
    throw toAuthError(err)
  }
}

/**
 * `POST /api/auth/login/` — exchanges an email/password pair for a JWT pair.
 * @param {{ email: string, password: string }} credentials
 * @returns {Promise<import('./authStorage').AuthSession>}
 */
export function loginUser({ email, password }) {
  return requestSession('/auth/login/', { email, password })
}

/**
 * `POST /api/auth/register/` — creates an account and signs it in.
 * @param {{ fullName: string, email: string, password: string }} details
 * @returns {Promise<import('./authStorage').AuthSession>}
 */
export function signupUser({ fullName, email, password }) {
  return requestSession('/auth/register/', { full_name: fullName.trim(), email, password })
}
