"use client";

import { ChevronDown, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <svg
      className={`animate-spin ${className}`}
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <circle
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeOpacity="0.25"
        strokeWidth="4"
      />
      <path
        d="M22 12a10 10 0 0 0-10-10"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
      />
    </svg>
  );
}

/**
 * Кнопка раскладывает содержимое во flex с зазором — иконку можно ставить
 * рядом с текстом без обёртки. Фокус виден с клавиатуры: юристы работают
 * с длинными формами и часто ходят табом.
 */
export function Button({
  variant = "primary",
  size = "md",
  className = "",
  loading = false,
  disabled,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md";
  loading?: boolean;
}) {
  const styles = {
    primary:
      "bg-primary text-on-primary shadow-sm hover:bg-primary-hover hover:shadow disabled:opacity-50 disabled:shadow-none",
    secondary:
      "border border-outline-variant text-primary bg-surface-container-lowest hover:border-primary hover:bg-primary-fixed/40",
    danger:
      "border border-outline-variant text-error bg-surface-container-lowest hover:border-error hover:bg-error-container/50",
    ghost:
      "text-on-surface-variant hover:text-on-surface hover:bg-surface-container",
  }[variant];
  const sizing = size === "sm" ? "h-8 px-3 text-[13px]" : "h-10 px-4 text-sm";
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-lg font-medium
        transition-[background-color,border-color,box-shadow,transform] duration-150
        cursor-pointer select-none whitespace-nowrap
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-1 focus-visible:ring-offset-surface
        disabled:cursor-not-allowed disabled:opacity-50 active:scale-[0.98]
        ${sizing} ${styles} ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Spinner />}
      {children}
    </button>
  );
}

/**
 * Кнопка разрушающего действия с подтверждением на месте.
 *
 * Архивация шаблона и удаление участника проекта срабатывали с одного клика,
 * причём кнопка стоит вплотную к «Верифицировать» и к списку людей. Отдельное
 * модальное окно здесь мешало бы больше, чем помогало: подтверждение
 * раскрывается прямо в строке.
 */
export function ConfirmButton({
  onConfirm,
  confirmLabel = "Точно?",
  children,
  variant = "ghost",
  size = "sm",
  className = "",
  disabled,
  loading,
  title,
}: {
  onConfirm: () => void;
  confirmLabel?: string;
  children: React.ReactNode;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md";
  className?: string;
  disabled?: boolean;
  loading?: boolean;
  title?: string;
}) {
  const [armed, setArmed] = useState(false);

  if (!armed)
    return (
      <Button
        variant={variant}
        size={size}
        className={className}
        disabled={disabled}
        loading={loading}
        title={title}
        onClick={() => setArmed(true)}
      >
        {children}
      </Button>
    );

  return (
    <span className="inline-flex items-center gap-1">
      <Button
        variant="danger"
        size={size}
        disabled={disabled}
        loading={loading}
        onClick={() => {
          setArmed(false);
          onConfirm();
        }}
      >
        {confirmLabel}
      </Button>
      <Button variant="ghost" size={size} onClick={() => setArmed(false)}>
        Отмена
      </Button>
    </span>
  );
}

/** Иконочная кнопка одинакового размера — для панелей действий. */
export function IconButton({
  label,
  className = "",
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      title={label}
      aria-label={label}
      className={`w-9 h-9 shrink-0 inline-flex items-center justify-center rounded-lg
        text-on-surface-variant transition-colors cursor-pointer
        hover:text-primary hover:bg-surface-container
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40
        disabled:opacity-40 disabled:cursor-not-allowed ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div className={`rounded-lg bg-surface-container animate-pulse ${className}`} />
  );
}

export function Input({
  label,
  className = "",
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { label?: string }) {
  return (
    <label className="block">
      {label && (
        <span className="block text-[13px] font-semibold mb-1.5">{label}</span>
      )}
      <input
        className={`w-full h-10 px-3 rounded-lg border border-outline-variant bg-surface-container-lowest text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary-fixed placeholder:text-outline ${className}`}
        {...props}
      />
    </label>
  );
}

export function Select({
  label,
  className = "",
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement> & { label?: string }) {
  return (
    <label className="block">
      {label && (
        <span className="block text-[13px] font-semibold mb-1.5">{label}</span>
      )}
      <select
        className={`w-full h-10 px-3 rounded-lg border border-outline-variant bg-surface-container-lowest text-sm outline-none focus:border-primary ${className}`}
        {...props}
      >
        {children}
      </select>
    </label>
  );
}

export function Card({
  className = "",
  interactive = false,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { interactive?: boolean }) {
  return (
    <div
      className={`bg-surface-container-lowest border border-outline-variant rounded-xl ${
        interactive
          ? "transition-[border-color,box-shadow] duration-150 hover:border-primary/50 hover:shadow-sm"
          : ""
      } ${className}`}
      {...props}
    />
  );
}

/* Статус-чип «soft fill»: фон 10% семантического цвета, текст 100% */
export function Chip({
  tone,
  children,
}: {
  tone: "success" | "warning" | "error" | "info" | "neutral";
  children: React.ReactNode;
}) {
  const styles = {
    success: "bg-success/10 text-success",
    warning: "bg-warning/10 text-warning",
    error: "bg-error/10 text-error",
    info: "bg-primary/10 text-primary",
    neutral: "bg-secondary-container text-on-secondary-container",
  }[tone];
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap ${styles}`}
    >
      {children}
    </span>
  );
}

export function Modal({
  title,
  onClose,
  size = "md",
  children,
}: {
  title: string;
  onClose: () => void;
  size?: "md" | "lg" | "xl";
  children: React.ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-on-surface/30 p-4 animate-fade-in"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        className={`w-full ${
          { md: "max-w-md", lg: "max-w-2xl", xl: "max-w-4xl" }[size]
        } max-h-[90vh] overflow-y-auto bg-surface-container-lowest rounded-xl shadow-xl border border-outline-variant animate-modal-pop`}
      >
        <div className="flex items-center justify-between px-6 pt-5 pb-3">
          <h3 className="text-lg font-semibold">{title}</h3>
          <button
            onClick={onClose}
            className="text-on-surface-variant hover:text-on-surface cursor-pointer"
            aria-label="Закрыть"
          >
            <X size={20} />
          </button>
        </div>
        <div className="px-6 pb-6">{children}</div>
      </div>
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="rounded-lg bg-error-container text-error text-sm px-3 py-2">
      {message}
    </div>
  );
}

export function EmptyState({
  title,
  hint,
  action,
  icon,
}: {
  title: string;
  hint?: string;
  action?: React.ReactNode;
  icon?: React.ReactNode;
}) {
  return (
    <div className="py-14 px-6 text-center animate-fade-in-up">
      {icon && (
        <div className="w-12 h-12 mx-auto mb-3 rounded-xl bg-surface-container flex items-center justify-center text-outline">
          {icon}
        </div>
      )}
      <p className="text-on-surface font-medium">{title}</p>
      {hint && (
        <p className="text-sm text-on-surface-variant mt-1.5 max-w-md mx-auto leading-relaxed">
          {hint}
        </p>
      )}
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </div>
  );
}


export type Tone = "success" | "warning" | "error" | "info" | "neutral";

const TONE_TEXT: Record<Tone, string> = {
  success: "text-success",
  warning: "text-warning",
  error: "text-error",
  info: "text-primary",
  neutral: "text-on-surface-variant",
};

const TONE_BG: Record<Tone, string> = {
  success: "bg-success",
  warning: "bg-warning",
  error: "bg-error",
  info: "bg-primary",
  neutral: "bg-outline-variant",
};

/**
 * Сегментированные вкладки. Активный сегмент подсвечивается «плашкой», которая
 * едет за выбором — так видно, что экран один, а не четыре разных.
 */
export function Tabs<T extends string>({
  items,
  value,
  onChange,
  className = "",
}: {
  items: Array<{ value: T; label: string; count?: number | null; tone?: Tone }>;
  value: T;
  onChange: (value: T) => void;
  className?: string;
}) {
  return (
    <div
      role="tablist"
      className={`inline-flex items-center gap-1 p-1 rounded-xl bg-surface-container-low border border-outline-variant ${className}`}
    >
      {items.map((item) => {
        const active = item.value === value;
        return (
          <button
            key={item.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(item.value)}
            className={`inline-flex items-center gap-2 px-3 h-9 rounded-lg text-sm font-medium
              transition-[background-color,color,box-shadow] duration-150 cursor-pointer whitespace-nowrap
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 ${
                active
                  ? "bg-surface-container-lowest text-on-surface shadow-sm"
                  : "text-on-surface-variant hover:text-on-surface"
              }`}
          >
            {item.label}
            {item.count != null && item.count > 0 && (
              <span
                className={`min-w-5 h-5 px-1.5 inline-flex items-center justify-center rounded-full text-[11px] font-semibold tabular-nums ${
                  item.tone && item.tone !== "neutral"
                    ? `${TONE_BG[item.tone]}/12 ${TONE_TEXT[item.tone]}`
                    : "bg-surface-container text-on-surface-variant"
                }`}
              >
                {item.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/**
 * Полоса прогресса из сегментов: юристу важно не одно число, а из чего оно
 * сложилось — что подтверждено, что переписано, что отложено.
 */
export function SegmentedProgress({
  total,
  segments,
  className = "",
}: {
  total: number;
  segments: Array<{ value: number; tone: Tone; label: string }>;
  className?: string;
}) {
  const safeTotal = Math.max(total, 1);
  return (
    <div
      className={`h-2 w-full rounded-full bg-surface-container overflow-hidden flex ${className}`}
    >
      {segments
        .filter((segment) => segment.value > 0)
        .map((segment) => (
          <span
            key={segment.label}
            title={`${segment.label}: ${segment.value}`}
            className={`h-full transition-[width] duration-500 ease-out ${TONE_BG[segment.tone]}`}
            style={{ width: `${(segment.value / safeTotal) * 100}%` }}
          />
        ))}
    </div>
  );
}

/** Компактная метрика для полосы сводки. */
export function Metric({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: Tone;
}) {
  return (
    <div className="min-w-0 px-4 py-3 first:pl-0 last:pr-0">
      <div className={`text-xl font-semibold tabular-nums ${TONE_TEXT[tone]}`}>
        {value}
      </div>
      <div className="text-[13px] text-on-surface-variant truncate">{label}</div>
      {hint && <div className="text-xs text-outline truncate mt-0.5">{hint}</div>}
    </div>
  );
}

/** Строка метрик с разделителями. */
export function MetricRow({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap divide-x divide-outline-variant">{children}</div>
  );
}

/** Точка-индикатор состояния: читается быстрее слова. */
export function Dot({ tone, className = "" }: { tone: Tone; className?: string }) {
  return (
    <span
      aria-hidden
      className={`inline-block w-2 h-2 rounded-full shrink-0 ${TONE_BG[tone]} ${className}`}
    />
  );
}

/**
 * Подсказка на CSS, без библиотек: наведение и фокус с клавиатуры.
 */
export function Tooltip({
  text,
  children,
  side = "top",
}: {
  text: string;
  children: React.ReactNode;
  side?: "top" | "bottom";
}) {
  const position =
    side === "top"
      ? "bottom-full mb-2 origin-bottom"
      : "top-full mt-2 origin-top";
  return (
    <span className="relative inline-flex group">
      {children}
      <span
        role="tooltip"
        className={`pointer-events-none absolute left-1/2 -translate-x-1/2 ${position}
          z-30 whitespace-nowrap rounded-lg px-2.5 py-1.5 text-xs font-medium
          bg-on-surface text-surface shadow-lg
          opacity-0 scale-95 transition-[opacity,transform] duration-150
          group-hover:opacity-100 group-hover:scale-100
          group-focus-within:opacity-100 group-focus-within:scale-100`}
      >
        {text}
      </span>
    </span>
  );
}

/**
 * Сворачиваемая секция. Нужна там, где панель важна раз в сессию (запуск
 * проверки) и мешает всё остальное время.
 */
export function Disclosure({
  title,
  subtitle,
  defaultOpen = false,
  right,
  children,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  defaultOpen?: boolean;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-xl border border-outline-variant bg-surface-container-lowest overflow-hidden">
      <div className="flex items-center gap-3 px-4 py-3">
        <button
          onClick={() => setOpen((current) => !current)}
          aria-expanded={open}
          className="flex-1 min-w-0 flex items-center gap-2 text-left cursor-pointer group"
        >
          <ChevronDown
            size={16}
            className={`shrink-0 text-on-surface-variant transition-transform duration-200 ${
              open ? "rotate-0" : "-rotate-90"
            }`}
          />
          <span className="min-w-0">
            <span className="block text-sm font-semibold truncate group-hover:text-primary transition-colors">
              {title}
            </span>
            {subtitle && (
              <span className="block text-xs text-on-surface-variant truncate">
                {subtitle}
              </span>
            )}
          </span>
        </button>
        {right}
      </div>
      {open && (
        <div className="px-4 pb-4 animate-fade-in-up">{children}</div>
      )}
    </div>
  );
}


/**
 * Выпадающее меню для второстепенных действий. Своё, а не из библиотеки:
 * проекту нужен один компонент, а не дерево зависимостей Radix.
 */
export function Menu({
  label,
  icon,
  items,
  align = "right",
}: {
  label: string;
  icon?: React.ReactNode;
  align?: "left" | "right";
  items: Array<{
    label: string;
    icon?: React.ReactNode;
    onClick: () => void;
    danger?: boolean;
    disabled?: boolean;
  }>;
}) {
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (!boxRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="relative" ref={boxRef}>
      <Button
        variant="secondary"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        {icon}
        {label}
        <ChevronDown
          size={15}
          className={`transition-transform duration-150 ${open ? "rotate-180" : ""}`}
        />
      </Button>

      {open && (
        <div
          role="menu"
          className={`absolute z-40 mt-1.5 min-w-56 p-1 rounded-xl border border-outline-variant
            bg-surface-container-lowest shadow-lg animate-modal-pop
            ${align === "right" ? "right-0" : "left-0"}`}
        >
          {items.map((item) => (
            <button
              key={item.label}
              role="menuitem"
              disabled={item.disabled}
              onClick={() => {
                setOpen(false);
                item.onClick();
              }}
              className={`w-full flex items-center gap-2.5 px-3 h-9 rounded-lg text-sm text-left
                transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed
                ${
                  item.danger
                    ? "text-error hover:bg-error-container/60"
                    : "text-on-surface hover:bg-surface-container"
                }`}
            >
              <span className="shrink-0 text-on-surface-variant">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
