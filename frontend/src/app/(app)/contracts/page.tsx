"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronRight, FileDown, Plus, Search } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, apiDownload } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import type { ContractList } from "@/lib/types";
import { Button, Card, EmptyState, Select, Skeleton } from "@/components/ui";
import {
  RiskChip,
  STATUS_LABELS,
  StatusChip,
  TypeChip,
  TypeIcon,
} from "@/components/contract-chips";
import { CreateContractModal } from "@/components/create-contract-modal";

/** Русское склонение: plural(2, ["договор","договора","договоров"]) → "договора" */
function plural(n: number, forms: [string, string, string]) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return forms[0];
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return forms[1];
  return forms[2];
}

export default function ContractsPage() {
  return (
    <Suspense>
      <ContractsSearchBoundary />
    </Suspense>
  );
}

function ContractsSearchBoundary() {
  const params = useSearchParams();
  const urlQuery = params.get("q") ?? "";
  return <ContractsContent key={params.toString()} initialQuery={urlQuery} />;
}

function ContractsContent({ initialQuery }: { initialQuery: string }) {
  const router = useRouter();
  const { user } = useAuth();
  const canCreate = can(user, "create");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState(initialQuery);
  const [modalOpen, setModalOpen] = useState(false);

  // Поиск из шапки: /contracts?q=... обновляет поле и результаты
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
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Все контракты</h1>
          <p className="mt-1 text-sm text-on-surface-variant">
            {data
              ? `${data.total} ${plural(data.total, ["договор", "договора", "договоров"])} в реестре`
              : "Реестр договоров"}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            onClick={() =>
              apiDownload(
                "/api/contracts/export/csv",
                `contracts_${new Date().toISOString().slice(0, 10)}.csv`
              )
            }
          >
            <span className="flex items-center gap-2">
              <FileDown size={16} /> Экспорт CSV
            </span>
          </Button>
          {canCreate && (
            <Button onClick={() => setModalOpen(true)}>
              <span className="flex items-center gap-2">
                <Plus size={16} /> Создать контракт
              </span>
            </Button>
          )}
        </div>
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
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead className="bg-surface-container-low">
              <tr className="text-left text-xs font-medium uppercase tracking-wide text-on-surface-variant">
                <th className="px-5 py-3">Договор</th>
                <th className="px-5 py-3">Тип</th>
                <th className="px-5 py-3">Риск</th>
                <th className="px-5 py-3">Статус</th>
                <th className="whitespace-nowrap px-5 py-3">Обновлён</th>
                <th className="px-5 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((c) => (
                <tr
                  key={c.id}
                  onClick={() => router.push(`/contracts/${c.id}`)}
                  className="group border-t border-outline-variant hover:bg-surface-container-low cursor-pointer"
                >
                  <td className="px-5 py-3.5">
                    <div className="flex items-center gap-3">
                      <TypeIcon type={c.contract_type} className="h-9 w-9 shrink-0" />
                      <div className="min-w-0">
                        <div className="font-medium text-on-surface group-hover:text-primary">
                          {c.title}
                        </div>
                        <div className="truncate text-xs text-on-surface-variant">
                          {c.counterparty ?? "Контрагент не указан"}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="px-5 py-3.5">
                    <TypeChip type={c.contract_type} />
                  </td>
                  <td className="px-5 py-3.5">
                    <RiskChip score={c.risk_score} />
                  </td>
                  <td className="px-5 py-3.5">
                    <StatusChip status={c.status} />
                  </td>
                  <td className="whitespace-nowrap px-5 py-3.5 text-on-surface-variant">
                    {new Date(c.updated_at).toLocaleDateString("ru-RU")}
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    <ChevronRight
                      size={16}
                      className="text-outline opacity-0 transition-opacity group-hover:opacity-100"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table></div>
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
              !status &&
              canCreate && (
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
