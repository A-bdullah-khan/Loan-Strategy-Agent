import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import ProtectedRoute from './components/ProtectedRoute'
import { AuthProvider } from './context/AuthContext'
import AppShell from './pages/AppShell'
import Landing from './pages/Landing'
import Profile from './pages/Profile'
import ReportPage from './pages/ReportPage'
import Workspace from './pages/Workspace'

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Landing />} />

          <Route
            path="/app"
            element={
              <ProtectedRoute>
                <Workspace />
              </ProtectedRoute>
            }
          />

          {/* Not gated by ProtectedRoute — same accessibility as the old
              ReportPreviewModal it replaces, since a guest (no Django login)
              can still complete a loan request and needs to view/export it. */}
          <Route path="/reports/:loanRequestId" element={<ReportPage />} />

          <Route
            element={
              <ProtectedRoute>
                <AppShell />
              </ProtectedRoute>
            }
          >
            <Route path="/profile" element={<Profile />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
