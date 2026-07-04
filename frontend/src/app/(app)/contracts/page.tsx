"use client";

import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import type { ContractList } from "@/lib/types";
import { Button, Card, Chip, EmptyState, Select } from "@/components/ui";

const STATUS_LABELS: Record<string, { label: string; tone: "success" | "warning" | "error" | "info" | "neutral" }> = {
  draft: { label: "Черновик", tone: "neutral" },
  analyzing: { label: "На проверке", tone: "info" },
  analyzed: { label: "Проверен", tone: "info" },
  approved: { label: "Согласован", tone: "success" },
  ready_to_sign: { label: "К подписанию", tone: "warning" },
  signed: { label: "Подписан", tone: "success" },
  archived: { label: "В архиве", tone: "neutral" },
};

function riskChip(score: number | null) {
  if (score === null) return <Chip tone="neutral">—</Chip>;
  if (score > 70) return <Chip tone="error">● Высокий</Chip>;
  if (score >= 40) return <Chip tone="warning">● Средний</Chip>;
  return <Chip tone="success">● Низкий</Chip>;
}

export default function ContractsPage() {
  const [status, setStatus] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["contracts", status],
    queryFn: () =>
      api<ContractList>(
        `/api/contracts/?limit=20${status ? `&status_filter=${status}` : ""}`
      ),
  });

  return (
    <div className="max-w-6xl">
      <h1 className="text-2xl font-semibold">Все контракты</h1>

      {/* Панель фильтров */}
      <Card className="mt-6 p-4 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-64">
          <Search
            size={18}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-outline"
          />
          <input
            placeholder="Имя контракта или ID..."
            className="w-full h-10 pl-10 pr-3 rounded-lg border border-outline-variant bg-surface-container-lowest text-sm outline-none focus:border-primary placeholder:text-outline"
          />
        </div>
        <Select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="w-44"
        >
          <option value="">Статус: Все</option>
          {Object.entries(STATUS_LABELS).map(([value, { label }]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </Card>

      {/* Таблица */}
      <Card className="mt-4 overflow-hidden">
        {isLoading ? (
          <EmptyState title="Загрузка..." />
        ) : data && data.items.length > 0 ? (
          <table className="w-full text-sm">
            <thead className="bg-surface-container-low">
              <tr className="text-left text-xs uppercase tracking-wide text-on-surface-variant">
                <th className="px-6 py-3">Название</th>
                <th className="px-6 py-3">Тип</th>
                <th className="px-6 py-3">Контрагент</th>
                <th className="px-6 py-3">Риск</th>
                <th className="px-6 py-3">Статус</th>
                <th className="px-6 py-3">Дата создания</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((c) => {
                const st = STATUS_LABELS[c.status] ?? {
                  label: c.status,
                  tone: "neutral" as const,
                };
                return (
                  <tr
                    key={c.id}
                    className="border-t border-outline-variant hover:bg-surface-container-low"
                  >
                    <td className="px-6 py-4 text-primary font-medium">
                      {c.title}
                    </td>
                    <td className="px-6 py-4">
                      <Chip tone="neutral">{c.contract_type ?? "—"}</Chip>
                    </td>
                    <td className="px-6 py-4">{c.counterparty ?? "—"}</td>
                    <td className="px-6 py-4">{riskChip(c.risk_score)}</td>
                    <td className="px-6 py-4">
                      <Chip tone={st.tone}>{st.label}</Chip>
                    </td>
                    <td className="px-6 py-4">
                      {new Date(c.created_at).toLocaleDateString("ru-RU")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <EmptyState
            title="Контрактов пока нет"
            hint="Создание контрактов, загрузка PDF/DOCX и AI-анализ появятся на этапе Weeks 5-8"
          />
        )}
        <div className="px-6 py-4 border-t border-outline-variant bg-surface-container-low">
          <Button disabled title="Появится на этапе Weeks 5-6">
            Создать контракт
          </Button>
        </div>
      </Card>
    </div>
  );
}
