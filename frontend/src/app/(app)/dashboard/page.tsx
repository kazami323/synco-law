"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CalendarClock,
  CheckCircle2,
  Clock,
  FileCheck2,
  ShieldAlert,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import type { ContractList, DashboardMetrics } from "@/lib/types";
import { Card, Chip, EmptyState, Skeleton } from "@/components/ui";
import { RiskChip, StatusChip, TypeChip } from "@/components/contract-chips";

type Tint = "primary" | "warning" | "success" | "error";

const RING: Record<Tint, string> = {
  primary: "bg-primary-fixed text-primary",
  warning: "bg-warning/10 text-warning",
  success: "bg-success/10 text-success",
  error: "bg-error/10 text-error",
};

const HERO: {
  key: keyof DashboardMetrics;
  label: string;
  tint: Tint;
  icon: React.ComponentType<{ size?: number }>;
}[] = [
  { key: "total_reviewed", label: "Проверено договоров", tint: "primary", icon: FileCheck2 },
  { key: "pending_approval", label: "На согласовании", tint: "warning", icon: Clock },
  { key: "signed", label: "Подписано", tint: "success", icon: CheckCircle2 },
  { key: "upcoming_deadlines_count", label: "Ближайшие сроки", tint: "error", icon: CalendarClock },
];

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

function greeting() {
  const h = new Date().getHours();
  if (h < 6) return "Доброй ночи";
  if (h < 12) return "Доброе утро";
  if (h < 18) return "Добрый день";
  return "Добрый вечер";
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

  const m = metrics.data;
  const upcoming = m?.upcoming_deadlines ?? [];
  const firstName = user?.full_name?.split(" ")[0] ?? "";

  const riskTotal = (m?.high_risk ?? 0) + (m?.medium_risk ?? 0) + (m?.low_risk ?? 0);
  const riskSegments = [
    { label: "Высокий", n: m?.high_risk ?? 0, bar: "bg-error", dot: "bg-error" },
    { label: "Средний", n: m?.medium_risk ?? 0, bar: "bg-warning", dot: "bg-warning" },
    { label: "Низкий", n: m?.low_risk ?? 0, bar: "bg-success", dot: "bg-success" },
  ];

  return (
    <div className="max-w-6xl">
      <h1 className="text-2xl font-semibold">
        {greeting()}
        {firstName && `, ${firstName}`}
      </h1>
      <p className="mt-1 text-sm text-on-surface-variant">
        Сводка по контрактам, рискам, подписям и ближайшим срокам.
      </p>

      {/* ── Ключевые показатели ── */}
      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {HERO.map(({ key, label, tint, icon: Icon }) => (
          <Card key={key} className="p-5 transition-shadow hover:shadow-sm">
            <div className="flex items-center justify-between">
              <span className={`flex h-10 w-10 items-center justify-center rounded-xl ${RING[tint]}`}>
                <Icon size={20} />
              </span>
            </div>
            <div className="mt-3 text-3xl font-semibold tabular-nums">
              {metrics.isLoading ? (
                <Skeleton className="h-8 w-12" />
              ) : (
                ((m?.[key] as number) ?? 0)
              )}
            </div>
            <div className="mt-0.5 text-sm text-on-surface-variant">{label}</div>
          </Card>
        ))}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
        {/* ── Недавние контракты ── */}
        <Card className="overflow-hidden xl:col-span-2">
          <div className="flex items-center justify-between border-b border-outline-variant bg-surface-container-low px-6 py-4">
            <h2 className="font-semibold">Недавние контракты</h2>
            <Link href="/contracts" className="text-sm text-primary hover:underline">
              Смотреть все
            </Link>
          </div>
          {contracts.isLoading ? (
            <div className="space-y-3 p-6">
              {[0, 1, 2].map((item) => (
                <Skeleton key={item} className="h-14" />
              ))}
            </div>
          ) : contracts.data && contracts.data.items.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase text-on-surface-variant">
                    <th className="px-4 py-3 font-medium">Название</th>
                    <th className="px-4 py-3 font-medium">Тип</th>
                    <th className="px-4 py-3 font-medium">Риск</th>
                    <th className="px-4 py-3 font-medium">Статус</th>
                    <th className="px-4 py-3 font-medium">Дата</th>
                  </tr>
                </thead>
                <tbody>
                  {contracts.data.items.map((c) => (
                    <tr
                      key={c.id}
                      className="border-t border-outline-variant transition-colors hover:bg-surface-container-low"
                    >
                      <td className="px-4 py-3">
                        <Link
                          href={`/contracts/${c.id}`}
                          className="font-medium text-primary hover:underline"
                        >
                          {c.title}
                        </Link>
                      </td>
                      <td className="px-4 py-3">
                        <TypeChip type={c.contract_type} />
                      </td>
                      <td className="px-4 py-3">
                        <RiskChip score={c.risk_score} />
                      </td>
                      <td className="px-4 py-3">
                        <StatusChip status={c.status} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-on-surface-variant">
                        {new Date(c.created_at).toLocaleDateString("ru-RU")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="Контрактов пока нет"
              hint="Создайте первый контракт на странице «Контракты»"
            />
          )}
        </Card>

        {/* ── Правая колонка: риски + сроки ── */}
        <div className="space-y-6">
          <Card className="p-5">
            <div className="flex items-center gap-2">
              <ShieldAlert size={18} className="text-primary" />
              <h2 className="font-semibold">Распределение рисков</h2>
            </div>

            {metrics.isLoading ? (
              <Skeleton className="mt-4 h-3 w-full" />
            ) : riskTotal === 0 ? (
              <p className="mt-4 text-sm text-on-surface-variant">
                Пока нет оценённых договоров.
              </p>
            ) : (
              <>
                <div className="mt-4 flex h-2.5 gap-0.5 overflow-hidden rounded-full">
                  {riskSegments
                    .filter((s) => s.n > 0)
                    .map((s) => (
                      <span
                        key={s.label}
                        className={s.bar}
                        style={{ width: `${(s.n / riskTotal) * 100}%` }}
                        title={`${s.label}: ${s.n}`}
                      />
                    ))}
                </div>
                <div className="mt-4 space-y-2">
                  {riskSegments.map((s) => (
                    <div key={s.label} className="flex items-center justify-between text-sm">
                      <span className="flex items-center gap-2 text-on-surface-variant">
                        <span className={`h-2 w-2 rounded-full ${s.dot}`} />
                        {s.label} риск
                      </span>
                      <span className="font-semibold tabular-nums">{s.n}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </Card>

          <Card className="overflow-hidden">
            <div className="flex items-center justify-between border-b border-outline-variant px-5 py-4">
              <div className="flex items-center gap-2">
                <CalendarClock size={18} className="text-warning" />
                <h2 className="font-semibold">Предстоящие сроки</h2>
              </div>
              <span className="text-lg font-semibold tabular-nums text-error">
                {metrics.isLoading ? "…" : (m?.upcoming_deadlines_count ?? 0)}
              </span>
            </div>
            {metrics.isLoading ? (
              <div className="space-y-3 p-5">
                {[0, 1].map((item) => (
                  <Skeleton key={item} className="h-12" />
                ))}
              </div>
            ) : upcoming.length > 0 ? (
              <div className="divide-y divide-outline-variant">
                {upcoming.map((item) => (
                  <Link
                    key={item.id}
                    href={`/contracts/${item.contract_id}`}
                    className="block px-5 py-3.5 transition-colors hover:bg-surface-container-low"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium">
                          {item.contract_title}
                        </div>
                        <div className="mt-1 text-xs text-on-surface-variant">
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
              <p className="px-5 py-8 text-center text-sm text-on-surface-variant">
                Нет приближающихся сроков.
              </p>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
