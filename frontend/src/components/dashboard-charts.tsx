"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

/**
 * Графики дашборда.
 *
 * Цвета берутся из токенов LexOS (--color-chart-1/2) прямо в SVG: так серии
 * сами переключаются вместе с темой. Пара проверена валидатором палитры на
 * обеих поверхностях — ΔE 24.9 на светлой и 24.5 на тёмной при пороге 8.
 */

const MONTHS_SHORT = [
  "янв", "фев", "мар", "апр", "май", "июн",
  "июл", "авг", "сен", "окт", "ноя", "дек",
];

export function monthLabel(key: string): string {
  const [, month] = key.split("-").map(Number);
  return MONTHS_SHORT[(month ?? 1) - 1] ?? key;
}

const AXIS = {
  stroke: "var(--color-outline-variant)",
  fontSize: 11,
  tickLine: false,
  axisLine: false,
} as const;

/** Подпись оси: цвет — токен текста, а не цвет серии. */
const TICK = { fill: "var(--color-on-surface-variant)", fontSize: 11 };

interface Point {
  month: string;
  created: number;
  signed: number;
}

/** Всплывающая подсказка на токенах — штатная у recharts белая и ломается в тёмной теме. */
function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ name?: string; value?: number; color?: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-outline-variant bg-surface-container-lowest px-3 py-2 shadow-lg">
      <p className="text-xs font-semibold text-on-surface">{label}</p>
      <ul className="mt-1 space-y-0.5">
        {payload.map((item) => (
          <li
            key={item.name}
            className="flex items-center gap-2 text-xs text-on-surface-variant"
          >
            <span
              aria-hidden
              className="inline-block h-2 w-2 shrink-0 rounded-full"
              style={{ background: item.color }}
            />
            {item.name}
            <span className="ml-auto font-semibold tabular-nums text-on-surface">
              {item.value}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Сколько документов заводили по месяцам. Одна серия — легенда не нужна,
 *  её роль выполняет заголовок карточки. */
export function DocumentsBarChart({ data }: { data: Point[] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: -24 }}>
        <defs>
          <linearGradient id="barCreated" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-chart-1)" stopOpacity={0.95} />
            <stop offset="100%" stopColor="var(--color-chart-1)" stopOpacity={0.45} />
          </linearGradient>
        </defs>
        <CartesianGrid
          vertical={false}
          stroke="var(--color-outline-variant)"
          strokeOpacity={0.5}
        />
        <XAxis dataKey="month" tickFormatter={monthLabel} tick={TICK} {...AXIS} />
        <YAxis width={44} allowDecimals={false} tick={TICK} {...AXIS} />
        <Tooltip
          content={<ChartTooltip />}
          labelFormatter={(label) => monthLabel(String(label ?? ""))}
          cursor={{ fill: "var(--color-surface-container)", opacity: 0.5 }}
        />
        <Bar
          dataKey="created"
          name="Создано"
          fill="url(#barCreated)"
          radius={[4, 4, 0, 0]}
          maxBarSize={44}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

/**
 * Легенда своя: recharts 3 выстраивает штатную по порядку отрисовки, а не
 * объявления, и «Подписано» оказывалось перед «Создано». Порядок серий должен
 * быть закреплён — цвет закреплён за сущностью, а не за местом в списке.
 */
function SeriesLegend() {
  const series = [
    { label: "Создано", color: "var(--color-chart-1)" },
    { label: "Подписано", color: "var(--color-chart-2)" },
  ];
  return (
    <ul className="flex items-center gap-4 pl-11">
      {series.map((item) => (
        <li
          key={item.label}
          className="flex items-center gap-1.5 text-xs text-on-surface-variant"
        >
          <span
            aria-hidden
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: item.color }}
          />
          {item.label}
        </li>
      ))}
    </ul>
  );
}

/** Создано и подписано — две серии, поэтому легенда обязательна: различие не
 *  должно держаться на одном цвете. */
export function FlowLineChart({ data }: { data: Point[] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -24 }}>
        <CartesianGrid
          vertical={false}
          stroke="var(--color-outline-variant)"
          strokeOpacity={0.5}
        />
        <XAxis dataKey="month" tickFormatter={monthLabel} tick={TICK} {...AXIS} />
        <YAxis width={44} allowDecimals={false} tick={TICK} {...AXIS} />
        <Tooltip
          content={<ChartTooltip />}
          labelFormatter={(label) => monthLabel(String(label ?? ""))}
          cursor={{ stroke: "var(--color-outline)", strokeWidth: 1 }}
        />
        <Legend verticalAlign="top" align="left" height={28} content={<SeriesLegend />} />
        <Line
          type="linear"
          dataKey="created"
          name="Создано"
          stroke="var(--color-chart-1)"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--color-surface-container-lowest)" }}
        />
        <Line
          type="linear"
          dataKey="signed"
          name="Подписано"
          stroke="var(--color-chart-2)"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--color-surface-container-lowest)" }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
