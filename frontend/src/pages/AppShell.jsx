import { Outlet } from 'react-router-dom'
import Footer from '../components/Footer'
import Navbar from '../components/Navbar'

/**
 * Plain navbar/footer chrome for protected pages that aren't the chat
 * workspace (currently just `/profile`) — the workspace's own layout lives
 * in `Workspace.jsx`, which owns the sidebar directly instead of going
 * through this shell.
 */
function AppShell() {
  return (
    <div className="flex min-h-screen flex-col">
      <Navbar />
      <main className="flex flex-1 flex-col">
        <Outlet />
      </main>
      <Footer />
    </div>
  )
}

export default AppShell
