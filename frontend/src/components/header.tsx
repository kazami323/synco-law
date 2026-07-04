"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Check, LogOut, Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ROLE_LABELS, type Notification as AppNotification } from "@/lib/types";

export function Header() {
  const { user, logout } = useAuth();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);

  const notifications = useQuery({
    queryKey: ["notifications", "header"],
    queryFn: () => api<AppNotification[]>("/api/notifications/?limit=10"),
    refetchInterval: 60_000,
  });
  const unread = useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: () => api<{ count: number }>("/api/notifications/unread-count"),
    refetchInterval: 60_000,
  });

  const markRead = useMutation({
    mutationFn: (id: string) =>
      api<AppNotification>(`/api/notifications/${id}/read`, {
        method: "PATCH",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
  });

  return (
    <header className="h-16 shrink-0 border-b border-outline-variant bg-surface-container-lowest flex items-center gap-4 px-6">
      <div className="flex-1 max-w-xl">
        <div className="relative">
          <Search
            size={18}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-outline"
          />
          <input
            placeholder="Поиск контрактов..."
            className="w-full h-10 pl-10 pr-3 rounded-lg bg-surface-container text-sm outline-none focus:ring-2 focus:ring-primary-fixed placeholder:text-outline"
          />
        </div>
      </div>

      <div className="flex items-center gap-4 ml-auto">
        <div className="relative">
          <button
            onClick={() => setOpen((value) => !value)}
            title="Уведомления"
            className="relative w-10 h-10 rounded-lg text-on-surface-variant hover:text-primary hover:bg-surface-container flex items-center justify-center cursor-pointer"
          >
            <Bell size={20} />
            {(unread.data?.count ?? 0) > 0 && (
              <span className="absolute -top-1 -right-1 min-w-5 h-5 px-1 rounded-full bg-error text-white text-[11px] font-semibold flex items-center justify-center">
                {Math.min(unread.data?.count ?? 0, 99)}
              </span>
            )}
          </button>

          {open && (
            <div className="absolute right-0 top-12 w-96 max-w-[calc(100vw-2rem)] bg-surface-container-lowest border border-outline-variant rounded-xl shadow-xl z-40 overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-outline-variant">
                <div className="font-semibold">Уведомления</div>
                <Link
                  href="/notifications"
                  onClick={() => setOpen(false)}
                  className="text-sm text-primary hover:underline"
                >
                  Все
                </Link>
              </div>
              <div className="max-h-96 overflow-y-auto">
                {notifications.isLoading ? (
                  <div className="p-4 space-y-3">
                    {[0, 1, 2].map((item) => (
                      <div
                        key={item}
                        className="h-12 rounded-lg bg-surface-container animate-pulse"
                      />
                    ))}
                  </div>
                ) : notifications.data && notifications.data.length > 0 ? (
                  notifications.data.map((item) => (
                    <div
                      key={item.id}
                      className={`px-4 py-3 border-b border-outline-variant last:border-b-0 ${
                        item.read_at ? "" : "bg-primary-fixed/40"
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <Link
                          href={
                            item.contract_id
                              ? `/contracts/${item.contract_id}`
                              : "/notifications"
                          }
                          onClick={() => setOpen(false)}
                          className="flex-1 min-w-0 text-sm hover:text-primary"
                        >
                          <span className="line-clamp-2">{item.text}</span>
                          <span className="block text-xs text-on-surface-variant mt-1">
                            {new Date(item.created_at).toLocaleString("ru-RU")}
                          </span>
                        </Link>
                        {!item.read_at && (
                          <button
                            title="Отметить прочитанным"
                            disabled={markRead.isPending}
                            onClick={() => markRead.mutate(item.id)}
                            className="w-8 h-8 rounded-lg border border-outline-variant text-primary hover:border-primary flex items-center justify-center cursor-pointer disabled:opacity-50"
                          >
                            <Check size={16} />
                          </button>
                        )}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="px-4 py-8 text-sm text-center text-on-surface-variant">
                    Уведомлений нет
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="text-right">
          <div className="text-sm font-semibold leading-tight">
            {user?.full_name || user?.username}
          </div>
          <div className="text-xs text-on-surface-variant">
            {user ? ROLE_LABELS[user.role] ?? user.role : ""}
          </div>
        </div>
        <div className="w-10 h-10 rounded-full bg-primary-fixed text-primary flex items-center justify-center font-semibold">
          {(user?.full_name || user?.username || "?").slice(0, 1).toUpperCase()}
        </div>
        <button
          onClick={logout}
          title="Выйти"
          className="text-on-surface-variant hover:text-error cursor-pointer"
        >
          <LogOut size={20} />
        </button>
      </div>
    </header>
  );
}
