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

const NAV = [
  { href: "/dashboard", label: "Дашборд", icon: LayoutDashboard },
  { href: "/contracts", label: "Контракты", icon: FileText },
  { href: "/analysis", label: "Анализ", icon: BarChart3 },
  { href: "/agents", label: "AI-агенты", icon: Bot },
  { href: "/workflow", label: "Согласование", icon: Workflow },
  { href: "/notifications", label: "Уведомления", icon: Bell },
  { href: "/archive", label: "Архив", icon: Archive },
  { href: "/settings", label: "Настройки", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

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

      <div className="px-4 pb-4">
        <Link
          href="/contracts"
          className="flex items-center justify-center gap-2 h-10 rounded-lg bg-primary text-on-primary text-sm font-medium hover:bg-primary-hover transition-colors"
        >
          <Plus size={18} />
          Новый контракт
        </Link>
      </div>

      <nav className="flex-1 px-4 space-y-1">
        {NAV.map(({ href, label, icon: Icon }) => {
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
