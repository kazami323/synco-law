"use client";

import { X } from "lucide-react";

export function Button({
  variant = "primary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger";
}) {
  const styles = {
    primary:
      "bg-primary text-on-primary hover:bg-primary-hover disabled:opacity-50",
    secondary:
      "border border-outline-variant text-primary bg-transparent hover:border-primary",
    danger:
      "border border-outline-variant text-error bg-transparent hover:border-error",
  }[variant];
  return (
    <button
      className={`h-10 px-4 rounded-lg text-sm font-medium transition-colors cursor-pointer disabled:cursor-not-allowed ${styles} ${className}`}
      {...props}
    />
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
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`bg-surface-container-lowest border border-outline-variant rounded-xl ${className}`}
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
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-on-surface/30 p-4">
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-xl border border-outline-variant">
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
}: {
  title: string;
  hint?: string;
}) {
  return (
    <div className="py-16 text-center">
      <p className="text-on-surface-variant font-medium">{title}</p>
      {hint && <p className="text-sm text-outline mt-1">{hint}</p>}
    </div>
  );
}
