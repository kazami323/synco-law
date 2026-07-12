"use client";

import {
  Bot,
  ChevronLeft,
  ChevronRight,
  FileText,
  LayoutDashboard,
  MessageSquarePlus,
  Search,
  Settings,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { getAgent } from "@/lib/agents";

export interface SidebarSession {
  id: string;
  agent: string;
  title: string;
  updatedAt: string;
}

interface ChatSidebarProps {
  sessions: SidebarSession[];
  activeSessionId: string | null;
  userName: string;
  collapsed: boolean;
  mobileOpen: boolean;
  onCollapsedChange: (value: boolean) => void;
  onMobileClose: () => void;
  onNewChat: () => void;
  onOpenSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
}

export function ChatSidebar({
  sessions,
  activeSessionId,
  userName,
  collapsed,
  mobileOpen,
  onCollapsedChange,
  onMobileClose,
  onNewChat,
  onOpenSession,
  onDeleteSession,
}: ChatSidebarProps) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const value = query.trim().toLocaleLowerCase("ru-RU");
    if (!value) return sessions;
    return sessions.filter((session) =>
      session.title.toLocaleLowerCase("ru-RU").includes(value)
    );
  }, [query, sessions]);

  const initial = userName.trim().slice(0, 1).toUpperCase() || "П";

  return (
    <>
      {mobileOpen && (
        <button
          type="button"
          aria-label="Закрыть меню"
          onClick={onMobileClose}
          className="fixed inset-0 z-40 bg-on-surface/40 lg:hidden"
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex shrink-0 flex-col border-r border-outline-variant bg-surface-container-low text-on-surface transition-[width,transform] duration-200 lg:static lg:translate-x-0 ${collapsed ? "lg:w-[4.5rem]" : "lg:w-[17.5rem]"} ${mobileOpen ? "w-[17.5rem] translate-x-0" : "w-[17.5rem] -translate-x-full"}`}
      >
        <div className="flex h-16 items-center gap-2 px-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary text-on-primary">
            <Sparkles size={19} />
          </span>
          {(!collapsed || mobileOpen) && (
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold">Synco AI</div>
              <div className="truncate text-[11px] text-on-surface-variant">Legal Workspace</div>
            </div>
          )}
          <button
            type="button"
            aria-label="Закрыть меню"
            onClick={onMobileClose}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface lg:hidden"
          >
            <X size={18} />
          </button>
        </div>

        <div className="px-3 pt-2">
          <button
            type="button"
            title="Новый чат"
            aria-label="Новый чат"
            onClick={() => {
              onNewChat();
              onMobileClose();
            }}
            className={`flex h-11 w-full items-center rounded-xl bg-primary text-sm font-medium text-on-primary transition-colors hover:bg-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${collapsed && !mobileOpen ? "justify-center" : "gap-3 px-3"}`}
          >
            <MessageSquarePlus size={19} className="shrink-0" />
            {(!collapsed || mobileOpen) && <span>Новый чат</span>}
          </button>
        </div>

        {(!collapsed || mobileOpen) && (
          <div className="px-3 pt-3">
            <div className="relative">
              <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-outline" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                aria-label="Поиск по чатам"
                placeholder="Поиск по чатам"
                className="h-10 w-full rounded-xl bg-transparent pl-9 pr-3 text-sm outline-none placeholder:text-outline hover:bg-surface-container focus:bg-surface-container-lowest focus:ring-1 focus:ring-outline-variant"
              />
            </div>
          </div>
        )}

        <nav className="space-y-1 px-3 pt-3">
          <Link
            href="/dashboard"
            title="Вернуться на дашборд"
            className={`flex h-10 items-center rounded-xl text-sm text-on-surface-variant transition-colors hover:bg-surface-container hover:text-on-surface ${collapsed && !mobileOpen ? "justify-center" : "gap-3 px-3"}`}
          >
            <LayoutDashboard size={18} className="shrink-0" />
            {(!collapsed || mobileOpen) && <span>Дашборд</span>}
          </Link>
          <Link
            href="/agents"
            title="AI-агенты"
            className={`flex h-10 items-center rounded-xl bg-secondary-container text-sm font-medium text-on-surface ${collapsed && !mobileOpen ? "justify-center" : "gap-3 px-3"}`}
          >
            <Bot size={18} className="shrink-0 text-primary" />
            {(!collapsed || mobileOpen) && <span>AI-агенты</span>}
          </Link>
          <Link
            href="/contracts"
            title="Библиотека документов"
            className={`flex h-10 items-center rounded-xl text-sm text-on-surface-variant transition-colors hover:bg-surface-container hover:text-on-surface ${collapsed && !mobileOpen ? "justify-center" : "gap-3 px-3"}`}
          >
            <FileText size={18} className="shrink-0" />
            {(!collapsed || mobileOpen) && <span>Библиотека документов</span>}
          </Link>
        </nav>

        <div className="mt-5 min-h-0 flex-1 overflow-y-auto px-2">
          {(!collapsed || mobileOpen) && (
            <div className="px-3 pb-2 text-xs font-medium text-on-surface-variant">Недавние</div>
          )}
          <div className="space-y-0.5">
            {filtered.map((session) => {
              const active = session.id === activeSessionId;
              const AgentIcon = getAgent(session.agent).icon;
              return (
                <div key={session.id} className="group relative">
                  <button
                    type="button"
                    title={session.title}
                    onClick={() => {
                      onOpenSession(session.id);
                      onMobileClose();
                    }}
                    className={`flex h-10 w-full items-center rounded-xl text-left text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-primary ${active ? "bg-primary-fixed text-on-surface" : "text-on-surface-variant hover:bg-surface-container hover:text-on-surface"} ${collapsed && !mobileOpen ? "justify-center" : "gap-3 px-3 pr-10"}`}
                  >
                    <AgentIcon size={17} className={`shrink-0 ${active ? "text-primary" : ""}`} />
                    {(!collapsed || mobileOpen) && <span className="truncate">{session.title}</span>}
                  </button>
                  {(!collapsed || mobileOpen) && (
                    <button
                      type="button"
                      title="Удалить чат"
                      aria-label={`Удалить чат ${session.title}`}
                      onClick={() => onDeleteSession(session.id)}
                      className="absolute right-2 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-lg text-outline opacity-0 transition hover:bg-error-container hover:text-error focus:opacity-100 group-hover:opacity-100"
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div className="border-t border-outline-variant p-3">
          <div className={`flex items-center ${collapsed && !mobileOpen ? "justify-center" : "gap-3"}`}>
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary-fixed text-sm font-semibold text-primary">
              {initial}
            </span>
            {(!collapsed || mobileOpen) && (
              <>
                <span className="min-w-0 flex-1 truncate text-sm font-medium">{userName || "Пользователь"}</span>
                <Link
                  href="/settings"
                  title="Настройки"
                  aria-label="Настройки"
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface"
                >
                  <Settings size={17} />
                </Link>
              </>
            )}
          </div>
          <button
            type="button"
            title={collapsed ? "Развернуть панель" : "Свернуть панель"}
            aria-label={collapsed ? "Развернуть панель" : "Свернуть панель"}
            onClick={() => onCollapsedChange(!collapsed)}
            className="mt-2 hidden h-8 w-full items-center justify-center rounded-lg text-outline transition-colors hover:bg-surface-container hover:text-on-surface lg:flex"
          >
            {collapsed ? <ChevronRight size={17} /> : <ChevronLeft size={17} />}
          </button>
        </div>
      </aside>
    </>
  );
}
