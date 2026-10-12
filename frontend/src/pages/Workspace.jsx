import Navbar from '../components/Navbar'
import Sidebar from '../components/Sidebar'
import { useChatSession } from '../hooks/useChatSession'
import Home from './Home'

/**
 * The protected `/app` shell: the navbar (with its Services / Banks
 * / About Us modals), a collapsible left Sidebar for session management, and
 * the main passive chat workspace. Owns the chat session — Sidebar and the
 * main pane are both driven off it, so "+ New Chat" resets `messages` to
 * `[]` in one place and both sides of the layout pick it up from the same
 * source of truth. The navbar's modals are pure overlay UI with their own
 * local open/close state, so opening one never touches this chat session.
 */
function Workspace() {
  const chatSession = useChatSession()

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <Navbar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          sessions={chatSession.sessions}
          activeSessionId={chatSession.sessionId}
          onNewChat={chatSession.newChat}
          onSelectSession={chatSession.loadSession}
          onRenameSession={chatSession.renameSessionTitle}
          onTogglePinSession={chatSession.toggleSessionPinned}
          onDeleteSession={chatSession.deleteSession}
        />
        <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <Home chatSession={chatSession} />
        </main>
      </div>
    </div>
  )
}

export default Workspace
