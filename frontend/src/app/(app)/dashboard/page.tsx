"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  CircleAlert,
  TriangleAlert,
} from "lucide-react";
import { api } from "@/lib/api";
import type { ContractList, DashboardMetrics } from "@/lib/types";
import { Card, EmptyState } from "@/components/ui";

const KPI: {
  key: keyof DashboardMetrics;
  label: string;
  tone: "neutral" | "error" | "warning" | "success" | "info";
  icon?: React.ComponentType<{ size?: number; className?: string }>;
}[] = [
  { key: "total_reviewed", label: "Проверено контрактов", tone: "neutral" },
  { key: "high_risk", label: "Высокий риск", tone: "error", icon: TriangleAlert },
  { key: "medium_risk", label: "Средний риск", tone: "warning", icon: CircleAlert },
  { key: "low_risk", label: "Низкий риск", tone: "success", icon: CheckCircle2 },
  { key: "pending_approval", label: "На согласовании", tone: "neutral" },
  { key: "signed", label: "Подписано", tone: "success" },
];

const TONE_TEXT = {
  neutral: "text-on-surface",
  error: "text-error",
  warning: "text-warning",
  success: "text-success",
  info: "text-primary",
};

export default function DashboardPage() {
  const metrics = useQuery({
    queryKey: ["dashboard-metrics"],
    queryFn: () => api<DashboardMetrics>("/api/dashboard/metrics"),
  });
  const contracts = useQuery({
    queryKey: ["contracts", "recent"],
    queryFn: () => api<ContractList>("/api/contracts/?limit=5"),
  });

  return (
    <div className="max-w-6xl">
      <h1 className="text-2xl font-semibold">Обзор панелей</h1>
      <p className="text-on-surface-variant text-sm mt-1">
        Сводка по контрактам и критичные уведомления.
      </p>

      {/* KPI-карточки */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4 mt-6">
        {KPI.map(({ key, label, tone, icon: Icon }) => (
          <Card key={key} className="p-4">
            <div
              className={`flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide ${TONE_TEXT[tone]}`}
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
        {/* Недавние контракты */}
        <Card className="xl:col-span-2 overflow-hidden">
          <div className="flex items-center justify-between px-6 py-4 bg-surface-container-low border-b border-outline-variant">
            <h2 className="font-semibold">Недавние контракты</h2>
          </div>
          {contracts.data && contracts.data.items.length > 0 ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-on-surface-variant">
                  <th className="px-6 py-3">Название</th>
                  <th className="px-6 py-3">Статус</th>
                  <th className="px-6 py-3">Дата</th>
                </tr>
              </thead>
              <tbody>
                {contracts.data.items.map((c) => (
                  <tr key={c.id} className="border-t border-outline-variant">
                    <td className="px-6 py-3">{c.title}</td>
                    <td className="px-6 py-3">{c.status}</td>
                    <td className="px-6 py-3">
                      {new Date(c.created_at).toLocaleDateString("ru-RU")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState
              title="Контрактов пока нет"
              hint="Раздел контрактов заработает на следующем этапе разработки (Weeks 5-6)"
            />
          )}
        </Card>

        {/* Критичные сроки */}
        <Card className="bg-warning-container/30 border-warning/30">
          <div className="flex items-center gap-2 px-6 py-4">
            <AlertTriangle size={18} className="text-warning" />
            <h2 className="font-semibold">Критичные сроки</h2>
          </div>
          <div className="px-6 pb-6 text-sm text-on-surface-variant">
            Нет приближающихся сроков. Уведомления появятся, когда в системе
            будут подписанные контракты с датами окончания.
          </div>
        </Card>
      </div>
    </div>
  );
}
