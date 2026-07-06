"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  CircleAlert,
  CircleHelp,
  Table2,
  TriangleAlert,
} from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { CONTRACT_TYPES } from "@/lib/types";
import { Card, Skeleton } from "@/components/ui";

/* Палитра серий проверена валидатором dataviz (CVD ΔE 99, контраст ≥3:1) */
const SERIES = {
  created: { label: "Создано", color: "#005ea4" },
  signed: { label: "Подписано", color: "#b87700" },
};

interface Analytics {
  months: { month: string; created: number; signed: number }[];
  by_type: { type: string; count: number }[];
  top_counterparties: {
    counterparty: string;
    total_amount: number;
    count: number;
  }[];
  risk: { high: number; medium: number; low: number; unscored: number };
  totals: {
    contracts: number;
    signed_amount: number;
    avg_risk: number | null;
    in_work: number;
  };
}

const MONTH_LABELS = [
  "янв",
  "фев",
  "мар",
  "апр",
  "май",
  "июн",
  "июл",
  "авг",
  "сен",
  "окт",
  "ноя",
  "дек",
];

function monthLabel(key: string) {
  const [year, month] = key.split("-").map(Number);
  return `${MONTH_LABELS[month - 1]} ${String(year).slice(2)}`;
}

function formatAmount(value: number) {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)} млрд`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} млн`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)} тыс`;
  return String(Math.round(value));
}

export default function AnalysisPage() {
  const analytics = useQuery({
    queryKey: ["analytics"],
    queryFn: () => api<Analytics>("/api/dashboard/analytics?months=6"),
  });

  const d = analytics.data;

  return (
    <div className="max-w-6xl">
      <h1 className="text-2xl font-semibold">Аналитика</h1>
      <p className="text-on-surface-variant text-sm mt-1">
        Динамика договорной работы, структура портфеля и риски — сводка для
        руководителя.
      </p>

      {analytics.isLoading && (
        <div className="mt-6 space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
          <Skeleton className="h-72" />
          <div className="grid md:grid-cols-2 gap-6">
            <Skeleton className="h-64" />
            <Skeleton className="h-64" />
          </div>
        </div>
      )}

      {d && (
        <div className="mt-6 space-y-6">
          {/* KPI-плитки */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatTile label="Всего контрактов" value={String(d.totals.contracts)} />
            <StatTile
              label="Сумма подписанных"
              value={`${formatAmount(d.totals.signed_amount)} UZS`}
            />
            <StatTile label="В работе" value={String(d.totals.in_work)} />
            <StatTile
              label="Средний риск"
              value={d.totals.avg_risk !== null ? `${d.totals.avg_risk}` : "—"}
              hint="/100"
            />
          </div>

          {/* Динамика по месяцам */}
          <TrendCard months={d.months} />

          <div className="grid md:grid-cols-2 gap-6">
            {/* По типам */}
            <Card className="p-6">
              <h2 className="font-semibold">Контракты по типам</h2>
              <p className="text-xs text-on-surface-variant mt-0.5 mb-4">
                Количество за всё время
              </p>
              <HBars
                items={d.by_type.map((t) => ({
                  label: CONTRACT_TYPES[t.type] ?? t.type,
                  value: t.count,
                }))}
                format={(v) => String(v)}
              />
            </Card>

            {/* Топ контрагентов */}
            <Card className="p-6">
              <h2 className="font-semibold">Топ контрагентов</h2>
              <p className="text-xs text-on-surface-variant mt-0.5 mb-4">
                По сумме контрактов, UZS
              </p>
              {d.top_counterparties.length === 0 ? (
                <p className="text-sm text-on-surface-variant py-8 text-center">
                  Пока нет контрактов с контрагентами и суммами
                </p>
              ) : (
                <HBars
                  items={d.top_counterparties.map((c) => ({
                    label: c.counterparty,
                    value: c.total_amount,
                    sub: `${c.count} шт.`,
                  }))}
                  format={formatAmount}
                />
              )}
            </Card>
          </div>

          {/* Риски */}
          <RiskCard risk={d.risk} />
        </div>
      )}
    </div>
  );
}

function StatTile({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <Card className="p-4">
      <div className="text-[11px] font-semibold uppercase text-on-surface-variant">
        {label}
      </div>
      <div className="text-3xl font-semibold mt-2">
        {value}
        {hint && (
          <span className="text-sm text-on-surface-variant font-normal">
            {hint}
          </span>
        )}
      </div>
    </Card>
  );
}

/* Линейный график: 2 серии, кроссхейр + тултип, прямые подписи у концов линий */
function TrendCard({ months }: { months: Analytics["months"] }) {
  const [tableView, setTableView] = useState(false);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const W = 720;
  const H = 240;
  const PAD = { top: 16, right: 96, bottom: 28, left: 36 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  const maxValue = Math.max(
    1,
    ...months.map((m) => Math.max(m.created, m.signed))
  );
  const yMax = Math.ceil(maxValue * 1.15);
  const x = (i: number) =>
    PAD.left + (months.length > 1 ? (i * plotW) / (months.length - 1) : plotW / 2);
  const y = (v: number) => PAD.top + plotH - (v / yMax) * plotH;

  const path = (key: "created" | "signed") =>
    months.map((m, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(m[key])}`).join(" ");

  const yTicks = [0, Math.round(yMax / 2), yMax];

  return (
    <Card className="p-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="font-semibold">Динамика по месяцам</h2>
          <p className="text-xs text-on-surface-variant mt-0.5">
            Создано и подписано контрактов, последние 6 месяцев
          </p>
        </div>
        <div className="flex items-center gap-4">
          {/* Легенда */}
          {Object.values(SERIES).map((s) => (
            <span key={s.label} className="flex items-center gap-1.5 text-xs">
              <span
                className="w-3 h-0.5 rounded-full inline-block"
                style={{ background: s.color }}
              />
              {s.label}
            </span>
          ))}
          <button
            onClick={() => setTableView((v) => !v)}
            title="Таблица данных"
            className={`w-8 h-8 rounded-lg border flex items-center justify-center cursor-pointer ${
              tableView
                ? "border-primary text-primary"
                : "border-outline-variant text-on-surface-variant hover:border-primary"
            }`}
          >
            <Table2 size={15} />
          </button>
        </div>
      </div>

      {tableView ? (
        <table className="w-full text-sm mt-4">
          <thead>
            <tr className="text-left text-xs uppercase text-on-surface-variant border-b border-outline-variant">
              <th className="py-2">Месяц</th>
              <th className="py-2">Создано</th>
              <th className="py-2">Подписано</th>
            </tr>
          </thead>
          <tbody>
            {months.map((m) => (
              <tr key={m.month} className="border-b border-outline-variant last:border-0">
                <td className="py-2">{monthLabel(m.month)}</td>
                <td className="py-2">{m.created}</td>
                <td className="py-2">{m.signed}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="relative mt-4 overflow-x-auto">
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="w-full min-w-[560px]"
            onMouseLeave={() => setHoverIdx(null)}
          >
            {/* Сетка — приглушённая */}
            {yTicks.map((t) => (
              <g key={t}>
                <line
                  x1={PAD.left}
                  x2={W - PAD.right}
                  y1={y(t)}
                  y2={y(t)}
                  stroke="var(--color-outline-variant)"
                  strokeWidth="1"
                />
                <text
                  x={PAD.left - 8}
                  y={y(t) + 4}
                  textAnchor="end"
                  fontSize="11"
                  fill="var(--color-on-surface-variant)"
                >
                  {t}
                </text>
              </g>
            ))}
            {months.map((m, i) => (
              <text
                key={m.month}
                x={x(i)}
                y={H - 8}
                textAnchor="middle"
                fontSize="11"
                fill="var(--color-on-surface-variant)"
              >
                {monthLabel(m.month)}
              </text>
            ))}

            {/* Кроссхейр */}
            {hoverIdx !== null && (
              <line
                x1={x(hoverIdx)}
                x2={x(hoverIdx)}
                y1={PAD.top}
                y2={PAD.top + plotH}
                stroke="var(--color-outline)"
                strokeWidth="1"
                strokeDasharray="3 3"
              />
            )}

            {/* Линии серий, 2px */}
            {(Object.keys(SERIES) as ("created" | "signed")[]).map((key) => (
              <path
                key={key}
                d={path(key)}
                fill="none"
                stroke={SERIES[key].color}
                strokeWidth="2"
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            ))}

            {/* Точки при наведении: маркер ≥8px с белым кольцом */}
            {hoverIdx !== null &&
              (Object.keys(SERIES) as ("created" | "signed")[]).map((key) => (
                <circle
                  key={key}
                  cx={x(hoverIdx)}
                  cy={y(months[hoverIdx][key])}
                  r="4.5"
                  fill={SERIES[key].color}
                  stroke="var(--color-surface-container-lowest)"
                  strokeWidth="2"
                />
              ))}

            {/* Прямые подписи у концов линий */}
            {months.length > 0 &&
              (Object.keys(SERIES) as ("created" | "signed")[]).map((key) => (
                <text
                  key={key}
                  x={W - PAD.right + 8}
                  y={y(months[months.length - 1][key]) + 4}
                  fontSize="12"
                  fontWeight="600"
                  fill="var(--color-on-surface)"
                >
                  {SERIES[key].label}
                </text>
              ))}

            {/* Зоны наведения — шире маркеров */}
            {months.map((m, i) => (
              <rect
                key={m.month}
                x={x(i) - plotW / months.length / 2}
                y={PAD.top}
                width={plotW / months.length}
                height={plotH}
                fill="transparent"
                onMouseEnter={() => setHoverIdx(i)}
              />
            ))}
          </svg>

          {/* Тултип */}
          {hoverIdx !== null && (
            <div
              className="absolute pointer-events-none bg-surface-container-lowest border border-outline-variant rounded-lg shadow-lg px-3 py-2 text-xs"
              style={{
                left: `${(x(hoverIdx) / W) * 100}%`,
                top: 0,
                transform: "translateX(-50%)",
              }}
            >
              <div className="font-semibold mb-1">
                {monthLabel(months[hoverIdx].month)}
              </div>
              {(Object.keys(SERIES) as ("created" | "signed")[]).map((key) => (
                <div key={key} className="flex items-center gap-1.5">
                  <span
                    className="w-2 h-2 rounded-full inline-block"
                    style={{ background: SERIES[key].color }}
                  />
                  {SERIES[key].label}: {months[hoverIdx][key]}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

/* Горизонтальные бары: одна серия — один цвет, скруглён только конец данных */
function HBars({
  items,
  format,
}: {
  items: { label: string; value: number; sub?: string }[];
  format: (v: number) => string;
}) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div key={item.label} className="group">
          <div className="flex items-center justify-between text-sm mb-1">
            <span className="truncate">{item.label}</span>
            <span className="text-on-surface-variant text-xs shrink-0 ml-2">
              {format(item.value)}
              {item.sub ? ` · ${item.sub}` : ""}
            </span>
          </div>
          <div className="h-5 bg-surface-container rounded-r-md rounded-l-sm">
            <div
              className="h-full rounded-r-md rounded-l-sm transition-all group-hover:opacity-80"
              style={{
                width: `${(item.value / max) * 100}%`,
                background: SERIES.created.color,
                minWidth: item.value > 0 ? "6px" : 0,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

/* Риски — статусные цвета LexOS, всегда с иконкой и подписью */
function RiskCard({ risk }: { risk: Analytics["risk"] }) {
  const segments = [
    {
      key: "high",
      label: "Высокий",
      value: risk.high,
      color: "var(--color-error)",
      icon: TriangleAlert,
    },
    {
      key: "medium",
      label: "Средний",
      value: risk.medium,
      color: "var(--color-warning)",
      icon: CircleAlert,
    },
    {
      key: "low",
      label: "Низкий",
      value: risk.low,
      color: "var(--color-success)",
      icon: CheckCircle2,
    },
    {
      key: "unscored",
      label: "Не оценён",
      value: risk.unscored,
      color: "var(--color-outline)",
      icon: CircleHelp,
    },
  ];
  const total = segments.reduce((sum, s) => sum + s.value, 0);

  return (
    <Card className="p-6">
      <h2 className="font-semibold">Распределение рисков</h2>
      <p className="text-xs text-on-surface-variant mt-0.5 mb-4">
        Оценка Risk Agent по всем контрактам
      </p>
      {total === 0 ? (
        <p className="text-sm text-on-surface-variant py-4 text-center">
          Контрактов пока нет
        </p>
      ) : (
        <>
          {/* Стек с 2px зазорами */}
          <div className="flex h-6 rounded-md overflow-hidden gap-0.5 bg-surface-container-lowest">
            {segments
              .filter((s) => s.value > 0)
              .map((s) => (
                <div
                  key={s.key}
                  title={`${s.label}: ${s.value}`}
                  className="h-full first:rounded-l-md last:rounded-r-md"
                  style={{
                    width: `${(s.value / total) * 100}%`,
                    background: s.color,
                    minWidth: "8px",
                  }}
                />
              ))}
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-2 mt-4">
            {segments.map(({ key, label, value, color, icon: Icon }) => (
              <span key={key} className="flex items-center gap-1.5 text-sm">
                <Icon size={15} style={{ color }} />
                {label}:{" "}
                <span className="font-semibold">{value}</span>
              </span>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}
