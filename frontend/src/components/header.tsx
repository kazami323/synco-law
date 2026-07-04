"use client";

import { LogOut, Search } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { ROLE_LABELS } from "@/lib/types";

export function Header() {
  const { user, logout } = useAuth();

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
