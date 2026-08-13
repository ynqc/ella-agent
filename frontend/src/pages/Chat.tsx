import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import './Chat.css'

type Message = {
  id: string
  role: 'assistant' | 'user'
  content: string
  phases?: PhaseEvent[]
}

type PhaseEvent = {
  phase: string
  message: string
  tools?: string[]
}

type ChatThread = {
  id: string
  title: string
  sessionId: string
  messages: Message[]
}

type ChatStorageState = {
  activeThreadId: string
  threads: ChatThread[]
}

const CHAT_STORAGE_KEY = 'ella-chat-state'

function createId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function createWelcomeMessage(): Message {
  return {
    id: 'welcome',
    role: 'assistant',
    content:
      'Hello, I am Ella. Ask a question on the left input box and I will stream the answer into this chat window.',
  }
}

function createSessionId() {
  return `session-${createId()}`
}

function createThread(overrides?: Partial<ChatThread>): ChatThread {
  return {
    id: `thread-${createId()}`,
    title: 'New conversation',
    sessionId: createSessionId(),
    messages: [createWelcomeMessage()],
    ...overrides,
  }
}

function sanitizeMessage(value: unknown): Message | null {
  if (!value || typeof value !== 'object') {
    return null
  }

  const candidate = value as Partial<Message>

  if (typeof candidate.id !== 'string' || (candidate.role !== 'assistant' && candidate.role !== 'user')) {
    return null
  }

  const phases: PhaseEvent[] = []
  if (Array.isArray(candidate.phases)) {
    for (const p of candidate.phases) {
      if (p && typeof p === 'object' && typeof p.message === 'string') {
        phases.push({ phase: p.phase || '', message: p.message, tools: p.tools })
      }
    }
  }

  return {
    id: candidate.id,
    role: candidate.role,
    content: typeof candidate.content === 'string' ? candidate.content : '',
    phases: phases.length > 0 ? phases : undefined,
  }
}

function sanitizeThread(value: unknown): ChatThread | null {
  if (!value || typeof value !== 'object') {
    return null
  }

  const candidate = value as Partial<ChatThread>
  const messages = Array.isArray(candidate.messages)
    ? candidate.messages.map(sanitizeMessage).filter((item): item is Message => item !== null)
    : []

  if (typeof candidate.id !== 'string' || typeof candidate.sessionId !== 'string') {
    return null
  }

  return {
    id: candidate.id,
    title: typeof candidate.title === 'string' && candidate.title.trim() ? candidate.title : 'New conversation',
    sessionId: candidate.sessionId,
    messages: messages.length > 0 ? messages : [createWelcomeMessage()],
  }
}

function getStoredChatState(): ChatStorageState {
  const fallbackThread = createThread()

  if (typeof window === 'undefined') {
    return {
      activeThreadId: fallbackThread.id,
      threads: [fallbackThread],
    }
  }

  try {
    const raw = window.sessionStorage.getItem(CHAT_STORAGE_KEY)

    if (!raw) {
      return {
        activeThreadId: fallbackThread.id,
        threads: [fallbackThread],
      }
    }

    const payload = JSON.parse(raw) as Partial<ChatStorageState>
    const threads = Array.isArray(payload.threads)
      ? payload.threads.map(sanitizeThread).filter((item): item is ChatThread => item !== null)
      : []

    if (threads.length === 0) {
      return {
        activeThreadId: fallbackThread.id,
        threads: [fallbackThread],
      }
    }

    const activeThreadId =
      typeof payload.activeThreadId === 'string' && threads.some((thread) => thread.id === payload.activeThreadId)
        ? payload.activeThreadId
        : threads[0].id

    return {
      activeThreadId,
      threads,
    }
  } catch {
    return {
      activeThreadId: fallbackThread.id,
      threads: [fallbackThread],
    }
  }
}

function persistChatState(state: ChatStorageState) {
  if (typeof window === 'undefined') {
    return
  }

  try {
    window.sessionStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(state))
  } catch {
    // Ignore storage failures and keep the in-memory thread state.
  }
}

function buildThreadTitle(messages: Message[]) {
  const firstUserMessage = messages.find((message) => message.role === 'user' && message.content.trim())

  if (!firstUserMessage) {
    return 'New conversation'
  }

  return firstUserMessage.content.trim().slice(0, 40)
}

async function buildChatError(response: Response) {
  const contentType = response.headers.get('content-type') || ''
  const fallbackMessage = `Chat API request failed with status ${response.status}.`

  try {
    if (contentType.includes('application/json')) {
      const payload = (await response.json()) as { detail?: unknown }

      if (typeof payload.detail === 'string' && payload.detail.trim()) {
        return payload.detail
      }

      if (Array.isArray(payload.detail) && payload.detail.length > 0) {
        return payload.detail
          .map((item) => {
            if (typeof item === 'string') {
              return item
            }

            if (item && typeof item === 'object' && 'msg' in item && typeof item.msg === 'string') {
              return item.msg
            }

            return JSON.stringify(item)
          })
          .join('; ')
      }
    }

    const text = await response.text()

    if (text.trim()) {
      return text.trim()
    }
  } catch {
    // Fall through to the generic status message.
  }

  return fallbackMessage
}

export default function Chat() {
  const [chatState, setChatState] = useState<ChatStorageState>(() => getStoredChatState())
  const [draft, setDraft] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState('')
  const formRef = useRef<HTMLFormElement | null>(null)
  const viewportRef = useRef<HTMLDivElement | null>(null)

  const activeThread = useMemo(
    () => chatState.threads.find((thread) => thread.id === chatState.activeThreadId) ?? chatState.threads[0],
    [chatState],
  )
  const messages = activeThread?.messages ?? []

  useEffect(() => {
    persistChatState(chatState)
  }, [chatState])

  useEffect(() => {
    const viewport = viewportRef.current

    if (!viewport) {
      return
    }

    viewport.scrollTop = viewport.scrollHeight
  }, [messages])

  const canSend = useMemo(() => draft.trim().length > 0 && !isStreaming, [draft, isStreaming])

  function updateThread(threadId: string, updater: (thread: ChatThread) => ChatThread) {
    setChatState((current) => ({
      ...current,
      threads: current.threads.map((thread) =>
        thread.id === threadId ? updater(thread) : thread,
      ),
    }))
  }

  function handleCreateThread() {
    if (isStreaming) {
      return
    }

    const nextThread = createThread()

    setChatState((current) => ({
      activeThreadId: nextThread.id,
      threads: [nextThread, ...current.threads],
    }))
    setDraft('')
    setError('')
  }

  function handleSelectThread(threadId: string) {
    if (threadId === chatState.activeThreadId) {
      return
    }

    setChatState((current) => ({
      ...current,
      activeThreadId: threadId,
    }))
    setError('')
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) {
      return
    }

    event.preventDefault()
    formRef.current?.requestSubmit()
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    const message = draft.trim()
    if (!message || isStreaming) {
      return
    }

    const userMessage: Message = {
      id: createId(),
      role: 'user',
      content: message,
    }
    const assistantId = createId()
    const threadId = activeThread.id

    setDraft('')
    setError('')
    setIsStreaming(true)
    updateThread(threadId, (thread) => {
      const assistantMessage: Message = { id: assistantId, role: 'assistant', content: '' }
      const nextMessages: Message[] = [
        ...thread.messages,
        userMessage,
        assistantMessage,
      ]

      return {
        ...thread,
        title: buildThreadTitle(nextMessages),
        messages: nextMessages,
      }
    })

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ session_id: activeThread.sessionId, message }),
      })

      const responseSessionId = response.headers.get('X-Session-Id')

      if (responseSessionId) {
        updateThread(threadId, (thread) => ({
          ...thread,
          sessionId: responseSessionId,
        }))
      }

      if (!response.ok) {
        throw new Error(await buildChatError(response))
      }

      if (!response.body) {
        throw new Error('The chat API did not return a streaming response body.')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      const EVENT_PREFIX = '§event:'

      while (true) {
        const { value, done } = await reader.read()

        if (done) {
          break
        }

        const chunk = decoder.decode(value, { stream: true })
        const lines = chunk.split('\n')
        let textParts: string[] = []

        for (let i = 0; i < lines.length; i++) {
          const line = lines[i]
          if (line.startsWith(EVENT_PREFIX)) {
            try {
              const event = JSON.parse(line.slice(EVENT_PREFIX.length)) as PhaseEvent
              updateThread(threadId, (thread) => ({
                ...thread,
                messages: thread.messages.map((item) =>
                  item.id === assistantId
                    ? { ...item, phases: [...(item.phases || []), event] }
                    : item,
                ),
              }))
            } catch {
              // ignore malformed event
            }
          } else {
            textParts.push(line)
          }
        }

        const textContent = textParts.join('\n')
        if (textContent) {
          updateThread(threadId, (thread) => ({
            ...thread,
            messages: thread.messages.map((item) =>
              item.id === assistantId
                ? { ...item, content: `${item.content}${textContent}` }
                : item,
            ),
          }))
        }
      }
    } catch (streamError) {
      const messageText = streamError instanceof Error ? streamError.message : 'Unknown chat error.'

      setError(messageText)
      updateThread(threadId, (thread) => ({
        ...thread,
        messages: thread.messages.map((item) =>
          item.id === assistantId
            ? {
                ...item,
                content:
                  item.content || 'The assistant could not produce a response. Check whether the backend is running.',
              }
            : item,
        ),
      }))
    } finally {
      setIsStreaming(false)
    }
  }

  return (
    <section className="chat-page">
      <aside className="thread-panel">
        <div className="thread-panel-header">
          <div>
            <p className="chat-kicker">Threads</p>
            <h2>Ella Chat</h2>
          </div>
          <button className="thread-create-button" type="button" onClick={handleCreateThread} disabled={isStreaming}>
            New conversation
          </button>
        </div>

        <div className="thread-list" role="list" aria-label="Chat threads">
          {chatState.threads.map((thread) => (
            <button
              key={thread.id}
              type="button"
              className={thread.id === activeThread.id ? 'thread-card thread-card-active' : 'thread-card'}
              onClick={() => handleSelectThread(thread.id)}
              disabled={isStreaming && thread.id === activeThread.id}
            >
              <span className="thread-title">{thread.title}</span>
              <span className="thread-meta">{thread.sessionId}</span>
            </button>
          ))}
        </div>
      </aside>

      <div className="chat-main">
        <header className="chat-header">
          <div>
            <p className="chat-kicker">Conversation</p>
            <h2>{activeThread.title}</h2>
            <p className="chat-session-id">Session: {activeThread.sessionId}</p>
          </div>
          <p className="chat-status" aria-live="polite">
            {isStreaming ? 'Assistant is typing...' : 'Ready'}
          </p>
        </header>

        <div className="chat-viewport" ref={viewportRef}>
          {messages.map((message) => (
            <article
              key={message.id}
              className={message.role === 'user' ? 'message-row message-user' : 'message-row'}
            >
              <div className="message-bubble">
                <p className="message-role">{message.role === 'user' ? 'You' : 'Ella'}</p>
                {message.role === 'user' ? (
                  <p className="message-content">{message.content || (isStreaming ? '...' : '')}</p>
                ) : (
                  <>
                    {message.phases && message.phases.length > 0 && (
                      <div className="phase-pipeline">
                        {message.phases.map((phase, idx) => (
                          <div
                            key={idx}
                            className={`phase-step ${idx === message.phases!.length - 1 && isStreaming && !message.content ? 'phase-step-active' : 'phase-step-done'}`}
                          >
                            <span className="phase-dot" />
                            <span className="phase-label">{phase.message}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="message-content message-markdown">
                      {message.content ? (
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {message.content}
                        </ReactMarkdown>
                      ) : isStreaming ? (
                        <span className="typing-indicator"><span /><span /><span /></span>
                      ) : null}
                    </div>
                  </>
                )}
              </div>
            </article>
          ))}
        </div>

        <form className="chat-composer" onSubmit={handleSubmit} ref={formRef}>
          <label className="composer-label" htmlFor="message">
            Ask Ella anything
          </label>
          <div className="composer-row">
            <textarea
              id="message"
              className="composer-input"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleComposerKeyDown}
              placeholder="Type your request here..."
              rows={4}
              disabled={isStreaming}
            />
            <button className="composer-button" type="submit" disabled={!canSend}>
              {isStreaming ? 'Streaming...' : 'Send'}
            </button>
          </div>
          {error ? <p className="composer-error">{error}</p> : null}
        </form>
      </div>
    </section>
  )
}