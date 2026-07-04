import { Chip } from "@/components/ui";
import { CONTRACT_TYPES } from "@/lib/types";

export const STATUS_LABELS: Record<
  string,
  { label: string; tone: "success" | "warning" | "error" | "info" | "neutral" }
> = {
  draft: { label: "Черновик", tone: "neutral" },
  analyzing: { label: "На проверке", tone: "info" },
  analyzed: { label: "Проверен", tone: "info" },
  approved: { label: "Согласован", tone: "success" },
  approved_finance: { label: "Согласован (финансы)", tone: "success" },
  ready_to_sign: { label: "К подписанию", tone: "warning" },
  signed: { label: "Подписан", tone: "success" },
  archived: { label: "В архиве", tone: "neutral" },
};

export function StatusChip({ status }: { status: string }) {
  const st = STATUS_LABELS[status] ?? { label: status, tone: "neutral" as const };
  return <Chip tone={st.tone}>{st.label}</Chip>;
}

export function RiskChip({ score }: { score: number | null }) {
  if (score === null) return <Chip tone="neutral">Не оценён</Chip>;
  if (score > 70) return <Chip tone="error">● Высокий</Chip>;
  if (score >= 40) return <Chip tone="warning">● Средний</Chip>;
  return <Chip tone="success">● Низкий</Chip>;
}

export function TypeChip({ type }: { type: string | null }) {
  return <Chip tone="neutral">{type ? CONTRACT_TYPES[type] ?? type : "—"}</Chip>;
}
