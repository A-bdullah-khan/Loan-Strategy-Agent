import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { getStoredSession } from '../services/authStorage'
import { deleteChatHistory, getChatHistory, sendChatMessage } from '../services/chat'

// Both keys are suffixed with the signed-in user's key (see `toUserKey`), so
// two accounts sharing one browser never read each other's active session or
// sidebar list.
const SESSION_STORAGE_KEY_PREFIX = 'loan_agent_chat_session_id'
const SESSIONS_INDEX_KEY_PREFIX = 'loan_agent_chat_sessions'
const PREVIEW_MAX_LENGTH = 80

/**
 * The stable per-account identifier the storage keys are scoped by: the
 * Django user's primary key from the auth session (see `services/authStorage`)
 * — the same id the backend scopes each chat transcript to.
 * @param {{ id?: number | string } | null | undefined} user
 * @returns {string | null} null when nobody is signed in.
 */
function toUserKey(user) {
  const id = user?.id
  return id === null || id === undefined || id === '' ? null : String(id)
}

function sessionIdStorageKey(userKey) {
  return `${SESSION_STORAGE_KEY_PREFIX}_${userKey}`
}

function sessionsIndexStorageKey(userKey) {
  return `${SESSIONS_INDEX_KEY_PREFIX}_${userKey}`
}

// The pre-scoping, browser-wide keys can't be attributed to any one account,
// so they're dropped rather than migrated — otherwise whoever signs in next
// would inherit a previous user's sidebar entries.
function purgeUnscopedStorage() {
  try {
    localStorage.removeItem(SESSION_STORAGE_KEY_PREFIX)
    localStorage.removeItem(SESSIONS_INDEX_KEY_PREFIX)
  } catch {
    // Ignore — nothing reads these keys anymore.
  }
}

purgeUnscopedStorage()

function readStoredSessionId(userKey) {
  if (!userKey) return null
  try {
    return localStorage.getItem(sessionIdStorageKey(userKey))
  } catch {
    return null
  }
}

function storeSessionId(userKey, sessionId) {
  if (!userKey) return
  try {
    localStorage.setItem(sessionIdStorageKey(userKey), sessionId)
  } catch {
    // Ignore storage errors (private browsing, quota, etc.) — the chat still
    // works for the current tab, it just won't survive a reload.
  }
}

function clearStoredSessionId(userKey) {
  if (!userKey) return
  try {
    localStorage.removeItem(sessionIdStorageKey(userKey))
  } catch {
    // Ignore — worst case a stale id lingers and fails to restore next load.
  }
}

/**
 * The sidebar's session list for one user. There is no backend endpoint that
 * enumerates a user's past sessions, so this browser-local, per-user index —
 * session id, first-query preview, last-active time — is the source of truth
 * for what shows up in the sidebar. Full conversation content is always
 * fetched live from `/api/chat/history/`, never cached here.
 */
function readSessionsIndex(userKey) {
  if (!userKey) return []
  try {
    const raw = localStorage.getItem(sessionsIndexStorageKey(userKey))
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function writeSessionsIndex(userKey, sessions) {
  if (!userKey) return sessions
  try {
    localStorage.setItem(sessionsIndexStorageKey(userKey), JSON.stringify(sessions))
  } catch {
    // Ignore — the sidebar list just won't persist across reloads.
  }
  return sessions
}

/**
 * Every chat session id this browser knows about for the signed-in user. The
 * Navbar's Reports drawer uses this to aggregate
 * `GET /api/reports/?chat_id=...` across every session — there's no backend
 * endpoint that lists a user's reports globally, so the per-session id list
 * doubles as that scope.
 * @returns {string[]}
 */
export function getKnownSessionIds() {
  return readSessionsIndex(toUserKey(getStoredSession())).map((s) => s.sessionId)
}

function buildPreview(text) {
  const collapsed = text.trim().replace(/\s+/g, ' ')
  return collapsed.length > PREVIEW_MAX_LENGTH ? `${collapsed.slice(0, PREVIEW_MAX_LENGTH)}…` : collapsed
}

/**
 * Moves/creates `sessionId` to the front of the sessions index. The preview
 * is set once, from that session's first user message, and left untouched on
 * later turns so the sidebar keeps showing what the chat was originally
 * about rather than the most recent line. `title` (a user-chosen rename) and
 * `pinned` are carried over from the existing entry, if any — they're only
 * ever changed explicitly, via `renameSessionTitle`/`toggleSessionPinned`.
 */
function upsertSessionIndex(userKey, sessionId, preview) {
  const sessions = readSessionsIndex(userKey)
  const existing = sessions.find((s) => s.sessionId === sessionId)
  const updatedAt = new Date().toISOString()
  const rest = sessions.filter((s) => s.sessionId !== sessionId)
  const entry = {
    sessionId,
    preview: existing?.preview || preview,
    updatedAt,
    title: existing?.title ?? null,
    pinned: existing?.pinned ?? false,
  }
  return writeSessionsIndex(userKey, [entry, ...rest])
}

let messageIdCounter = 0
function nextMessageId() {
  messageIdCounter += 1
  return `msg-${messageIdCounter}`
}

/**
 * Normalizes a backend message payload into a plain string plus optional
 * extras. Only needed for history restored from MongoDB (`hydrateFromHistory`)
 * — a live turn now always returns a plain string reply (see `sendChatMessage`),
 * but a row saved back when this app used Gemini can still have `content`
 * stored as a single `{ type, text, extras }` block or a list of them (an
 * artifact of `AIMessage.content` carrying a "thought signature"), and none
 * of those are safe to render directly as a React child.
 * @param {unknown} raw
 * @returns {{ text: string, extras: object | null }}
 */
function normalizeMessageContent(raw) {
  const blocks = Array.isArray(raw) ? raw : [raw]
  let text = ''
  let extras = null
  for (const block of blocks) {
    if (typeof block === 'string') {
      text += block
    } else if (block && typeof block === 'object' && typeof block.text === 'string') {
      text += block.text
      if (extras === null && block.extras != null) extras = block.extras
    } else if (block != null && typeof block !== 'object') {
      text += String(block)
    }
  }
  return { text, extras }
}

/**
 * Owns the loan strategy chat conversation: message history, MongoDB-backed
 * session persistence/restore, slot-filling state carried between turns, and
 * the browser-local index of past sessions shown in the sidebar. Shared by
 * the landing hero, the full-screen chat workspace, and the sidebar so they
 * all render/drive the same live conversation instead of disconnected state.
 * @returns {{
 *   messages: Array<{ id: string, role: 'user' | 'assistant', content: string, toolCalls: Array }>,
 *   hasStarted: boolean,
 *   isTyping: boolean,
 *   sessionId: string | null,
 *   sessions: Array<{ sessionId: string, preview: string, updatedAt: string, title: string | null, pinned: boolean }>,
 *   sendMessage: (text: string) => Promise<void>,
 *   newChat: () => void,
 *   loadSession: (sessionId: string) => Promise<void>,
 *   renameSessionTitle: (sessionId: string, title: string) => void,
 *   toggleSessionPinned: (sessionId: string) => void,
 *   deleteSession: (sessionId: string) => Promise<void>,
 * }}
 */
export function useChatSession() {
  const { user } = useAuth()
  const userKey = toUserKey(user)

  const [messages, setMessages] = useState([])
  const [isTyping, setIsTyping] = useState(false)
  const [loanState, setLoanState] = useState({})
  const [sessionId, setSessionId] = useState(null)
  const [loanRequestId, setLoanRequestId] = useState(null)
  const [sessions, setSessions] = useState(() => readSessionsIndex(userKey))

  const hasStarted = messages.length > 0

  const hydrateFromHistory = useCallback((data) => {
    setSessionId(data.session_id)
    setMessages(
      (data.messages || []).map((message) => {
        const { text, extras } = normalizeMessageContent(message.content)
        return {
          id: nextMessageId(),
          role: message.role,
          content: text,
          extras,
          toolCalls: [],
        }
      }),
    )

    const lastAssistantTurn = [...(data.messages || [])].reverse().find((m) => m.role === 'assistant')
    if (lastAssistantTurn?.slots_captured) {
      const { loan_request_id: restoredLoanRequestId, ...restoredState } = lastAssistantTurn.slots_captured
      setLoanState(restoredState)
      setLoanRequestId(restoredLoanRequestId ?? null)
    } else {
      setLoanState({})
      setLoanRequestId(null)
    }
  }, [])

  // When the signed-in user changes (including sign out), drop whatever
  // conversation is in memory and swap the sidebar to that user's own index.
  // Done during render rather than in an effect so the previous user's chat
  // is never painted for the new one.
  const [loadedUserKey, setLoadedUserKey] = useState(userKey)
  if (loadedUserKey !== userKey) {
    setLoadedUserKey(userKey)
    setMessages([])
    setSessionId(null)
    setLoanState({})
    setLoanRequestId(null)
    setSessions(readSessionsIndex(userKey))
  }

  // Reload the signed-in user's last conversation from MongoDB if this
  // browser has one for them.
  useEffect(() => {
    let cancelled = false

    const storedSessionId = readStoredSessionId(userKey)
    if (!storedSessionId) return undefined

    getChatHistory(storedSessionId)
      .then(({ data }) => {
        // `cancelled` guards a response landing after the user has changed.
        if (cancelled || !data.messages || data.messages.length === 0) return
        hydrateFromHistory(data)
      })
      .catch(() => {
        // Stale/invalid session — ignore and stay on the empty passive state.
      })

    return () => {
      cancelled = true
    }
  }, [userKey, hydrateFromHistory])

  async function sendMessage(text) {
    const trimmed = text.trim()
    if (!trimmed || isTyping) return

    const isFirstMessage = messages.length === 0
    const userMessage = { id: nextMessageId(), role: 'user', content: trimmed, toolCalls: [] }
    const assistantId = nextMessageId()

    setMessages((prev) => [...prev, userMessage])
    setIsTyping(true)

    function showAssistantMessage(content, toolCalls = []) {
      setMessages((prev) => [...prev, { id: assistantId, role: 'assistant', content, toolCalls }])
    }

    try {
      const { data } = await sendChatMessage(trimmed, sessionId, loanState, loanRequestId)
      const replyText = data.reply || 'No response received. Please try again.'
      showAssistantMessage(replyText, data.tool_calls ?? [])

      if (data.state) setLoanState(data.state)
      // Always sync loan_request_id to the backend's value, including an
      // explicit null (e.g. after a greeting resets the slot-filling state)
      // — a truthy-only check would leave a stale id from a prior, unrelated
      // evaluation in place and misattach the next completed evaluation to it.
      setLoanRequestId(data.loan_request_id ?? null)
      if (data.session_id) {
        setSessionId(data.session_id)
        storeSessionId(userKey, data.session_id)
        setSessions(upsertSessionIndex(userKey, data.session_id, isFirstMessage ? buildPreview(trimmed) : ''))
      }
    } catch (err) {
      const detail = err?.response?.data?.detail
      showAssistantMessage(detail || "Sorry, I couldn't reach the loan strategy service. Please try again shortly.")
    } finally {
      setIsTyping(false)
    }
  }

  // Stable identity for as long as the same user is signed in, so components
  // that only care about "can I start a new chat" — like the memoized
  // Sidebar — don't re-render just because a message streamed in.
  const newChat = useCallback(() => {
    setMessages([])
    setSessionId(null)
    setLoanState({})
    setLoanRequestId(null)
    clearStoredSessionId(userKey)
  }, [userKey])

  /** Switches the active session to a previously saved one, fetched live from MongoDB. */
  const loadSession = useCallback(
    async (targetSessionId) => {
      if (targetSessionId === sessionId) return

      const { data } = await getChatHistory(targetSessionId)
      hydrateFromHistory(data)
      storeSessionId(userKey, targetSessionId)
    },
    [sessionId, userKey, hydrateFromHistory],
  )

  /** Renames a session's sidebar entry. Local-only — there's no per-session title on the backend. */
  const renameSessionTitle = useCallback(
    (targetSessionId, title) => {
      const trimmed = title.trim()
      setSessions((prev) => {
        const updated = prev.map((s) => (s.sessionId === targetSessionId ? { ...s, title: trimmed || null } : s))
        return writeSessionsIndex(userKey, updated)
      })
    },
    [userKey],
  )

  /** Toggles whether a session is pinned to the dedicated section at the top of the sidebar. */
  const toggleSessionPinned = useCallback(
    (targetSessionId) => {
      setSessions((prev) => {
        const updated = prev.map((s) => (s.sessionId === targetSessionId ? { ...s, pinned: !s.pinned } : s))
        return writeSessionsIndex(userKey, updated)
      })
    },
    [userKey],
  )

  /** Permanently deletes a session's MongoDB transcript and drops it from the sidebar index. */
  const deleteSession = useCallback(
    async (targetSessionId) => {
      await deleteChatHistory(targetSessionId)
      setSessions((prev) => writeSessionsIndex(userKey, prev.filter((s) => s.sessionId !== targetSessionId)))
      if (targetSessionId === sessionId) newChat()
    },
    [sessionId, userKey, newChat],
  )

  return {
    messages,
    hasStarted,
    isTyping,
    sessionId,
    sessions,
    sendMessage,
    newChat,
    loadSession,
    renameSessionTitle,
    toggleSessionPinned,
    deleteSession,
  }
}
