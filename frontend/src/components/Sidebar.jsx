import { memo, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  LogOut,
  MessageSquare,
  MoreVertical,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Pin,
  PinOff,
  Plus,
  Search,
  Trash2,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'

// Tooltip only kicks in past this length — short previews never truncate
// inside the two-line clamp, so there's nothing worth repeating on hover.
const TOOLTIP_MIN_LENGTH = 36

function initialsFor(name) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join('')
}

/**
 * One chat-history row: title (or an inline rename input), a hover-revealed
 * 3-dot menu (Pin/Unpin, Rename, Delete), and a hover tooltip for titles the
 * two-line clamp would otherwise cut off.
 * @param {{
 *   session: { sessionId: string, preview: string, updatedAt: string, title: string | null, pinned: boolean },
 *   isActive: boolean,
 *   isMenuOpen: boolean,
 *   isRenaming: boolean,
 *   renameValue: string,
 *   onSelect: () => void,
 *   onToggleMenu: () => void,
 *   onCloseMenu: () => void,
 *   onStartRename: () => void,
 *   onRenameChange: (value: string) => void,
 *   onRenameCommit: () => void,
 *   onRenameCancel: () => void,
 *   onTogglePin: () => void,
 *   onDelete: () => void,
 *   menuRef: React.RefObject,
 * }} props
 */
function SessionRow({
  session,
  isActive,
  isMenuOpen,
  isRenaming,
  renameValue,
  onSelect,
  onToggleMenu,
  onCloseMenu,
  onStartRename,
  onRenameChange,
  onRenameCommit,
  onRenameCancel,
  onTogglePin,
  onDelete,
  menuRef,
}) {
  const renameInputRef = useRef(null)
  const displayTitle = session.title || session.preview || 'New chat'

  useEffect(() => {
    if (isRenaming) {
      renameInputRef.current?.focus()
      renameInputRef.current?.select()
    }
  }, [isRenaming])

  function handleRenameKeyDown(event) {
    if (event.key === 'Enter') {
      event.preventDefault()
      onRenameCommit()
    } else if (event.key === 'Escape') {
      event.preventDefault()
      onRenameCancel()
    }
  }

  return (
    <div className="group relative">
      {isRenaming ? (
        <div className="flex items-center gap-2 rounded-lg bg-white/5 px-2.5 py-2">
          <MessageSquare className="h-4 w-4 flex-shrink-0 text-slate-500" />
          <input
            ref={renameInputRef}
            type="text"
            value={renameValue}
            onChange={(event) => onRenameChange(event.target.value)}
            onKeyDown={handleRenameKeyDown}
            onBlur={onRenameCommit}
            maxLength={120}
            aria-label="Rename chat"
            className="w-full min-w-0 bg-transparent text-sm text-white focus:outline-none"
          />
        </div>
      ) : (
        <>
          <button
            type="button"
            onClick={onSelect}
            aria-current={isActive ? 'true' : undefined}
            className={`flex w-full items-start gap-2 rounded-lg py-2 pl-2.5 pr-8 text-left text-sm transition-colors ${
              isActive ? 'bg-emerald/15 text-white' : 'text-slate-300 hover:bg-white/5 hover:text-white'
            }`}
          >
            <MessageSquare
              className={`mt-0.5 h-4 w-4 flex-shrink-0 ${isActive ? 'text-emerald' : 'text-slate-500'}`}
            />
            <span className="line-clamp-2 break-words">{displayTitle}</span>
          </button>

          {displayTitle.length > TOOLTIP_MIN_LENGTH ? (
            <div
              role="tooltip"
              className="pointer-events-none absolute left-2 top-full z-30 mt-1 max-w-xs rounded-md border border-white/10 bg-slate-900 px-2.5 py-1.5 text-xs text-slate-200 opacity-0 shadow-lg shadow-black/40 transition-opacity delay-300 group-hover:opacity-100"
            >
              {displayTitle}
            </div>
          ) : null}

          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation()
              onToggleMenu()
            }}
            aria-label="Chat options"
            aria-haspopup="true"
            aria-expanded={isMenuOpen}
            className={`absolute right-1 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-md text-slate-400 transition-opacity hover:bg-white/10 hover:text-white ${
              isMenuOpen ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 focus-visible:opacity-100'
            }`}
          >
            <MoreVertical className="h-4 w-4" />
          </button>
        </>
      )}

      {isMenuOpen ? (
        <div
          ref={menuRef}
          role="menu"
          className="absolute right-1 top-9 z-30 w-40 overflow-hidden rounded-lg border border-white/10 bg-slate-900 py-1 shadow-xl shadow-black/40"
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              onTogglePin()
              onCloseMenu()
            }}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-200 hover:bg-white/10 hover:text-white"
          >
            {session.pinned ? <PinOff className="h-3.5 w-3.5" /> : <Pin className="h-3.5 w-3.5" />}
            {session.pinned ? 'Unpin' : 'Pin'}
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              onCloseMenu()
              onStartRename()
            }}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-200 hover:bg-white/10 hover:text-white"
          >
            <Pencil className="h-3.5 w-3.5" />
            Rename
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              onCloseMenu()
              onDelete()
            }}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-red-400 hover:bg-red-500/10 hover:text-red-300"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete
          </button>
        </div>
      ) : null}
    </div>
  )
}

/**
 * Collapsible left sidebar for chat session management: start a new chat,
 * search past sessions, switch between them, pin/rename/delete a session,
 * and sign out. The session list itself comes from `useChatSession`'s
 * browser-local index (mongo has no per-browser notion of "my sessions" for
 * anonymous users); each session's full transcript is fetched from
 * `/api/chat/history/` only when it's opened, and deleted there too.
 *
 * Memoized: `sessions`/`activeSessionId`/the handler props only change when
 * the session list or active session actually changes, so this doesn't
 * re-render on every streamed message or typing-indicator tick from the main
 * chat pane.
 * @param {{
 *   sessions: Array<{ sessionId: string, preview: string, updatedAt: string, title: string | null, pinned: boolean }>,
 *   activeSessionId: string | null,
 *   onNewChat: () => void,
 *   onSelectSession: (sessionId: string) => void,
 *   onRenameSession: (sessionId: string, title: string) => void,
 *   onTogglePinSession: (sessionId: string) => void,
 *   onDeleteSession: (sessionId: string) => Promise<void>,
 * }} props
 */
function Sidebar({
  sessions,
  activeSessionId,
  onNewChat,
  onSelectSession,
  onRenameSession,
  onTogglePinSession,
  onDeleteSession,
}) {
  const [collapsed, setCollapsed] = useState(false)
  const [query, setQuery] = useState('')
  const [openMenuId, setOpenMenuId] = useState(null)
  const [renamingId, setRenamingId] = useState(null)
  const [renameValue, setRenameValue] = useState('')
  const menuRef = useRef(null)
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const filteredSessions = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    if (!normalized) return sessions
    return sessions.filter((session) => (session.title || session.preview).toLowerCase().includes(normalized))
  }, [sessions, query])

  const pinnedSessions = useMemo(() => filteredSessions.filter((session) => session.pinned), [filteredSessions])
  const otherSessions = useMemo(() => filteredSessions.filter((session) => !session.pinned), [filteredSessions])

  // Close the open menu on an outside click or Escape.
  useEffect(() => {
    if (!openMenuId) return undefined

    function handlePointerDown(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setOpenMenuId(null)
      }
    }

    function handleKeyDown(event) {
      if (event.key === 'Escape') setOpenMenuId(null)
    }

    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [openMenuId])

  function handleLogout() {
    logout()
    navigate('/', { replace: true })
  }

  function startRename(session) {
    setRenameValue(session.title || session.preview || '')
    setRenamingId(session.sessionId)
  }

  function commitRename(session) {
    if (renamingId !== session.sessionId) return
    onRenameSession(session.sessionId, renameValue)
    setRenamingId(null)
  }

  async function handleDelete(session) {
    const label = session.title || session.preview || 'this chat'
    if (!window.confirm(`Delete "${label}"? This can't be undone.`)) return
    try {
      await onDeleteSession(session.sessionId)
    } catch {
      window.alert("Couldn't delete this chat. Please try again.")
    }
  }

  const displayName = user?.fullName || user?.email || 'Guest'

  if (collapsed) {
    return (
      <aside className="flex w-14 flex-shrink-0 flex-col items-center gap-3 border-r border-white/10 bg-navy py-4">
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          aria-label="Expand sidebar"
          className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-300 transition-colors hover:bg-white/10 hover:text-white"
        >
          <PanelLeftOpen className="h-5 w-5" />
        </button>
        <button
          type="button"
          onClick={onNewChat}
          aria-label="New chat"
          className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald text-white shadow-md shadow-emerald/20 transition-transform hover:scale-105"
        >
          <Plus className="h-5 w-5" />
        </button>

        <div className="mt-auto flex flex-col items-center gap-2">
          <span
            title={displayName}
            className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald/15 text-xs font-semibold text-emerald"
          >
            {initialsFor(displayName)}
          </span>
          <button
            type="button"
            onClick={handleLogout}
            aria-label="Logout"
            className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-300 transition-colors hover:bg-white/10 hover:text-white"
          >
            <LogOut className="h-4.5 w-4.5" />
          </button>
        </div>
      </aside>
    )
  }

  function renderRow(session) {
    return (
      <SessionRow
        key={session.sessionId}
        session={session}
        isActive={session.sessionId === activeSessionId}
        isMenuOpen={openMenuId === session.sessionId}
        isRenaming={renamingId === session.sessionId}
        renameValue={renameValue}
        onSelect={() => onSelectSession(session.sessionId)}
        onToggleMenu={() => setOpenMenuId((current) => (current === session.sessionId ? null : session.sessionId))}
        onCloseMenu={() => setOpenMenuId(null)}
        onStartRename={() => startRename(session)}
        onRenameChange={setRenameValue}
        onRenameCommit={() => commitRename(session)}
        onRenameCancel={() => setRenamingId(null)}
        onTogglePin={() => onTogglePinSession(session.sessionId)}
        onDelete={() => handleDelete(session)}
        menuRef={menuRef}
      />
    )
  }

  return (
    <aside className="flex w-72 flex-shrink-0 flex-col border-r border-white/10 bg-navy">
      <div className="flex items-center gap-2 px-3 pt-4">
        <button
          type="button"
          onClick={onNewChat}
          className="flex flex-1 items-center gap-2 rounded-lg bg-emerald px-3 py-2.5 text-sm font-medium text-white shadow-md shadow-emerald/20 transition-colors hover:bg-emerald/90"
        >
          <Plus className="h-4 w-4" />
          New Chat
        </button>
        <button
          type="button"
          onClick={() => setCollapsed(true)}
          aria-label="Collapse sidebar"
          className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg text-slate-300 transition-colors hover:bg-white/10 hover:text-white"
        >
          <PanelLeftClose className="h-5 w-5" />
        </button>
      </div>

      <div className="relative px-3 pt-3">
        <Search className="pointer-events-none absolute left-6 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
        <input
          type="text"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search chats..."
          aria-label="Search past chats"
          className="w-full rounded-lg border border-white/10 bg-white/5 py-2 pl-9 pr-3 text-sm text-slate-100 placeholder:text-slate-500 focus:border-emerald/40 focus:outline-none"
        />
      </div>

      <nav className="mt-3 flex-1 space-y-4 overflow-y-auto px-3 pb-4" aria-label="Chat history">
        {filteredSessions.length === 0 ? (
          <p className="px-2 py-6 text-center text-sm text-slate-500">
            {sessions.length === 0 ? 'No past chats yet' : 'No chats match your search'}
          </p>
        ) : (
          <>
            {pinnedSessions.length > 0 ? (
              <div className="space-y-1">
                <p className="px-2.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Pinned</p>
                {pinnedSessions.map(renderRow)}
              </div>
            ) : null}

            {otherSessions.length > 0 ? (
              <div className="space-y-1">
                {pinnedSessions.length > 0 ? (
                  <p className="px-2.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Chats</p>
                ) : null}
                {otherSessions.map(renderRow)}
              </div>
            ) : null}
          </>
        )}
      </nav>

      <div className="flex items-center gap-2.5 border-t border-white/10 px-3 py-3">
        <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-emerald/15 text-sm font-semibold text-emerald">
          {initialsFor(displayName)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-white">{user?.fullName || 'Guest'}</p>
          <p className="truncate text-xs text-slate-400">{user?.email || 'Not signed in'}</p>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          aria-label="Logout"
          title="Logout"
          className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-white/10 hover:text-white"
        >
          <LogOut className="h-4 w-4" />
        </button>
      </div>
    </aside>
  )
}

export default memo(Sidebar)
