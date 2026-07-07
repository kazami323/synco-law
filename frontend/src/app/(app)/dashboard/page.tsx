"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CalendarClock,
  CheckCircle2,
  CircleAlert,
  TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import type { ContractList, DashboardMetrics } from "@/lib/types";
import { Card, Chip, EmptyState } from "@/components/ui";
import { RiskChip, StatusChip, TypeChip } from "@/components/contract-chips";

type NumericMetricKey =
  | "total_reviewed"
  | "high_risk"
  | "medium_risk"
  | "low_risk"
  | "pending_approval"
  | "signed"
  | "upcoming_deadlines_count";

const KPI: {
  key: NumericMetricKey;
  label: string;
  tone: "neutral" | "error" | "warning" | "success" | "info";
  icon?: React.ComponentType<{ size?: number; className?: string }>;
}[] = [
  { key: "total_reviewed", label: "Проверено", tone: "neutral" },
  { key: "high_risk", label: "Высокий риск", tone: "error", icon: TriangleAlert },
  { key: "medium_risk", label: "Средний риск", tone: "warning", icon: CircleAlert },
  { key: "low_risk", label: "Низкий риск", tone: "success", icon: CheckCircle2 },
  { key: "pending_approval", label: "На согласовании", tone: "neutral" },
  { key: "signed", label: "Подписано", tone: "success" },
  {
    key: "upcoming_deadlines_count",
    label: "Сроки 7 дней",
    tone: "error",
    icon: CalendarClock,
  },
];

const TONE_TEXT = {
  neutral: "text-on-surface",
  error: "text-error",
  warning: "text-warning",
  success: "text-success",
  info: "text-primary",
};

const DEADLINE_LABELS: Record<string, string> = {
  payment: "Оплата",
  delivery: "Поставка",
  report: "Отчет",
  other: "Другое",
};

function deadlineText(daysLeft: number) {
  if (daysLeft < 0) return `Просрочено на ${Math.abs(daysLeft)} дн.`;
  if (daysLeft === 0) return "Сегодня";
  return `${daysLeft} дн.`;
}

function formatDateOnly(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("ru-RU");
}

export default function DashboardPage() {
  const { user } = useAuth();
  const router = useRouter();
  const allowed = can(user, "view_all");

  // Дашборд — для ролей с обзором всей организации; юристов ведём в контракты
  useEffect(() => {
    if (user && !allowed) router.replace("/contracts");
  }, [user, allowed, router]);

  const metrics = useQuery({
    queryKey: ["dashboard-metrics"],
    queryFn: () => api<DashboardMetrics>("/api/dashboard/metrics"),
    enabled: allowed,
  });
  const contracts = useQuery({
    queryKey: ["contracts", "recent"],
    queryFn: () => api<ContractList>("/api/contracts/?limit=5"),
  });

  const upcoming = metrics.data?.upcoming_deadlines ?? [];

  return (
    <div className="max-w-6xl">
      <h1 className="text-2xl font-semibold">Обзор панелей</h1>
      <p className="text-on-surface-variant text-sm mt-1">
        Сводка по контрактам, рискам, подписям и ближайшим срокам.
      </p>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-7 gap-4 mt-6">
        {KPI.map(({ key, label, tone, icon: Icon }) => (
          <Card key={key} className="p-4">
            <div
              className={`flex items-center gap-1.5 text-[11px] font-semibold uppercase ${TONE_TEXT[tone]}`}
            >
              {Icon && <Icon size={14} />}
              {label}
            </div>
            <div className={`text-3xl font-semibold mt-2 ${TONE_TEXT[tone]}`}>
              {metrics.isLoading ? "…" : (metrics.data?.[key] ?? 0)}
            </div>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 mt-6">
        <Card className="xl:col-span-2 overflow-hidden">
          <div className="flex items-center justify-between px-6 py-4 bg-surface-container-low border-b border-outline-variant">
            <h2 className="font-semibold">Недавние контракты</h2>
            <Link href="/contracts" className="text-sm text-primary hover:underline">
              Смотреть все
            </Link>
          </div>
          {contracts.isLoading ? (
            <div className="p-6 space-y-3">
              {[0, 1, 2].map((item) => (
                <div
                  key={item}
                  className="h-14 rounded-lg bg-surface-container animate-pulse"
                />
              ))}
            </div>
          ) : contracts.data && contracts.data.items.length > 0 ? (
            <div className="overflow-x-auto"><table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase text-on-surface-variant">
                  <th className="px-6 py-3">Название</th>
                  <th className="px-6 py-3">Тип</th>
                  <th className="px-6 py-3">Риск</th>
                  <th className="px-6 py-3">Статус</th>
                  <th className="px-6 py-3">Дата</th>
                </tr>
              </thead>
              <tbody>
                {contracts.data.items.map((c) => (
                  <tr key={c.id} className="border-t border-outline-variant">
                    <td className="px-6 py-3">
                      <Link
                        href={`/contracts/${c.id}`}
                        className="text-primary font-medium hover:underline"
                      >
                        {c.title}
                      </Link>
                    </td>
                    <td className="px-6 py-3">
                      <TypeChip type={c.contract_type} />
                    </td>
                    <td className="px-6 py-3">
                      <RiskChip score={c.risk_score} />
                    </td>
                    <td className="px-6 py-3">
                      <StatusChip status={c.status} />
                    </td>
                    <td className="px-6 py-3">
                      {new Date(c.created_at).toLocaleDateString("ru-RU")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          ) : (
            <EmptyState
              title="Контрактов пока нет"
              hint="Создайте первый контракт на странице «Контракты»"
            />
          )}
        </Card>

        <Card className="bg-warning-container/30 border-warning/30 overflow-hidden">
          <div className="flex items-center justify-between gap-3 px-6 py-4 border-b border-warning/20">
            <div className="flex items-center gap-2">
              <CalendarClock size={18} className="text-warning" />
              <h2 className="font-semibold">Предстоящие сроки</h2>
            </div>
            <div className="text-2xl font-semibold text-error">
              {metrics.isLoading ? "…" : (metrics.data?.upcoming_deadlines_count ?? 0)}
            </div>
          </div>
          {metrics.isLoading ? (
            <div className="p-6 space-y-3">
              {[0, 1, 2].map((item) => (
                <div
                  key={item}
                  className="h-14 rounded-lg bg-surface-container animate-pulse"
                />
              ))}
            </div>
          ) : upcoming.length > 0 ? (
            <div className="divide-y divide-warning/20">
              {upcoming.map((item) => (
                <Link
                  key={item.id}
                  href={`/contracts/${item.contract_id}`}
                  className="block px-6 py-4 hover:bg-warning-container/40"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="font-medium text-sm truncate">
                        {item.contract_title}
                      </div>
                      <div className="text-xs text-on-surface-variant mt-1">
                        {DEADLINE_LABELS[item.type] ?? item.type} ·{" "}
                        {formatDateOnly(item.deadline_date)}
                      </div>
                    </div>
                    <Chip tone={item.days_left < 7 ? "error" : "neutral"}>
                      {deadlineText(item.days_left)}
                    </Chip>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="px-6 py-8 text-sm text-on-surface-variant">
              Нет приближающихся сроков.
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
