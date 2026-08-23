"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import type { ContractVersion, VersionDiff } from "@/lib/types";
import { Button, Chip, ErrorNote, Modal, Select, Spinner } from "@/components/ui";

/**
 * Сравнение версий в режиме различий и откат к предыдущей (ТЗ, раздел 5).
 * Откат создаёт новую версию, а не стирает историю: в журнале должно быть
 * видно, кто и когда откатывал.
 */
export function VersionDiffModal({
  contractId,
  versions,
  locked,
  onClose,
}: {
  contractId: string;
  versions: ContractVersion[];
  locked: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const { user } = useAuth();
  const sorted = [...versions].sort((a, b) => b.version_number - a.version_number);
  const [toVersion, setToVersion] = useState(sorted[0]?.version_number ?? 1);
  const [fromVersion, setFromVersion] = useState(
    sorted[1]?.version_number ?? Math.max(1, (sorted[0]?.version_number ?? 1) - 1),
  );
  const [error, setError] = useState("");
  const [confirmRestore, setConfirmRestore] = useState(false);

  const diff = useQuery({
    queryKey: ["version-diff", contractId, fromVersion, toVersion],
    queryFn: () =>
      api<VersionDiff>(
        `/api/contracts/${contractId}/versions/${toVersion}/diff?against=${fromVersion}`,
      ),
  });

  const restore = useMutation({
    mutationFn: (version: number) =>
      api(`/api/contracts/${contractId}/versions/${version}/restore`, {
        method: "POST",
        body: { comment: `Откат к версии ${version}` },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["contract", contractId] });
      qc.invalidateQueries({ queryKey: ["contract-versions", contractId] });
      qc.invalidateQueries({ queryKey: ["clauses", contractId] });
      onClose();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Не удалось откатить версию"),
  });

  return (
    <Modal title="Сравнение версий" onClose={onClose}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Select
            label="Версия «до»"
            value={fromVersion}
            onChange={(event) => setFromVersion(Number(event.target.value))}
          >
            {sorted.map((version) => (
              <option key={version.id} value={version.version_number}>
                Версия {version.version_number}
              </option>
            ))}
          </Select>
          <Select
            label="Версия «после»"
            value={toVersion}
            onChange={(event) => setToVersion(Number(event.target.value))}
          >
            {sorted.map((version) => (
              <option key={version.id} value={version.version_number}>
                Версия {version.version_number}
              </option>
            ))}
          </Select>
        </div>

        {diff.isLoading && <Spinner />}
        {diff.isError && <ErrorNote message="Не удалось получить различия" />}

        {diff.data && (
          <>
            <div className="flex flex-wrap gap-2">
              {diff.data.summary.identical ? (
                <Chip tone="neutral">Версии совпадают</Chip>
              ) : (
                <>
                  <Chip tone="success">Добавлено: {diff.data.summary.added}</Chip>
                  <Chip tone="error">Удалено: {diff.data.summary.removed}</Chip>
                  <Chip tone="warning">
                    Переформулировано: {diff.data.summary.changed}
                  </Chip>
                </>
              )}
            </div>

            <div className="max-h-[50vh] overflow-y-auto space-y-2 text-sm">
              {diff.data.blocks
                .filter((block) => block.type !== "equal")
                .map((block, index) => (
                  <div
                    key={`${block.type}-${index}`}
                    className="rounded-lg border border-outline-variant overflow-hidden"
                  >
                    {block.old_lines.map((line, lineIndex) => (
                      <p
                        key={`old-${lineIndex}`}
                        className="px-3 py-1.5 bg-error/10 text-error whitespace-pre-wrap"
                      >
                        − {line}
                      </p>
                    ))}
                    {block.new_lines.map((line, lineIndex) => (
                      <p
                        key={`new-${lineIndex}`}
                        className="px-3 py-1.5 bg-success/10 text-success whitespace-pre-wrap"
                      >
                        + {line}
                      </p>
                    ))}
                  </div>
                ))}
            </div>
          </>
        )}

        {error && <ErrorNote message={error} />}

        {can(user, "edit") && !locked && (
          confirmRestore ? (
            <div className="rounded-lg border border-warning/40 bg-warning/10 p-3 space-y-2.5">
              <p className="text-sm">
                Текст документа будет заменён редакцией версии {fromVersion}.
                Подтверждения по пунктам, текст которых изменится, придётся
                проходить заново.
              </p>
              <div className="flex gap-2">
                <Button
                  variant="danger"
                  onClick={() => restore.mutate(fromVersion)}
                  loading={restore.isPending}
                >
                  Да, откатить
                </Button>
                <Button variant="ghost" onClick={() => setConfirmRestore(false)}>
                  Отмена
                </Button>
              </div>
            </div>
          ) : (
            <Button
              variant="secondary"
              className="w-full"
              onClick={() => setConfirmRestore(true)}
            >
              Откатить к версии {fromVersion}
            </Button>
          )
        )}
        {locked && (
          <p className="text-xs text-on-surface-variant">
            Документ в статусе «Финальный»: откат недоступен.
          </p>
        )}
      </div>
    </Modal>
  );
}
