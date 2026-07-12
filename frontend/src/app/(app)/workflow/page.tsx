"use client";

import { useQuery } from "@tanstack/react-query";
import { Inbox } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Contract, ContractList } from "@/lib/types";
import { ErrorNote, Skeleton } from "@/components/ui";
import { RiskChip, TypeChip, TypeIcon } from "@/components/contract-chips";

type Tone = "neutral" | "info" | "warning" | "success";

const TONES: Record<Tone, { dot: string; badge: string; bar: string }> = {
  neutral: {
    dot: "bg-outline",
    badge: "bg-surface-container-high text-on-surface-variant",
    bar: "bg-outline-variant",
  },
  info: { dot: "bg-primary", badge: "bg-primary/10 text-primary", bar: "bg-primary" },
  warning: {
    dot: "bg-warning",
    badge: "bg-warning/10 text-warning",
    bar: "bg-warning",
  },
  success: {
    dot: "bg-success",
    badge: "bg-success/10 text-success",
    bar: "bg-success",
  },
};

// Колонки канбана: стадия процесса → какие статусы в неё попадают
const COLUMNS: { title: string; tone: Tone; match: (c: Contract) => boolean }[] = [
  { title: "Создание", tone: "neutral", match: (c) => c.status === "draft" },
  { title: "Проверка ИИ", tone: "info", match: (c) => c.status === "analyzing" },
  { title: "Юр. согласование", tone: "info", match: (c) => c.status === "analyzed" },
  { title: "Финансы", tone: "warning", match: (c) => c.status === "approved" },
  {
    title: "Подписание",
    tone: "warning",
    match: (c) => c.status === "approved_finance" || c.status === "ready_to_sign",
  },
  { title: "Подписано", tone: "success", match: (c) => c.status === "signed" },
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
      <p className="mt-1 text-sm text-on-surface-variant">
        Контракты по стадиям согласования. Откройте карточку, чтобы согласовать
        или отклонить.
      </p>

      {contracts.isError && (
        <div className="mt-6 max-w-xl">
          <ErrorNote
            message={
              contracts.error instanceof Error
                ? contracts.error.message
                : "Не удалось загрузить workflow"
            }
          />
        </div>
      )}

      <div className="mt-6 flex gap-4 overflow-x-auto pb-4">
        {contracts.isLoading &&
          COLUMNS.map((col) => (
            <div key={col.title} className="w-72 shrink-0 space-y-3">
              <Skeleton className="h-12" />
              <Skeleton className="h-28" />
              <Skeleton className="h-28" />
            </div>
          ))}
        {!contracts.isLoading &&
          COLUMNS.map((col) => {
            const inColumn = items.filter(col.match);
            const tone = TONES[col.tone];
            return (
              <div
                key={col.title}
                className="flex max-h-[calc(100vh-14rem)] w-72 shrink-0 flex-col overflow-hidden rounded-xl border border-outline-variant bg-surface-container-low"
              >
                {/* цветной акцент стадии */}
                <div className={`h-1 ${tone.bar}`} />
                <div className="flex items-center justify-between border-b border-outline-variant bg-surface-container-lowest px-4 py-3">
                  <span className="flex items-center gap-2 text-sm font-semibold">
                    <span className={`h-2 w-2 rounded-full ${tone.dot}`} />
                    {col.title}
                  </span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium tabular-nums ${tone.badge}`}
                  >
                    {inColumn.length}
                  </span>
                </div>
                <div className="flex-1 space-y-3 overflow-y-auto p-3">
                  {inColumn.length === 0 && (
                    <div className="py-10 text-center text-on-surface-variant">
                      <Inbox size={22} className="mx-auto text-outline" />
                      <div className="mt-2 text-xs">Пусто</div>
                    </div>
                  )}
                  {inColumn.map((c) => (
                    <Link
                      key={c.id}
                      href={`/contracts/${c.id}`}
                      className="block rounded-lg border border-outline-variant bg-surface-container-lowest p-3 transition-all hover:-translate-y-0.5 hover:border-primary hover:shadow-sm"
                    >
                      <div className="flex items-start gap-2.5">
                        <TypeIcon
                          type={c.contract_type}
                          size={15}
                          className="mt-0.5 h-7 w-7 shrink-0"
                        />
                        <div className="min-w-0 flex-1 text-sm font-medium leading-snug">
                          {c.title}
                        </div>
                      </div>
                      <div className="mt-2.5 flex flex-wrap gap-1.5">
                        <TypeChip type={c.contract_type} />
                        <RiskChip score={c.risk_score} />
                      </div>
                      <div className="mt-2.5 border-t border-outline-variant pt-2 text-xs text-on-surface-variant">
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
