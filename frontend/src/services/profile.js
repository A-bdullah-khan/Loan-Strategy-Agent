import apiClient from './api'

/**
 * Fetches the authenticated user's profile.
 */
export function getProfile() {
  return apiClient.get('/profile/')
}
