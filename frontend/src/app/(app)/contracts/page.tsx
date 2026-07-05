"use client";

import { useQuery } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ContractList } from "@/lib/types";
import { Button, Card, EmptyState, Select, Skeleton } from "@/components/ui";
import {
  RiskChip,
  STATUS_LABELS,
  StatusChip,
  TypeChip,
} from "@/components/contract-chips";
import { CreateContractModal } from "@/components/create-contract-modal";

export default function ContractsPage() {
  return (
    <Suspense>
      <ContractsContent />
    </Suspense>
  );
}

function ContractsContent() {
  const router = useRouter();
  const params = useSearchParams();
  const [status, setStatus] = useState("");
  const [q, setQ] = useState(params.get("q") ?? "");
  const [modalOpen, setModalOpen] = useState(false);

  // Поиск из шапки: /contracts?q=... обновляет поле и результаты
  const urlQuery = params.get("q") ?? "";
  useEffect(() => {
    setQ(urlQuery);
  }, [urlQuery]);

  const { data, isLoading } = useQuery({
    queryKey: ["contracts", status, q],
    queryFn: () =>
      api<ContractList>(
        `/api/contracts/?limit=20${status ? `&status_filter=${status}` : ""}${
          q ? `&q=${encodeURIComponent(q)}` : ""
        }`
      ),
  });

  return (
    <div className="max-w-6xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Все контракты</h1>
        <Button onClick={() => setModalOpen(true)}>
          <span className="flex items-center gap-2">
            <Plus size={16} /> Создать контракт
          </span>
        </Button>
      </div>

      {/* Панель фильтров */}
      <Card className="mt-6 p-4 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-64">
          <Search
            size={18}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-outline"
          />
          <input
            placeholder="Имя контракта или контрагент..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="w-full h-10 pl-10 pr-3 rounded-lg border border-outline-variant bg-surface-container-lowest text-sm outline-none focus:border-primary placeholder:text-outline"
          />
        </div>
        <Select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="w-48"
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
          <div className="p-6 space-y-3">
            {[0, 1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-12" />
            ))}
          </div>
        ) : data && data.items.length > 0 ? (
          <table className="w-full text-sm">
            <thead className="bg-surface-container-low">
              <tr className="text-left text-xs uppercase tracking-wide text-on-surface-variant">
                <th className="px-6 py-3">Название</th>
                <th className="px-6 py-3">Тип</th>
                <th className="px-6 py-3">Контрагент</th>
                <th className="px-6 py-3">Риск</th>
                <th className="px-6 py-3">Статус</th>
                <th className="px-6 py-3">Создан</th>
                <th className="px-6 py-3">Обновлён</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((c) => (
                <tr
                  key={c.id}
                  onClick={() => router.push(`/contracts/${c.id}`)}
                  className="border-t border-outline-variant hover:bg-surface-container-low cursor-pointer"
                >
                  <td className="px-6 py-4 text-primary font-medium">
                    {c.title}
                  </td>
                  <td className="px-6 py-4">
                    <TypeChip type={c.contract_type} />
                  </td>
                  <td className="px-6 py-4">{c.counterparty ?? "—"}</td>
                  <td className="px-6 py-4">
                    <RiskChip score={c.risk_score} />
                  </td>
                  <td className="px-6 py-4">
                    <StatusChip status={c.status} />
                  </td>
                  <td className="px-6 py-4">
                    {new Date(c.created_at).toLocaleDateString("ru-RU")}
                  </td>
                  <td className="px-6 py-4">
                    {new Date(c.updated_at).toLocaleDateString("ru-RU")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState
            title={q || status ? "Ничего не найдено" : "Контрактов пока нет"}
            hint={
              q || status
                ? "Попробуйте изменить фильтры"
                : "Загрузите файл или создайте контракт с помощью AI"
            }
            action={
              !q &&
              !status && (
                <Button onClick={() => setModalOpen(true)}>
                  <span className="flex items-center gap-2">
                    <Plus size={16} /> Создать контракт
                  </span>
                </Button>
              )
            }
          />
        )}
      </Card>

      {modalOpen && <CreateContractModal onClose={() => setModalOpen(false)} />}
    </div>
  );
}
