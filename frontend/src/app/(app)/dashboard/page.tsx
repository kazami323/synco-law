"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  ArrowUpRight,
  CalendarClock,
  CheckCircle2,
  CircleCheck,
  FileSignature,
  FileText,
  ShieldAlert,
  TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import type { Analytics, ContractList, DashboardMetrics } from "@/lib/types";
import { ErrorNote, Skeleton, type Tone } from "@/components/ui";
import { RiskChip, StatusChip, TypeChip } from "@/components/contract-chips";
import { DocumentsBarChart, FlowLineChart } from "@/components/dashboard-charts";

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
  const analytics = useQuery({
    queryKey: ["dashboard-analytics"],
    queryFn: () => api<Analytics>("/api/dashboard/analytics?months=7"),
    enabled: allowed,
  });
  const contracts = useQuery({
    queryKey: ["contracts", "recent"],
    queryFn: () => api<ContractList>("/api/contracts/?limit=5"),
  });

  const m = metrics.data;
  const upcoming = m?.upcoming_deadlines ?? [];
  const firstName = user?.full_name?.split(" ")[0] ?? "";
  const loading = metrics.isLoading;
  // Отказ бэкенда нельзя рисовать нулями и надписью «всё чисто»: руководитель
  // юротдела примет пустой дашборд за отсутствие проблем (аудит, P1-13).
  const failed = metrics.isError;

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="text-2xl font-semibold">
          {greeting()}
          {firstName && `, ${firstName}`}
        </h1>
        <p className="mt-1 text-sm text-on-surface-variant">
          Сводка по договорам, рискам, подписям и ближайшим срокам.
        </p>
      </div>

      {/* Единая сетка: ячейки делят общие границы, без зазоров между карточками */}
      <div className="overflow-hidden rounded-xl border border-outline-variant bg-surface-container-lowest">
        {/* ── Ключевые показатели ── */}
        <div className="grid grid-cols-1 lg:grid-cols-4">
          <Kpi
            label="Договоров в работе"
            failed={failed}
            value={m?.in_work}
            loading={loading}
            icon={<FileText size={15} />}
            note={m ? `${signed(m.created_last_7d)} создано за 7 дней` : undefined}
            noteTone={m && m.created_last_7d > 0 ? "success" : "neutral"}
          />
          <Kpi
            label="Ждут согласования"
            failed={failed}
            value={m?.pending_approval}
            loading={loading}
            icon={<CheckCircle2 size={15} />}
            note={
              m
                ? m.pending_approval > 0
                  ? "требуют решения юриста"
                  : "очередь пуста"
                : undefined
            }
            noteTone={m && m.pending_approval > 0 ? "warning" : "neutral"}
          />
          <Kpi
            label="Подписано"
            failed={failed}
            value={m?.signed}
            loading={loading}
            icon={<FileSignature size={15} />}
            note={m ? `${signed(m.signed_last_7d)} за 7 дней` : undefined}
            noteTone={m && m.signed_last_7d > 0 ? "success" : "neutral"}
          />
          <Kpi
            label="Ближайшие сроки"
            failed={failed}
            value={m?.upcoming_deadlines_count}
            loading={loading}
            icon={<CalendarClock size={15} />}
            note={
              m
                ? m.overdue_deadlines_count > 0
                  ? `${m.overdue_deadlines_count} просрочено`
                  : "просрочек нет"
                : undefined
            }
            noteTone={m && m.overdue_deadlines_count > 0 ? "error" : "neutral"}
          />
        </div>

        {/* ── Графики ── */}
        <div className="grid grid-cols-1 border-t border-outline-variant divide-y divide-outline-variant lg:grid-cols-2 lg:divide-x lg:divide-y-0">
          <Panel
            title="Документы по месяцам"
            subtitle="Сколько договоров заводили, последние 7 месяцев."
          >
            {analytics.isLoading ? (
              <Skeleton className="h-[220px]" />
            ) : analytics.isError ? (
              <LoadFailed height="h-[220px]" />
            ) : (
              <DocumentsBarChart data={analytics.data?.months ?? []} />
            )}
          </Panel>

          <Panel
            title="Создано и подписано"
            subtitle="Сколько документов доходит до подписи."
          >
            {analytics.isLoading ? (
              <Skeleton className="h-[220px]" />
            ) : analytics.isError ? (
              <LoadFailed height="h-[220px]" />
            ) : (
              <FlowLineChart data={analytics.data?.months ?? []} />
            )}
          </Panel>
        </div>

        {/* ── Нижний ряд ── */}
        <div className="grid grid-cols-1 border-t border-outline-variant divide-y divide-outline-variant lg:grid-cols-4 lg:divide-x lg:divide-y-0">
          {/* Недавние договоры */}
          <div className="flex flex-col lg:col-span-2">
            <PanelHead
              title="Недавние договоры"
              subtitle="Последние документы и их состояние."
            />
            {contracts.isLoading ? (
              <div className="space-y-2 px-5 pb-5">
                <Skeleton className="h-11" />
                <Skeleton className="h-11" />
                <Skeleton className="h-11" />
              </div>
            ) : contracts.isError ? (
              <div className="flex-1 px-5 pb-5">
                <ErrorNote message="Не удалось загрузить договоры" />
              </div>
            ) : contracts.data?.items.length ? (
              <div className="flex-1 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-y border-outline-variant text-left text-[11px] uppercase tracking-wide text-on-surface-variant">
                      <th className="w-full px-5 py-2.5 font-semibold">Название</th>
                      <th className="whitespace-nowrap px-3 py-2.5 font-semibold">Тип</th>
                      <th className="whitespace-nowrap px-3 py-2.5 font-semibold">Риск</th>
                      <th className="whitespace-nowrap px-3 py-2.5 font-semibold">Статус</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-outline-variant">
                    {contracts.data.items.map((c) => (
                      <tr
                        key={c.id}
                        className="transition-colors hover:bg-surface-container-low"
                      >
                        <td className="max-w-0 px-5 py-3">
                          <Link
                            href={`/contracts/${c.id}`}
                            className="block truncate font-medium hover:text-primary"
                          >
                            {c.title}
                          </Link>
                        </td>
                        <td className="whitespace-nowrap px-3 py-3">
                          <TypeChip type={c.contract_type} />
                        </td>
                        <td className="whitespace-nowrap px-3 py-3">
                          <RiskChip score={c.risk_score} />
                        </td>
                        <td className="whitespace-nowrap px-3 py-3">
                          <StatusChip status={c.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="flex-1 px-5 py-10 text-center text-sm text-on-surface-variant">
                Договоров пока нет.
              </p>
            )}
            <Link
              href="/contracts"
              className="flex items-center justify-center gap-1.5 border-t border-outline-variant py-3 text-sm font-medium text-on-surface-variant transition-colors hover:bg-surface-container-low hover:text-primary"
            >
              Смотреть все <ArrowRight size={15} />
            </Link>
          </div>

          {/* Что требует внимания */}
          <AttentionPanel metrics={m} loading={loading} failed={failed} />

          {/* Ближайшие сроки */}
          <div className="flex flex-col">
            <PanelHead
              title="Ближайшие сроки"
              subtitle="Что наступает в ближайшую неделю."
            />
            {loading ? (
              <div className="space-y-2 px-5 pb-5">
                <Skeleton className="h-12" />
                <Skeleton className="h-12" />
              </div>
            ) : failed ? (
              <div className="flex-1 px-5 pb-5">
                <ErrorNote message="Не удалось загрузить сроки" />
              </div>
            ) : upcoming.length ? (
              <ul className="divide-y divide-outline-variant border-t border-outline-variant">
                {upcoming.slice(0, 4).map((item) => (
                  <li key={item.id}>
                    <Link
                      href={`/contracts/${item.contract_id}`}
                      className="flex items-start gap-3 px-5 py-3 transition-colors hover:bg-surface-container-low"
                    >
                      <span
                        className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${
                          item.days_left < 0
                            ? "bg-error/10 text-error"
                            : "bg-warning/10 text-warning"
                        }`}
                      >
                        <CalendarClock size={13} />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] font-medium">
                          {item.contract_title}
                        </span>
                        <span className="block text-xs text-outline">
                          {DEADLINE_LABELS[item.type] ?? item.type} ·{" "}
                          {deadlineText(item.days_left)}
                        </span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="flex-1 px-5 py-10 text-center text-sm text-on-surface-variant">
                Приближающихся сроков нет.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Плашка показателя. Подпись снизу — либо реальный прирост за 7 дней, либо
 * пояснение к числу. Процентов «к прошлой неделе» здесь нет намеренно:
 * сравнивать не с чем, а выдуманная динамика в отчёте руководителю юротдела
 * хуже её отсутствия.
 */
function Kpi({
  label,
  value,
  note,
  noteTone = "neutral",
  icon,
  loading,
  failed,
}: {
  label: string;
  value: number | undefined;
  note?: string;
  noteTone?: Tone;
  icon: React.ReactNode;
  loading: boolean;
  failed?: boolean;
}) {
  const noteColor = {
    success: "text-success",
    warning: "text-warning",
    error: "text-error",
    info: "text-primary",
    neutral: "text-on-surface-variant",
  }[noteTone];

  return (
    <div className="border-b border-outline-variant px-5 py-4 last:border-b-0
      lg:border-b-0 lg:border-r lg:last:border-r-0">
      <div className="flex items-center gap-2 text-[13px] text-on-surface-variant">
        <span className="text-outline">{icon}</span>
        {label}
      </div>
      <div className="mt-2 text-3xl font-semibold tabular-nums leading-none">
        {loading ? (
          <Skeleton className="h-8 w-14" />
        ) : failed ? (
          <span className="text-outline">—</span>
        ) : (
          (value ?? 0)
        )}
      </div>
      {failed && (
        <div className="mt-2.5 flex items-center gap-1 text-xs text-error">
          <TriangleAlert size={13} />
          Данные не загрузились
        </div>
      )}
      {!failed && note && (
        <div className={`mt-2.5 flex items-center gap-1 text-xs ${noteColor}`}>
          {noteTone === "success" && <ArrowUpRight size={13} />}
          {noteTone === "error" && <TriangleAlert size={13} />}
          {note}
        </div>
      )}
    </div>
  );
}

/** Аналог «Billing health»: либо список того, что горит, либо честное «всё чисто». */
function AttentionPanel({
  metrics,
  loading,
  failed,
}: {
  metrics: DashboardMetrics | undefined;
  loading: boolean;
  failed?: boolean;
}) {
  const issues = metrics
    ? [
        metrics.overdue_deadlines_count > 0 && {
          href: "/contracts",
          tone: "error" as const,
          label: `${metrics.overdue_deadlines_count} просроченных срока`,
          hint: "Сроки уже прошли",
        },
        metrics.high_risk > 0 && {
          href: "/analysis",
          tone: "error" as const,
          label: `${metrics.high_risk} с высоким риском`,
          hint: "Оценка выше 70 из 100",
        },
        metrics.pending_approval > 0 && {
          href: "/workflow",
          tone: "warning" as const,
          label: `${metrics.pending_approval} ждут согласования`,
          hint: "Очередь юридического отдела",
        },
      ].filter(Boolean as unknown as (v: unknown) => v is {
        href: string;
        tone: "error" | "warning";
        label: string;
        hint: string;
      })
    : [];

  return (
    <div className="flex flex-col">
      <PanelHead
        title="Требует внимания"
        subtitle={
          failed
            ? "Состояние неизвестно."
            : issues.length
              ? "Разберите это до конца дня."
              : "Ничего срочного нет."
        }
      />

      {loading ? (
        <div className="space-y-2 px-5 pb-5">
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
        </div>
      ) : failed ? (
        <div className="flex-1 px-5 pb-5">
          <ErrorNote message="Не удалось загрузить сводку. Обновите страницу." />
        </div>
      ) : issues.length ? (
        <ul className="divide-y divide-outline-variant border-t border-outline-variant">
          {issues.map((issue) => (
            <li key={issue.label}>
              <Link
                href={issue.href}
                className="flex items-start gap-3 px-5 py-3 transition-colors hover:bg-surface-container-low"
              >
                <span
                  className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${
                    issue.tone === "error"
                      ? "bg-error/10 text-error"
                      : "bg-warning/10 text-warning"
                  }`}
                >
                  {issue.tone === "error" ? (
                    <TriangleAlert size={13} />
                  ) : (
                    <ShieldAlert size={13} />
                  )}
                </span>
                <span className="min-w-0">
                  <span className="block text-[13px] font-medium">{issue.label}</span>
                  <span className="block text-xs text-outline">{issue.hint}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <div className="flex flex-1 flex-col items-center justify-center px-5 py-10 text-center">
          <span className="mb-3 flex h-11 w-11 items-center justify-center rounded-full border border-outline-variant text-success">
            <CircleCheck size={20} />
          </span>
          <p className="font-medium">Всё под контролем</p>
          <p className="mt-1.5 text-xs leading-relaxed text-on-surface-variant">
            Просроченных сроков нет, договоров с высоким риском в работе нет.
          </p>
        </div>
      )}
    </div>
  );
}

/** Место графика, когда данные не пришли: не пустая ось, а явный отказ. */
function LoadFailed({ height }: { height: string }) {
  return (
    <div
      className={`flex ${height} items-center justify-center rounded-lg border border-dashed border-outline-variant px-4 text-center text-sm text-on-surface-variant`}
    >
      Не удалось загрузить данные
    </div>
  );
}

function Panel({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-w-0 p-5">
      <h2 className="font-semibold">{title}</h2>
      <p className="mt-0.5 mb-3 text-[13px] text-on-surface-variant">{subtitle}</p>
      {children}
    </div>
  );
}

function PanelHead({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="px-5 py-4">
      <h2 className="font-semibold">{title}</h2>
      <p className="mt-0.5 text-[13px] text-on-surface-variant">{subtitle}</p>
    </div>
  );
}

function signed(value: number): string {
  return value > 0 ? `+${value}` : String(value);
}
