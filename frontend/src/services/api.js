import axios from 'axios'
import { AUTH_SESSION_EXPIRED_EVENT, clearStoredSession, getStoredSession, storeSession } from './authStorage'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/'
const JSON_HEADERS = { 'Content-Type': 'application/json' }

// Login, signup and token refresh: a 401 from these means bad credentials or
// a dead refresh token, never an expired access token worth retrying.
const AUTH_PATH_PREFIX = '/auth/'
const TOKEN_REFRESH_PATH = '/auth/token/refresh/'

const apiClient = axios.create({ baseURL: BASE_URL, headers: JSON_HEADERS })

// Carries no interceptors, so refreshing can't recurse into the 401 handler.
const refreshClient = axios.create({ baseURL: BASE_URL, headers: JSON_HEADERS })

// The backend identifies the caller only from this JWT (see
// REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES in the Django settings).
apiClient.interceptors.request.use((config) => {
  const session = getStoredSession()
  if (session?.access) {
    config.headers.Authorization = `Bearer ${session.access}`
  }
  return config
})

/**
 * Exchanges the stored refresh token for a new access token and persists it.
 * @returns {Promise<void>}
 */
async function requestNewAccessToken() {
  const session = getStoredSession()
  if (!session?.refresh) throw new Error('No refresh token available.')

  const { data } = await refreshClient.post(TOKEN_REFRESH_PATH, { refresh: session.refresh })

  // The user may have signed out (or in as someone else) while this was in
  // flight — writing the session back would then resurrect the old account.
  if (getStoredSession()?.refresh !== session.refresh) throw new Error('Session changed during refresh.')
  storeSession({ ...session, access: data.access, refresh: data.refresh ?? session.refresh })
}

// Several requests can hit a 401 at once when the access token expires; they
// all wait on this single refresh instead of each spending the refresh token.
let refreshInFlight = null

function refreshAccessToken() {
  if (!refreshInFlight) {
    refreshInFlight = requestNewAccessToken().finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

function expireSession() {
  clearStoredSession()
  window.dispatchEvent(new Event(AUTH_SESSION_EXPIRED_EVENT))
}

// On a 401 from an expired access token, refresh once and replay the request.
apiClient.interceptors.response.use(undefined, async (error) => {
  const request = error.config
  const isRetryable =
    error.response?.status === 401 &&
    request &&
    !request.hasRetriedAfterRefresh &&
    !request.url?.startsWith(AUTH_PATH_PREFIX) &&
    getStoredSession() !== null

  if (!isRetryable) throw error

  request.hasRetriedAfterRefresh = true
  try {
    await refreshAccessToken()
  } catch (refreshError) {
    // Only a refusal from the server ends the session; a network failure
    // leaves it in place so the next request can try again.
    if (refreshError?.response) expireSession()
    throw error
  }
  return apiClient(request)
})

export default apiClient
