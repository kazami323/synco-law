"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Download,
  Menu,
  MessageSquarePlus,
  Trash2,
} from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChatComposer } from "@/components/ai-chat/chat-composer";
import { ChatSidebar } from "@/components/ai-chat/chat-sidebar";
import {
  type ChatMessage,
  MessageList,
} from "@/components/ai-chat/message-list";
import { getAgent } from "@/lib/agents";
import { api, ApiError, apiChatStream, apiParseFile } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ContractList } from "@/lib/types";

interface ChatSession {
  id: string;
  agent: string;
  title: string;
  updatedAt: string;
  messages: ChatMessage[];
  contractId?: string;
  documentName?: string | null;
}

interface StoredChatSession {
  id: string;
  agent: string;
  title: string;
  updated_at: string;
  messages: ChatMessage[];
  contract_id?: string | null;
  document_name?: string | null;
}

interface AttachedDocument {
  name: string;
  text: string;
  size: number;
  type: string;
  extractionMethod: "text" | "ocr";
  textChars: number;
}

interface SendPayload {
  sessionId: string;
  agentKey: string;
  history: ChatMessage[];
  contractId: string;
  docs: AttachedDocument[];
}

const MAX_SESSIONS = 60;
const MAX_ATTACHED_DOCUMENTS = 3;
const MAX_COMBINED_DOCUMENT_CHARS = 90_000;

function documentNames(documents: AttachedDocument[]): string | null {
  if (documents.length === 0) return null;
  return documents.map((document) => document.name).join(", ").slice(0, 512);
}

function combinedDocumentText(documents: AttachedDocument[]): string | null {
  if (documents.length === 0) return null;
  const perDocument = Math.floor(MAX_COMBINED_DOCUMENT_CHARS / documents.length);
  return documents
    .map(
      (document, index) =>
        `=== Документ ${index + 1}: ${document.name} ===\n${document.text.slice(0, perDocument)}`
    )
    .join("\n\n");
}

function createSession(agentKey: string): ChatSession {
  return {
    id:
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `chat-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    agent: agentKey,
    title: "Новый чат",
    updatedAt: new Date().toISOString(),
    messages: [],
    contractId: "",
    documentName: null,
  };
}

function sessionTitle(messages: ChatMessage[]): string {
  const source =
    messages.find((message) => message.role === "user")?.content ??
    messages[0]?.content;
  if (!source) return "Новый чат";
  const clean = source.replace(/\s+/g, " ").trim();
  return clean.length > 48 ? `${clean.slice(0, 48)}...` : clean;
}

function readSessions(key: string): ChatSession[] {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item): item is ChatSession => {
        if (!item || typeof item !== "object") return false;
        const candidate = item as Partial<ChatSession>;
        return (
          typeof candidate.id === "string" &&
          typeof candidate.agent === "string" &&
          Array.isArray(candidate.messages)
        );
      })
      .slice(0, MAX_SESSIONS);
  } catch {
    return [];
  }
}

function fromStoredSession(session: StoredChatSession): ChatSession {
  return {
    id: session.id,
    agent: session.agent,
    title: session.title,
    updatedAt: session.updated_at,
    messages: session.messages,
    contractId: session.contract_id ?? "",
    documentName: session.document_name ?? null,
  };
}

function storedPayload(session: ChatSession) {
  return {
    id: session.id,
    agent: session.agent,
    title: session.title,
    messages: session.messages,
    contract_id: session.contractId || null,
    document_name: session.documentName ?? null,
  };
}

async function createRemoteSession(session: ChatSession): Promise<void> {
  await api("/api/agents/sessions/", {
    method: "POST",
    body: storedPayload(session),
  });
}

async function updateRemoteSession(session: ChatSession): Promise<void> {
  try {
    await api(`/api/agents/sessions/${session.id}`, {
      method: "PATCH",
      body: storedPayload(session),
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      await createRemoteSession(session);
      return;
    }
    throw error;
  }
}

export default function AgentChatPage() {
  const params = useParams<{ agent: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const [initialAgentKey] = useState(() => getAgent(params.agent).key);
  const [agent, setAgent] = useState(initialAgentKey);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  // Живой черновик потокового ответа: null — стрим не идёт
  const [streamingDraft, setStreamingDraft] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [docs, setDocs] = useState<AttachedDocument[]>([]);
  const [uploading, setUploading] = useState(false);
  const [contractId, setContractId] = useState("");
  const [error, setError] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const activeSessionIdRef = useRef<string | null>(null);

  const active = getAgent(agent);
  const ActiveIcon = active.icon;
  const storageKey = `synco:agent-chat-history:${user?.id ?? "guest"}`;

  const contracts = useQuery({
    queryKey: ["contracts", "for-chat"],
    queryFn: () => api<ContractList>("/api/contracts/?limit=50"),
  });

  const persistSessions = useCallback(
    (next: ChatSession[]) => {
      try {
        window.localStorage.setItem(
          storageKey,
          JSON.stringify(next.slice(0, MAX_SESSIONS))
        );
      } catch (persistError) {
        console.warn("Не удалось сохранить историю чатов", persistError);
      }
    },
    [storageKey]
  );

  const commitSessions = useCallback(
    (updater: (current: ChatSession[]) => ChatSession[]) => {
      setSessions((current) => {
        const next = updater(current)
          .sort(
            (first, second) =>
              new Date(second.updatedAt).getTime() -
              new Date(first.updatedAt).getTime()
          )
          .slice(0, MAX_SESSIONS);
        persistSessions(next);
        return next;
      });
    },
    [persistSessions]
  );

  const openSession = useCallback(
    (session: ChatSession) => {
      setActiveSessionId(session.id);
      setAgent(session.agent);
      setMessages(session.messages);
      setContractId(session.contractId ?? "");
      setDocs([]);
      setError("");
      router.replace(`/agents/chat/${session.agent}`, { scroll: false });
    },
    [router]
  );

  useEffect(() => {
    activeSessionIdRef.current = activeSessionId;
  }, [activeSessionId]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      await Promise.resolve();
      let loaded: ChatSession[] = [];
      try {
        const remote = await api<StoredChatSession[]>(
          "/api/agents/sessions/?limit=60"
        );
        loaded = remote.map(fromStoredSession);
        if (loaded.length === 0) {
          const cached = readSessions(storageKey);
          loaded = cached;
          await Promise.all(
            cached.slice(0, 20).map((session) =>
              api("/api/agents/sessions/", {
                method: "POST",
                body: {
                  id: session.id,
                  agent: session.agent,
                  title: session.title,
                  messages: session.messages,
                  contract_id: session.contractId || null,
                  document_name: session.documentName ?? null,
                },
              }).catch(() => undefined)
            )
          );
        }
      } catch {
        loaded = readSessions(storageKey);
      }
      if (cancelled) return;
      if (loaded.length > 0) {
        setSessions(loaded);
        openSession(loaded[0]);
        return;
      }

      const created = createSession(initialAgentKey || "law");
      setSessions([created]);
      persistSessions([created]);
      setActiveSessionId(created.id);
      setAgent(created.agent);
      setMessages([]);
      void createRemoteSession(created);
    })();

    return () => {
      cancelled = true;
    };
  }, [initialAgentKey, openSession, persistSessions, storageKey]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  function saveSessionMessages(
    sessionId: string,
    nextMessages: ChatMessage[],
    agentKey = agent,
    nextContractId = contractId,
    documentName = documentNames(docs)
  ) {
    const existing =
      sessions.find((session) => session.id === sessionId) ??
      createSession(agentKey);
    const updated: ChatSession = {
      ...existing,
      id: sessionId,
      agent: agentKey,
      title: sessionTitle(nextMessages),
      updatedAt: new Date().toISOString(),
      messages: nextMessages,
      contractId: nextContractId,
      documentName: documentName ?? existing.documentName ?? null,
    };
    commitSessions((current) => {
      return [updated, ...current.filter((session) => session.id !== sessionId)];
    });
    void updateRemoteSession(updated);
  }

  function ensureActiveSession(agentKey = agent): string {
    if (activeSessionId) return activeSessionId;
    const created = createSession(agentKey);
    setActiveSessionId(created.id);
    commitSessions((current) => [created, ...current]);
    return created.id;
  }

  function createNewChat(agentKey = agent) {
    const created = createSession(agentKey);
    commitSessions((current) => [created, ...current]);
    openSession(created);
    void createRemoteSession(created);
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }

  function deleteSession(id: string) {
    const next = sessions.filter((session) => session.id !== id);
    if (next.length === 0) {
      const created = createSession(agent);
      setSessions([created]);
      persistSessions([created]);
      openSession(created);
      void api(`/api/agents/sessions/${id}`, { method: "DELETE" }).catch(
        () => undefined
      );
      void createRemoteSession(created);
      return;
    }
    setSessions(next);
    persistSessions(next);
    if (activeSessionId === id) openSession(next[0]);
    void api(`/api/agents/sessions/${id}`, { method: "DELETE" }).catch(
      () => undefined
    );
  }

  function clearCurrentChat() {
    const sessionId = ensureActiveSession();
    setMessages([]);
    setInput("");
    setDocs([]);
    setError("");
    commitSessions((current) =>
      current.map((session) =>
        session.id === sessionId
          ? {
              ...session,
              title: "Новый чат",
              messages: [],
              documentName: null,
              updatedAt: new Date().toISOString(),
            }
          : session
      )
    );
    const current = sessions.find((session) => session.id === sessionId);
    if (current) {
      void updateRemoteSession({
        ...current,
        title: "Новый чат",
        messages: [],
        documentName: null,
        updatedAt: new Date().toISOString(),
      });
    }
  }

  function switchAgent(key: string) {
    setAgent(key);
    window.localStorage.setItem("synco:last-agent", key);
    router.replace(`/agents/chat/${key}`, { scroll: false });
    if (!activeSessionId) return;
    commitSessions((current) =>
      current.map((session) =>
        session.id === activeSessionId
          ? { ...session, agent: key, updatedAt: new Date().toISOString() }
          : session
      )
    );
    const current = sessions.find((session) => session.id === activeSessionId);
    if (current) void updateRemoteSession({ ...current, agent: key });
  }

  const send = useMutation({
    mutationFn: async ({ sessionId, agentKey, history, contractId, docs }: SendPayload) => {
      const body = {
        agent: agentKey,
        messages: history.map(({ role, content, agent: messageAgent, feedback, sources }) => ({
          role,
          content,
          agent: messageAgent,
          feedback,
          sources: sources ?? [],
        })),
        contract_id: contractId || null,
        document_text: contractId ? null : combinedDocumentText(docs),
        document_name: contractId ? null : documentNames(docs),
        session_id: sessionId,
      };
      try {
        // Потоковый ответ: текст появляется по мере генерации
        return await apiChatStream<NonNullable<ChatMessage["sources"]>>(body, (text) => {
          if (activeSessionIdRef.current !== sessionId) return;
          setStreamingDraft((current) => (current ?? "") + text);
        });
      } catch (streamError) {
        // Старый бэкенд без /stream — обычный запрос
        if (
          streamError instanceof ApiError &&
          (streamError.status === 404 || streamError.status === 405)
        ) {
          return api<{ reply: string; sources: ChatMessage["sources"] }>(
            "/api/agents/chat",
            { method: "POST", body }
          );
        }
        throw streamError;
      }
    },
    onSettled: () => setStreamingDraft(null),
    onSuccess: (data, payload) => {
      const finalMessages: ChatMessage[] = [
        ...payload.history,
        {
          role: "assistant",
          content: data.reply,
          agent: payload.agentKey,
          sources: data.sources ?? [],
        },
      ];
      saveSessionMessages(
        payload.sessionId,
        finalMessages,
        payload.agentKey,
        payload.contractId,
        documentNames(payload.docs)
      );
      if (activeSessionIdRef.current === payload.sessionId) {
        setMessages(finalMessages);
      }
    },
    onError: (requestError) =>
      setError(
        requestError instanceof Error ? requestError.message : "Ошибка запроса"
      ),
  });

  function sendText(text: string) {
    const trimmed = text.trim();
    if (!trimmed || send.isPending || uploading) return;
    setError("");
    const sessionId = ensureActiveSession();
    const history: ChatMessage[] = [
      ...messages,
      { role: "user", content: trimmed },
    ];
    setMessages(history);
    saveSessionMessages(sessionId, history);
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    send.mutate({ sessionId, agentKey: agent, history, contractId, docs });
  }

  function regenerateLastAnswer() {
    if (send.isPending || uploading) return;
    const history =
      messages.at(-1)?.role === "assistant" ? messages.slice(0, -1) : messages;
    if (!history.some((message) => message.role === "user")) return;
    const sessionId = ensureActiveSession();
    setMessages(history);
    setError("");
    saveSessionMessages(sessionId, history);
    send.mutate({ sessionId, agentKey: agent, history, contractId, docs });
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    sendText(input);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendText(input);
    }
  }

  function grow(event: React.ChangeEvent<HTMLTextAreaElement>) {
    setInput(event.target.value);
    const element = event.target;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 176)}px`;
  }

  async function attachFile(event: React.ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(event.target.files ?? []);
    if (selected.length === 0) return;
    const available = MAX_ATTACHED_DOCUMENTS - docs.length;
    if (available <= 0 || selected.length > available) {
      setError(`Можно прикрепить не более ${MAX_ATTACHED_DOCUMENTS} файлов к одному чату`);
      if (fileRef.current) fileRef.current.value = "";
      return;
    }
    setError("");
    setUploading(true);
    try {
      const parsedDocuments: AttachedDocument[] = [];
      for (const file of selected) {
        const form = new FormData();
        form.append("file", file);
        const parsed = await apiParseFile(form);
        parsedDocuments.push({
          name: parsed.filename,
          text: parsed.text,
          size: file.size,
          type: file.name.split(".").pop()?.toUpperCase() ?? "ФАЙЛ",
          extractionMethod: parsed.extraction_method,
          textChars: parsed.text.length,
        });
      }
      const nextDocs = [...docs, ...parsedDocuments];
      const nextDocumentName = documentNames(nextDocs);
      setDocs(nextDocs);
      setContractId("");
      if (activeSessionId) {
        commitSessions((current) =>
          current.map((session) =>
            session.id === activeSessionId
              ? { ...session, documentName: nextDocumentName }
              : session
          )
        );
        const current = sessions.find((session) => session.id === activeSessionId);
        if (current) {
          void updateRemoteSession({
            ...current,
            contractId: "",
            documentName: nextDocumentName,
          });
        }
      }
    } catch (uploadError) {
      setError(
        uploadError instanceof Error
          ? uploadError.message
          : "Не удалось прочитать файл"
      );
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  function removeFile(index: number) {
    const nextDocs = docs.filter((_, documentIndex) => documentIndex !== index);
    const nextDocumentName = documentNames(nextDocs);
    setDocs(nextDocs);
    if (!activeSessionId) return;
    commitSessions((current) =>
      current.map((session) =>
        session.id === activeSessionId
          ? { ...session, documentName: nextDocumentName }
          : session
      )
    );
    const current = sessions.find((session) => session.id === activeSessionId);
    if (current) void updateRemoteSession({ ...current, documentName: nextDocumentName });
  }

  function clearPersistedDocumentContext() {
    setDocs([]);
    if (!activeSessionId) return;
    commitSessions((current) =>
      current.map((session) =>
        session.id === activeSessionId
          ? { ...session, documentName: null, updatedAt: new Date().toISOString() }
          : session
      )
    );
    const current = sessions.find((session) => session.id === activeSessionId);
    if (current) void updateRemoteSession({ ...current, documentName: null });
  }

  function rateMessage(messageIndex: number, rating: "up" | "down" | null) {
    if (!activeSessionId) return;
    const previous = messages[messageIndex]?.feedback ?? null;
    const nextMessages = messages.map((message, index) =>
      index === messageIndex ? { ...message, feedback: rating ?? undefined } : message
    );
    setMessages(nextMessages);
    commitSessions((current) =>
      current.map((session) =>
        session.id === activeSessionId
          ? { ...session, messages: nextMessages, updatedAt: new Date().toISOString() }
          : session
      )
    );
    void api(`/api/agents/sessions/${activeSessionId}/messages/${messageIndex}/feedback`, {
      method: "PUT",
      body: { rating },
    }).catch((feedbackError) => {
      const restored = messages.map((message, index) =>
        index === messageIndex
          ? { ...message, feedback: previous ?? undefined }
          : message
      );
      setMessages(restored);
      setError(
        feedbackError instanceof Error
          ? feedbackError.message
          : "Не удалось сохранить оценку ответа"
      );
    });
  }

  function changeContract(id: string) {
    setContractId(id);
    if (id) setDocs([]);
    if (!activeSessionId) return;
    commitSessions((current) =>
      current.map((session) =>
        session.id === activeSessionId
          ? { ...session, contractId: id, documentName: id ? null : session.documentName }
          : session
      )
    );
    const current = sessions.find((session) => session.id === activeSessionId);
    if (current) {
      void updateRemoteSession({
        ...current,
        contractId: id,
        documentName: id ? null : current.documentName,
      });
    }
  }

  function exportChat() {
    if (messages.length === 0) return;
    const content = messages
      .map((message) => {
        const label =
          message.role === "user"
            ? "Пользователь"
            : getAgent(message.agent ?? agent).name;
        return `## ${label}\n\n${message.content}`;
      })
      .join("\n\n---\n\n");
    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${sessionTitle(messages) || "chat"}.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  const orderedSessions = useMemo(
    () =>
      [...sessions].sort(
        (first, second) =>
          new Date(second.updatedAt).getTime() -
          new Date(first.updatedAt).getTime()
      ),
    [sessions]
  );

  const userName = user?.full_name || user?.username || "Пользователь";
  const persistedDocumentName =
    docs.length === 0 && !contractId
      ? sessions.find((session) => session.id === activeSessionId)?.documentName ?? null
      : null;

  return (
    <div className="flex h-dvh min-h-[38rem] overflow-hidden bg-surface text-on-surface">
      <ChatSidebar
        sessions={orderedSessions}
        activeSessionId={activeSessionId}
        userName={userName}
        collapsed={sidebarCollapsed}
        mobileOpen={mobileSidebarOpen}
        onCollapsedChange={setSidebarCollapsed}
        onMobileClose={() => setMobileSidebarOpen(false)}
        onNewChat={() => createNewChat()}
        onOpenSession={(id) => {
          const session = sessions.find((item) => item.id === id);
          if (session) openSession(session);
        }}
        onDeleteSession={deleteSession}
      />

      <main className="relative flex min-w-0 flex-1 flex-col bg-surface">
        <header className="flex h-16 shrink-0 items-center gap-3 border-b border-outline-variant bg-surface-container-lowest px-3 sm:px-5">
          <button
            type="button"
            title="Открыть меню"
            aria-label="Открыть меню"
            onClick={() => setMobileSidebarOpen(true)}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-on-surface-variant hover:bg-surface-container hover:text-on-surface lg:hidden"
          >
            <Menu size={19} />
          </button>
          <button
            type="button"
            title="Вернуться в рабочее пространство"
            aria-label="Вернуться в рабочее пространство"
            onClick={() => router.push("/dashboard")}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-on-surface-variant outline-none transition-colors hover:bg-surface-container hover:text-on-surface focus-visible:ring-2 focus-visible:ring-primary"
          >
            <ArrowLeft size={19} />
          </button>
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary-fixed text-primary">
            <ActiveIcon size={18} />
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="truncate text-sm font-semibold text-on-surface">{active.name}</span>
              <span className="hidden items-center gap-1 text-[10px] font-medium text-success sm:inline-flex">
                <span className="h-1.5 w-1.5 rounded-full bg-success" />
                Активен
              </span>
            </div>
            <div className="truncate text-xs text-on-surface-variant">{active.role}</div>
          </div>
          <div className="ml-auto flex items-center gap-1">
            <button
              type="button"
              title="Новый чат"
              aria-label="Новый чат"
              onClick={() => createNewChat()}
              className="flex h-9 w-9 items-center justify-center rounded-lg text-on-surface-variant hover:bg-surface-container hover:text-on-surface"
            >
              <MessageSquarePlus size={18} />
            </button>
            <button
              type="button"
              title="Экспортировать чат"
              aria-label="Экспортировать чат"
              disabled={messages.length === 0}
              onClick={exportChat}
              className="flex h-9 w-9 items-center justify-center rounded-lg text-on-surface-variant hover:bg-surface-container hover:text-on-surface disabled:opacity-35"
            >
              <Download size={18} />
            </button>
            <button
              type="button"
              title="Очистить чат"
              aria-label="Очистить чат"
              disabled={messages.length === 0}
              onClick={clearCurrentChat}
              className="flex h-9 w-9 items-center justify-center rounded-lg text-on-surface-variant hover:bg-error-container hover:text-error disabled:opacity-35"
            >
              <Trash2 size={18} />
            </button>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <MessageList
            messages={
              streamingDraft !== null
                ? [
                    ...messages,
                    {
                      role: "assistant",
                      content: streamingDraft,
                      agent,
                      sources: [],
                    },
                  ]
                : messages
            }
            agentKey={agent}
            pending={send.isPending && streamingDraft === null}
            bottomRef={bottomRef}
            onPrompt={sendText}
            onRegenerate={regenerateLastAnswer}
            onFeedback={rateMessage}
          />
        </div>

        <ChatComposer
          value={input}
          agentKey={agent}
          pending={send.isPending}
          documents={docs}
          uploading={uploading}
          persistedDocumentName={persistedDocumentName}
          contractId={contractId}
          contracts={contracts.data?.items ?? []}
          error={error}
          textareaRef={textareaRef}
          fileRef={fileRef}
          onValueChange={grow}
          onKeyDown={onKeyDown}
          onSubmit={submit}
          onAgentChange={switchAgent}
          onFileChange={attachFile}
          onRemoveFile={removeFile}
          onClearPersistedDocument={clearPersistedDocumentContext}
          onContractChange={changeContract}
        />
      </main>
    </div>
  );
}
