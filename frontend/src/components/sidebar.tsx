"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Archive,
  BarChart3,
  Bell,
  Bot,
  CircleQuestionMark,
  CloudCheck,
  FileText,
  LayoutDashboard,
  Plus,
  Scale,
  Settings,
  Workflow,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";

// right: null — виден всем ролям
const NAV = [
  { href: "/dashboard", label: "Дашборд", icon: LayoutDashboard, right: "view_all" },
  { href: "/contracts", label: "Контракты", icon: FileText, right: null },
  { href: "/analysis", label: "Анализ", icon: BarChart3, right: "view_all" },
  { href: "/agents", label: "AI-агенты", icon: Bot, right: null },
  { href: "/workflow", label: "Согласование", icon: Workflow, right: null },
  { href: "/notifications", label: "Уведомления", icon: Bell, right: null },
  { href: "/archive", label: "Архив", icon: Archive, right: null },
  { href: "/settings", label: "Настройки", icon: Settings, right: null },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user } = useAuth();

  const items = NAV.filter((item) => item.right === null || can(user, item.right));

  return (
    <aside className="w-60 shrink-0 border-r border-outline-variant bg-surface-container-low flex flex-col">
      <div className="flex items-center gap-3 px-5 pt-6 pb-5">
        <div className="w-10 h-10 rounded-lg bg-primary text-on-primary flex items-center justify-center">
          <Scale size={22} />
        </div>
        <div>
          <div className="font-semibold leading-tight">AI Legal Workspace</div>
          <div className="text-xs text-on-surface-variant">Legal OS</div>
        </div>
      </div>

      {can(user, "create") && (
        <div className="px-4 pb-4">
          <Link
            href="/contracts"
            className="flex items-center justify-center gap-2 h-10 rounded-lg bg-primary text-on-primary text-sm font-medium hover:bg-primary-hover transition-colors"
          >
            <Plus size={18} />
            Новый контракт
          </Link>
        </div>
      )}

      <nav className="flex-1 px-4 space-y-1">
        {items.map(({ href, label, icon: Icon }) => {
          const active = pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-3 h-10 rounded-lg text-sm transition-colors ${
                active
                  ? "bg-secondary-container text-on-surface font-medium"
                  : "text-on-surface-variant hover:bg-surface-container"
              }`}
            >
              <Icon size={18} />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="px-4 py-5 border-t border-outline-variant space-y-1">
        <div className="flex items-center gap-3 px-3 h-9 text-sm text-on-surface-variant">
          <CloudCheck size={18} />
          Система работает
        </div>
        <div className="flex items-center gap-3 px-3 h-9 text-sm text-on-surface-variant">
          <CircleQuestionMark size={18} />
          Помощь
        </div>
      </div>
    </aside>
  );
}
