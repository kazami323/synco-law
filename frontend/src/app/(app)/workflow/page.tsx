"use client";

import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Contract, ContractList } from "@/lib/types";
import { RiskChip, TypeChip } from "@/components/contract-chips";

// Колонки канбана: стадия процесса → какие статусы в неё попадают
const COLUMNS: { title: string; match: (c: Contract) => boolean }[] = [
  { title: "Создание", match: (c) => c.status === "draft" },
  { title: "Проверка ИИ", match: (c) => c.status === "analyzing" },
  { title: "Юр. согласование", match: (c) => c.status === "analyzed" },
  { title: "Финансы", match: (c) => c.status === "approved" },
  {
    title: "Подписание",
    match: (c) => c.status === "approved_finance" || c.status === "ready_to_sign",
  },
  { title: "Подписано", match: (c) => c.status === "signed" },
];

export default function WorkflowPage() {
  const contracts = useQuery({
    queryKey: ["contracts", "kanban"],
    queryFn: () => api<ContractList>("/api/contracts/?limit=200"),
  });

  const items = contracts.data?.items ?? [];

  return (
    <div>
      <h1 className="text-2xl font-semibold">Workflow</h1>
      <p className="text-on-surface-variant text-sm mt-1">
        Контракты по стадиям согласования. Откройте карточку, чтобы
        согласовать или отклонить.
      </p>

      <div className="flex gap-4 mt-6 overflow-x-auto pb-4">
        {COLUMNS.map((col) => {
          const inColumn = items.filter(col.match);
          return (
            <div
              key={col.title}
              className="w-72 shrink-0 bg-surface-container-low border border-outline-variant rounded-xl flex flex-col max-h-[calc(100vh-14rem)]"
            >
              <div className="flex items-center justify-between px-4 py-3 border-b border-outline-variant bg-surface-container-lowest rounded-t-xl">
                <span className="font-semibold text-sm">{col.title}</span>
                <span className="text-xs bg-surface-container-high rounded-full px-2 py-0.5 text-on-surface-variant">
                  {inColumn.length}
                </span>
              </div>
              <div className="p-3 space-y-3 overflow-y-auto flex-1">
                {inColumn.length === 0 && (
                  <div className="text-center py-10 text-on-surface-variant">
                    <FileText size={20} className="mx-auto text-outline" />
                    <div className="text-xs mt-2">Пусто</div>
                  </div>
                )}
                {inColumn.map((c) => (
                  <Link
                    key={c.id}
                    href={`/contracts/${c.id}`}
                    className="block bg-surface-container-lowest border border-outline-variant rounded-lg p-3 hover:border-primary transition-colors"
                  >
                    <div className="flex flex-wrap gap-1.5">
                      <TypeChip type={c.contract_type} />
                      <RiskChip score={c.risk_score} />
                    </div>
                    <div className="font-medium text-sm mt-2 leading-snug">
                      {c.title}
                    </div>
                    <div className="text-xs text-on-surface-variant mt-1.5 pt-1.5 border-t border-outline-variant">
                      {c.counterparty ?? "Без контрагента"} ·{" "}
                      {new Date(c.updated_at).toLocaleDateString("ru-RU")}
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
