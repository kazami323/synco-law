"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CircleDashed, GitBranch, XCircle } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { Button, Card, ErrorNote, Modal } from "@/components/ui";

interface WorkflowInfo {
  status: string;
  available_actions: string[];
  history: {
    stage: string;
    comment: string | null;
    at: string | null;
    by: string | null;
  }[];
}

const CHAIN = [
  { status: "draft", label: "Черновик" },
  { status: "analyzed", label: "AI-анализ" },
  { status: "approved", label: "Юр. согласование" },
  { status: "approved_finance", label: "Финансы" },
  { status: "ready_to_sign", label: "К подписанию" },
  { status: "signed", label: "Подписан" },
];

const ACTION_LABELS: Record<string, string> = {
  approve_legal: "Согласовать (юрист)",
  approve_finance: "Согласовать (финансы)",
  finalize: "Передать на подписание",
};

const STAGE_LABELS: Record<string, string> = {
  approved: "Юр. согласование",
  approved_finance: "Финансовое согласование",
  ready_to_sign: "Передан на подписание",
  signed: "Подписан",
  rejected: "Отклонен",
};

export function WorkflowPanel({ contractId }: { contractId: string }) {
  const qc = useQueryClient();
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectComment, setRejectComment] = useState("");
  const [error, setError] = useState("");
  const [pendingAction, setPendingAction] = useState<string | null>(null);

  const wf = useQuery({
    queryKey: ["workflow", contractId],
    queryFn: () => api<WorkflowInfo>(`/api/contracts/${contractId}/workflow`),
  });

  const transition = useMutation({
    mutationFn: ({ action, comment }: { action: string; comment?: string }) => {
      setPendingAction(action);
      return api(`/api/contracts/${contractId}/workflow/${action}`, {
        method: "POST",
        body: { comment: comment ?? null },
      });
    },
    onSettled: () => setPendingAction(null),
    onSuccess: () => {
      setRejectOpen(false);
      setRejectComment("");
      qc.invalidateQueries({ queryKey: ["workflow", contractId] });
      qc.invalidateQueries({ queryKey: ["contract", contractId] });
      qc.invalidateQueries({ queryKey: ["contracts"] });
      qc.invalidateQueries({ queryKey: ["dashboard-metrics"] });
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Ошибка перехода"),
  });

  if (!wf.data) return null;
  const { status, available_actions, history } = wf.data;
  const currentIdx = CHAIN.findIndex((s) => s.status === status);
  const actions = available_actions.filter((a) => a !== "reject" && a !== "sign");
  const canReject = available_actions.includes("reject");

  if (status === "archived") return null;

  return (
    <Card className="p-6">
      <div className="flex items-center gap-2 font-semibold mb-4">
        <GitBranch size={18} />
        Согласование
      </div>

      <ol className="space-y-0">
        {CHAIN.map((step, i) => {
          const done = currentIdx >= i;
          const isCurrent = currentIdx === i;
          return (
            <li key={step.status} className="flex gap-3">
              <div className="flex flex-col items-center">
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 ${
                    done
                      ? "bg-primary text-on-primary"
                      : "bg-surface-container-high text-outline"
                  }`}
                >
                  {done ? <Check size={13} /> : <CircleDashed size={13} />}
                </div>
                {i < CHAIN.length - 1 && (
                  <div
                    className={`w-px flex-1 min-h-4 ${
                      done && currentIdx > i ? "bg-primary" : "bg-outline-variant"
                    }`}
                  />
                )}
              </div>
              <div
                className={`pb-4 text-sm ${
                  isCurrent
                    ? "font-semibold text-primary"
                    : done
                      ? "text-on-surface"
                      : "text-on-surface-variant"
                }`}
              >
                {step.label}
              </div>
            </li>
          );
        })}
      </ol>

      {error && (
        <div className="mb-3">
          <ErrorNote message={error} />
        </div>
      )}

      {(actions.length > 0 || canReject) && (
        <div className="flex flex-col gap-2 border-t border-outline-variant pt-4">
          {actions.map((a) => (
            <Button
              key={a}
              disabled={transition.isPending}
              loading={transition.isPending && pendingAction === a}
              onClick={() => {
                setError("");
                transition.mutate({ action: a });
              }}
            >
              {ACTION_LABELS[a] ?? a}
            </Button>
          ))}
          {canReject && (
            <Button
              variant="secondary"
              disabled={transition.isPending}
              onClick={() => setRejectOpen(true)}
            >
              <span className="flex items-center gap-2 text-error">
                <XCircle size={16} /> Отклонить
              </span>
            </Button>
          )}
        </div>
      )}

      {history.length > 0 && (
        <div className="border-t border-outline-variant pt-4 mt-4 space-y-3">
          {history
            .slice()
            .reverse()
            .map((h, i) => (
              <div key={i} className="text-sm">
                <div className="flex items-center justify-between">
                  <span
                    className={`font-medium ${
                      h.stage === "rejected" ? "text-error" : ""
                    }`}
                  >
                    {STAGE_LABELS[h.stage] ?? h.stage}
                  </span>
                  <span className="text-xs text-on-surface-variant">
                    {h.at ? new Date(h.at).toLocaleDateString("ru-RU") : ""}
                  </span>
                </div>
                <div className="text-xs text-on-surface-variant mt-0.5">
                  {h.by}
                  {h.comment ? ` - ${h.comment}` : ""}
                </div>
              </div>
            ))}
        </div>
      )}

      {rejectOpen && (
        <Modal title="Отклонить контракт" onClose={() => setRejectOpen(false)}>
          <p className="text-sm text-on-surface-variant mb-3">
            Контракт вернется в статус «Черновик». Укажите, что нужно исправить.
          </p>
          <textarea
            value={rejectComment}
            onChange={(e) => setRejectComment(e.target.value)}
            rows={4}
            placeholder="Причина отклонения..."
            className="w-full px-3 py-2 rounded-lg border border-outline-variant bg-surface-container-lowest text-sm outline-none focus:border-primary"
          />
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="secondary" onClick={() => setRejectOpen(false)}>
              Отмена
            </Button>
            <Button
              variant="danger"
              disabled={!rejectComment.trim()}
              loading={transition.isPending}
              onClick={() => {
                setError("");
                transition.mutate({
                  action: "reject",
                  comment: rejectComment.trim(),
                });
              }}
            >
              Отклонить
            </Button>
          </div>
        </Modal>
      )}
    </Card>
  );
}
