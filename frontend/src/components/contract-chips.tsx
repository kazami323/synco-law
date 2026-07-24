import {
  Briefcase,
  ClipboardCheck,
  FileText,
  Handshake,
  KeyRound,
  Lock,
  Scale,
  ShieldAlert,
  ShoppingCart,
  type LucideIcon,
} from "lucide-react";
import { Sparkles, UserCheck } from "lucide-react";
import { Chip } from "@/components/ui";
import { CONTRACT_TYPES, type DocumentLabel } from "@/lib/types";
import { labelActor, labelSpec } from "@/lib/labels";

const TYPE_ICONS: Record<string, LucideIcon> = {
  purchase: ShoppingCart,
  lease: KeyRound,
  service: Handshake,
  nda: Lock,
  employment: Briefcase,
  risk_map: ShieldAlert,
  legal_opinion: Scale,
  contract_review: ClipboardCheck,
  other: FileText,
};

/** Иконка типа договора в мягком квадрате — для списков и карточек. */
export function TypeIcon({
  type,
  size = 18,
  className = "",
}: {
  type: string | null;
  size?: number;
  className?: string;
}) {
  const Icon = (type && TYPE_ICONS[type]) || FileText;
  return (
    <span
      className={`flex items-center justify-center rounded-lg bg-primary-fixed text-primary ${className}`}
    >
      <Icon size={size} />
    </span>
  );
}

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
  if (score === null) return <Chip tone="neutral">Не оценен</Chip>;
  if (score > 70) return <Chip tone="error">Высокий</Chip>;
  if (score >= 40) return <Chip tone="warning">Средний</Chip>;
  return <Chip tone="success">Низкий</Chip>;
}

export function TypeChip({ type }: { type: string | null }) {
  return <Chip tone="neutral">{type ? CONTRACT_TYPES[type] ?? type : "—"}</Chip>;
}

/**
 * Плашки документа: «Проверено ИИ», «Подготовлено», «Утверждено».
 * В списках показываем компактно (без автора), в карточке — с автором.
 */
export function LabelChips({
  labels,
  compact = false,
}: {
  labels: DocumentLabel[] | undefined;
  compact?: boolean;
}) {
  if (!labels?.length) return null;
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {labels.map((label) => {
        const spec = labelSpec(label.kind);
        const Icon = label.actor_type === "agent" ? Sparkles : UserCheck;
        return (
          <Chip key={label.kind} tone={spec.tone}>
            <Icon size={12} />
            {spec.title}
            {!compact && (
              <span className="opacity-70">· {labelActor(label)}</span>
            )}
          </Chip>
        );
      })}
    </span>
  );
}
