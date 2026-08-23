"use client";

import { useQuery } from "@tanstack/react-query";
import { History } from "lucide-react";
import { api } from "@/lib/api";
import type { AuditPage } from "@/lib/types";
import { Card, EmptyState, ErrorNote, Skeleton } from "@/components/ui";

/**
 * Журнал действий по документу (ТЗ, раздел 5). Записи писались с самого
 * начала, но прочитать их было нечем — эндпоинта и экрана не существовало,
 * а ТЗ требует, чтобы решение юриста фиксировалось с автором и временем и это
 * можно было увидеть.
 */
export function AuditTrail({ contractId }: { contractId: string }) {
  const entries = useQuery({
    queryKey: ["contract-audit", contractId],
    queryFn: () => api<AuditPage>(`/api/contracts/${contractId}/audit?limit=100`),
  });

  if (entries.isLoading)
    return (
      <div className="space-y-2">
        <Skeleton className="h-14" />
        <Skeleton className="h-14" />
        <Skeleton className="h-14" />
      </div>
    );

  if (entries.isError)
    return <ErrorNote message="Не удалось загрузить журнал действий" />;

  const items = entries.data?.items ?? [];
  if (!items.length)
    return (
      <Card>
        <EmptyState
          icon={<History size={20} />}
          title="Записей пока нет"
          hint="Здесь появятся все действия с документом: кто и когда его менял, подтверждал пункты и менял статус."
        />
      </Card>
    );

  return (
    <Card>
      <ul className="divide-y divide-outline-variant">
        {items.map((entry) => (
          <li key={entry.id} className="flex flex-wrap items-baseline gap-x-2 gap-y-1 px-4 py-3">
            <span className="text-sm font-medium">{entry.title}</span>
            {entry.detail && (
              <span className="text-sm text-on-surface-variant">{entry.detail}</span>
            )}
            <span className="ml-auto text-xs text-outline whitespace-nowrap">
              {entry.author_name ?? "система"}
              {entry.author_role_title && ` · ${entry.author_role_title}`}
              {" · "}
              {new Date(entry.created_at).toLocaleString("ru-RU", {
                day: "2-digit",
                month: "2-digit",
                year: "2-digit",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </li>
        ))}
      </ul>
      {entries.data && entries.data.total > items.length && (
        <p className="border-t border-outline-variant px-4 py-2.5 text-xs text-on-surface-variant">
          Показаны последние {items.length} из {entries.data.total} записей.
        </p>
      )}
    </Card>
  );
}
