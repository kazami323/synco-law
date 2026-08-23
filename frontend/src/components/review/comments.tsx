"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import { ROLE_TITLES } from "@/lib/labels";
import type { DocumentComment } from "@/lib/types";
import { Button, Card, Chip, EmptyState, ErrorNote, Spinner } from "@/components/ui";

/**
 * Комментарии к документу и пунктам. Роль «Наблюдатель» по ТЗ смотрит и
 * комментирует, но статусы не меняет.
 */
export function DocumentComments({ contractId }: { contractId: string }) {
  const qc = useQueryClient();
  const { user } = useAuth();
  const [text, setText] = useState("");
  const [error, setError] = useState("");

  const comments = useQuery({
    queryKey: ["comments", contractId],
    queryFn: () => api<DocumentComment[]>(`/api/contracts/${contractId}/comments`),
  });

  const add = useMutation({
    mutationFn: () =>
      api(`/api/contracts/${contractId}/comments`, {
        method: "POST",
        body: { text },
      }),
    onSuccess: () => {
      setText("");
      setError("");
      qc.invalidateQueries({ queryKey: ["comments", contractId] });
      qc.invalidateQueries({ queryKey: ["clauses", contractId] });
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Не удалось добавить комментарий"),
  });

  const resolve = useMutation({
    mutationFn: (commentId: string) =>
      api(`/api/comments/${commentId}/resolve`, { method: "PATCH" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["comments", contractId] }),
  });

  const items = comments.data ?? [];

  return (
    <div className="space-y-4">
      {can(user, "comment") && (
        <Card className="p-4 space-y-3">
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={3}
            placeholder="Комментарий к документу"
            className="w-full rounded-lg border border-outline-variant bg-surface-container-lowest p-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
          {error && <ErrorNote message={error} />}
          <div className="flex justify-end">
            <Button
              onClick={() => add.mutate()}
              loading={add.isPending}
              disabled={!text.trim()}
            >
              Добавить
            </Button>
          </div>
        </Card>
      )}

      {comments.isLoading && <Spinner />}
      {!comments.isLoading && !items.length && (
        <EmptyState title="Комментариев пока нет" />
      )}

      {items.map((comment) => (
        <Card key={comment.id} className="p-4 space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-medium">
              {comment.author_name ?? "Пользователь"}
              {comment.author_role && (
                <span className="text-on-surface-variant font-normal">
                  {" "}
                  · {ROLE_TITLES[comment.author_role] ?? comment.author_role}
                </span>
              )}
            </p>
            <div className="flex items-center gap-2">
              {comment.clause_anchor && (
                <Chip tone="info">Пункт {comment.clause_anchor}</Chip>
              )}
              {comment.resolved_at && <Chip tone="success">Закрыт</Chip>}
            </div>
          </div>
          <p className="text-sm leading-relaxed whitespace-pre-wrap">
            {comment.text}
          </p>
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs text-outline">
              {new Date(comment.created_at).toLocaleString("ru-RU")}
            </p>
            {!comment.resolved_at && can(user, "comment") && (
              <button
                onClick={() => resolve.mutate(comment.id)}
                className="text-xs text-primary hover:underline cursor-pointer"
              >
                Отметить закрытым
              </button>
            )}
          </div>
        </Card>
      ))}
    </div>
  );
}
