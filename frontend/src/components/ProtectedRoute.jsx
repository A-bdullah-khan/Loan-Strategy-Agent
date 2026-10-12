import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

/**
 * Gates its children behind an authenticated session — an unauthenticated
 * visit to a protected route bounces straight back to the public landing
 * page instead of rendering anything.
 * @param {{ children: React.ReactNode }} props
 */
function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth()

  if (!isAuthenticated) {
    return <Navigate to="/" replace />
  }

  return children
}

export default ProtectedRoute
