"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import {
  Archive,
  BarChart3,
  Bell,
  Bot,
  CircleQuestionMark,
  CloudCheck,
  FileText,
  FolderKanban,
  LayoutDashboard,
  LayoutTemplate,
  Plus,
  Scale,
  Settings,
  Workflow,
  X,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";

// right: null — виден всем ролям
const NAV = [
  { href: "/dashboard", label: "Дашборд", icon: LayoutDashboard, right: "view_all" },
  { href: "/projects", label: "Проекты", icon: FolderKanban, right: null },
  { href: "/contracts", label: "Контракты", icon: FileText, right: null },
  { href: "/analysis", label: "Анализ", icon: BarChart3, right: "view_all" },
  { href: "/agents", label: "AI-агенты", icon: Bot, right: null },
  { href: "/templates", label: "Шаблоны", icon: LayoutTemplate, right: null },
  { href: "/workflow", label: "Согласование", icon: Workflow, right: null },
  { href: "/notifications", label: "Уведомления", icon: Bell, right: null },
  { href: "/archive", label: "Архив", icon: Archive, right: null },
  { href: "/settings", label: "Настройки", icon: Settings, right: null },
];

/**
 * Боковое меню: на десктопе свёрнуто в рейку с иконками и раскрывается по
 * наведению, на телефоне — выезжающая шторка.
 *
 * Раскрытие сделано целиком на CSS (`group-hover` + `group-focus-within`), без
 * состояния в React и без анимационной библиотеки: анимируются только ширина,
 * прозрачность и сдвиг. `focus-within` добавлен намеренно — иначе меню
 * недоступно с клавиатуры, а юристы часто ходят табом.
 *
 * Панель разворачивается ПОВЕРХ контента, а не раздвигает его: место под рейку
 * держит распорка постоянной ширины. Иначе случайное наведение переколбашивало
 * бы вёрстку всей страницы — на экране правовой проверки с тремя колонками это
 * особенно заметно.
 */
export function Sidebar({
  mobileOpen = false,
  onClose,
}: {
  mobileOpen?: boolean;
  onClose?: () => void;
}) {
  const pathname = usePathname();
  const { user } = useAuth();

  // На телефоне шторка закрывается после перехода по ссылке
  useEffect(() => {
    onClose?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  const items = NAV.filter((item) => item.right === null || can(user, item.right));

  return (
    <>
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-on-surface/30 lg:hidden animate-fade-in"
          onClick={onClose}
        />
      )}

      {/* Распорка держит место под рейку, чтобы контент не прыгал при
          наведении. Ширины (72px рейка / 264px панель) записаны классами
          целиком: Tailwind сканирует исходник статически и не увидел бы
          класс, собранный из переменной. */}
      <div className="hidden lg:block shrink-0 w-[72px]" aria-hidden />

      <aside
        className={`group fixed inset-y-0 left-0 z-50 flex flex-col
          border-r border-outline-variant bg-surface-container-low
          transition-[width,transform,box-shadow] duration-200 ease-out
          w-[264px] ${mobileOpen ? "translate-x-0" : "-translate-x-full"}
          lg:translate-x-0 lg:w-[72px] lg:hover:w-[264px] lg:focus-within:w-[264px]
          lg:hover:shadow-2xl lg:focus-within:shadow-2xl`}
      >
        {/* Логотип. В рейке остаётся только знак. */}
        <div className="flex items-center gap-3 h-16 shrink-0 px-4 overflow-hidden">
          <span className="w-10 h-10 shrink-0 rounded-lg bg-primary text-on-primary flex items-center justify-center">
            <Scale size={22} />
          </span>
          <Label className="min-w-0">
            <span className="block font-semibold leading-tight truncate">
              AI Legal Workspace
            </span>
            <span className="block text-xs text-on-surface-variant">Legal OS</span>
          </Label>
          <button
            onClick={onClose}
            aria-label="Закрыть меню"
            className="ml-auto shrink-0 w-9 h-9 rounded-lg flex items-center justify-center
              text-on-surface-variant hover:text-on-surface hover:bg-surface-container
              cursor-pointer lg:hidden"
          >
            <X size={18} />
          </button>
        </div>

        {can(user, "create") && (
          <div className="px-4 pb-3 shrink-0">
            <Link
              href="/contracts"
              className="flex items-center h-10 rounded-lg bg-primary text-on-primary
                text-sm font-medium hover:bg-primary-hover transition-colors overflow-hidden"
            >
              <span className="w-10 shrink-0 flex items-center justify-center">
                <Plus size={18} />
              </span>
              <Label className="pr-3 whitespace-nowrap">Новый контракт</Label>
            </Link>
          </div>
        )}

        <nav className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-4 space-y-1 pb-3">
          {items.map(({ href, label, icon: Icon }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`relative flex items-center h-10 rounded-lg text-sm
                  transition-colors overflow-hidden ${
                    active
                      ? "bg-secondary-container text-on-surface font-medium"
                      : "text-on-surface-variant hover:bg-surface-container hover:text-on-surface"
                  }`}
              >
                {/* Метка активного пункта читается и в свёрнутой рейке */}
                {active && (
                  <span
                    aria-hidden
                    className="absolute left-0 inset-y-1.5 w-0.5 rounded-full bg-primary"
                  />
                )}
                <span className="w-10 shrink-0 flex items-center justify-center">
                  <Icon size={18} />
                </span>
                <Label className="whitespace-nowrap pr-3">{label}</Label>
              </Link>
            );
          })}
        </nav>

        <div className="shrink-0 px-4 py-4 border-t border-outline-variant space-y-0.5">
          <div
            className="flex items-center h-9 text-sm text-on-surface-variant overflow-hidden"
          >
            <span className="w-10 shrink-0 flex items-center justify-center text-success">
              <CloudCheck size={18} />
            </span>
            <Label className="whitespace-nowrap">Система работает</Label>
          </div>
          <div
            className="flex items-center h-9 text-sm text-on-surface-variant overflow-hidden"
          >
            <span className="w-10 shrink-0 flex items-center justify-center">
              <CircleQuestionMark size={18} />
            </span>
            <Label className="whitespace-nowrap">Помощь</Label>
          </div>
        </div>
      </aside>
    </>
  );
}

/**
 * Подпись рядом с иконкой: на телефоне видна всегда, на десктопе появляется
 * при раскрытии рейки. Скрываем прозрачностью, а не display — иначе текст
 * дёргается вместо того, чтобы проявляться.
 */
function Label({
  className = "",
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={`transition-[opacity,transform] duration-200 ease-out
        lg:opacity-0 lg:-translate-x-1
        lg:group-hover:opacity-100 lg:group-hover:translate-x-0
        lg:group-focus-within:opacity-100 lg:group-focus-within:translate-x-0
        ${className}`}
    >
      {children}
    </span>
  );
}
