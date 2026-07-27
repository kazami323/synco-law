import type { DocumentLabel } from "@/lib/types";

type Tone = "success" | "warning" | "error" | "info" | "neutral";

interface LabelSpec {
  title: string;
  tone: Tone;
  autoOnly: boolean;
}

/**
 * Зеркало backend/app/core/labels.py — состав плашек правится в обоих местах.
 * Бэкенд остаётся источником правды по правам (кто может ставить), здесь —
 * только оформление: название и цвет.
 */
export const LABELS: Record<string, LabelSpec> = {
  ai_reviewed: { title: "Проверено ИИ", tone: "info", autoOnly: true },
  prepared: {
    title: "Подготовлено младшим юристом",
    tone: "neutral",
    autoOnly: false,
  },
  approved: {
    title: "Утверждено старшим юристом",
    tone: "success",
    autoOnly: false,
  },
};

export const ROLE_TITLES: Record<string, string> = {
  admin: "администратор",
  head: "руководитель отдела",
  senior_lawyer: "старший юрист",
  lawyer: "юрист",
  compliance: "комплаенс",
  finance: "финансист",
  external: "внешний пользователь",
};

export function labelSpec(kind: string): LabelSpec {
  return LABELS[kind] ?? { title: kind, tone: "neutral", autoOnly: false };
}

/** Кто поставил плашку: «Иванов (старший юрист)» или «Риск-агент». */
export function labelActor(label: DocumentLabel): string {
  if (label.actor_type === "agent") return label.actor_name || "ИИ-агент";
  const role = label.actor_role ? ROLE_TITLES[label.actor_role] : null;
  const name = label.actor_name || "пользователь";
  return role ? `${name} (${role})` : name;
}
