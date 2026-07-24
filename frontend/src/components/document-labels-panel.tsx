"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Plus, Sparkles, X } from "lucide-react";
import { Card, Chip, ErrorNote, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { labelActor, labelSpec } from "@/lib/labels";
import type { DocumentLabel } from "@/lib/types";

interface CatalogueItem {
  kind: string;
  title: string;
  tone: string;
  auto_only: boolean;
  can_set: boolean;
}

/**
 * Панель отметок документа: показывает проставленные плашки с автором и
 * позволяет ставить/снимать те, на которые у пользователя есть права.
 * Плашка «Проверено ИИ» ставится автоматически после анализа и руками не
 * снимается — она фиксирует факт проверки.
 */
export function DocumentLabelsPanel({
  contractId,
  labels,
}: {
  contractId: string;
  labels: DocumentLabel[];
}) {
  const qc = useQueryClient();

  const catalogue = useQuery({
    queryKey: ["labels", "catalogue"],
    queryFn: () => api<CatalogueItem[]>("/api/labels/catalogue"),
    staleTime: 5 * 60 * 1000,
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["contract", contractId] });
    qc.invalidateQueries({ queryKey: ["contracts"] });
  };

  const setLabel = useMutation({
    mutationFn: (kind: string) =>
      api(`/api/contracts/${contractId}/labels/${kind}`, { method: "PUT" }),
    onSuccess: refresh,
  });

  const removeLabel = useMutation({
    mutationFn: (kind: string) =>
      api(`/api/contracts/${contractId}/labels/${kind}`, { method: "DELETE" }),
    onSuccess: refresh,
  });

  const present = new Map(labels.map((label) => [label.kind, label]));
  const busy = setLabel.isPending || removeLabel.isPending;
  const error = (setLabel.error ?? removeLabel.error) as ApiError | null;

  return (
    <Card>
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-semibold">Отметки</h2>
        {busy && <Spinner className="w-4 h-4" />}
      </div>

      {labels.length > 0 ? (
        <div className="mt-3 flex flex-col gap-2">
          {labels.map((label) => {
            const spec = labelSpec(label.kind);
            const canRemove =
              !spec.autoOnly &&
              catalogue.data?.find((item) => item.kind === label.kind)?.can_set;
            return (
              <div
                key={label.kind}
                className="flex items-center justify-between gap-3 rounded-xl border border-outline-variant bg-surface-container-low px-3 py-2"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <Chip tone={spec.tone}>
                    {label.actor_type === "agent" && <Sparkles size={12} />}
                    {spec.title}
                  </Chip>
                  <span className="text-sm text-on-surface-variant truncate">
                    {labelActor(label)}
                  </span>
                </div>
                {canRemove && (
                  <button
                    type="button"
                    onClick={() => removeLabel.mutate(label.kind)}
                    disabled={busy}
                    title="Снять отметку"
                    className="shrink-0 rounded-lg p-1.5 text-on-surface-variant hover:bg-surface-container hover:text-error disabled:opacity-50"
                  >
                    <X size={16} />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <p className="mt-3 text-sm text-on-surface-variant">
          Отметок пока нет. «Проверено ИИ» появится автоматически после анализа.
        </p>
      )}

      {catalogue.data && (
        <div className="mt-4 flex flex-wrap gap-2">
          {catalogue.data
            .filter((item) => item.can_set && !present.has(item.kind))
            .map((item) => (
              <button
                key={item.kind}
                type="button"
                onClick={() => setLabel.mutate(item.kind)}
                disabled={busy}
                className="inline-flex items-center gap-1.5 rounded-full border border-outline-variant px-3 py-1.5 text-xs font-medium hover:bg-surface-container disabled:opacity-50"
              >
                <Plus size={13} />
                {item.title}
              </button>
            ))}
          {catalogue.data.every(
            (item) => !item.can_set || present.has(item.kind)
          ) && (
            <span className="inline-flex items-center gap-1.5 text-xs text-on-surface-variant">
              <Check size={13} /> Все доступные отметки проставлены
            </span>
          )}
        </div>
      )}

      {error && <div className="mt-3"><ErrorNote message={error.message} /></div>}
    </Card>
  );
}
