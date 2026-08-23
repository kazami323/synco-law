"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2, UserPlus } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import type {
  ProjectContext,
  ProjectMember,
  User,
  UserList,
} from "@/lib/types";
import { ROLE_LABELS } from "@/lib/types";
import {
  Button,
  Card,
  Chip,
  ConfirmButton,
  ErrorNote,
  Input,
  Select,
  Skeleton,
} from "@/components/ui";

const ACCESS_LABELS: Record<ProjectMember["access"], string> = {
  read: "Просмотр",
  comment: "Просмотр и комментарии",
  write: "Работа с документами",
};

/**
 * Общий контекст проекта и участники (ТЗ, раздел 1).
 *
 * Контекст заполняется один раз на проект и подставляется в генерацию
 * документов, чтобы юрист не вводил стороны, суммы и сроки в каждый договор.
 */
export function ProjectContextPanel({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const { user } = useAuth();
  const canEdit = can(user, "create");
  const [error, setError] = useState("");
  const [draft, setDraft] = useState<ProjectContext | null>(null);

  const context = useQuery({
    queryKey: ["project-context", projectId],
    queryFn: () => api<ProjectContext>(`/api/projects/${projectId}/context`),
  });

  const value = draft ?? context.data ?? {};

  const save = useMutation({
    mutationFn: () =>
      api<ProjectContext>(`/api/projects/${projectId}/context`, {
        method: "PUT",
        body: {
          ...value,
          amount: value.amount ? Number(value.amount) : null,
        },
      }),
    onSuccess: () => {
      setError("");
      setDraft(null);
      qc.invalidateQueries({ queryKey: ["project-context", projectId] });
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Не удалось сохранить контекст"),
  });

  const patch = (changes: Partial<ProjectContext>) =>
    setDraft({ ...value, ...changes });

  return (
    <Card className="p-5 space-y-4">
      <div>
        <h3 className="font-semibold">Контекст проекта</h3>
        <p className="text-sm text-on-surface-variant mt-0.5">
          Стороны, суммы и сроки — подставляются при генерации документов
        </p>
      </div>

      {/* Пустые поля означают «контекст не заполняли». Пока данные грузятся
          или запрос упал, это не так — и юрист не должен принять одно за
          другое: по этому контексту генерируются документы. */}
      {context.isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
        </div>
      )}

      {context.isError && (
        <ErrorNote message="Не удалось загрузить контекст проекта. Обновите страницу." />
      )}

      {!context.isLoading && !context.isError && (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Input
          label="Наша сторона"
          value={value.our_party ?? ""}
          disabled={!canEdit}
          onChange={(event) => patch({ our_party: event.target.value })}
        />
        <Input
          label="Контрагент"
          value={value.counterparty ?? ""}
          disabled={!canEdit}
          onChange={(event) => patch({ counterparty: event.target.value })}
        />
        <Input
          label="Сумма сделки"
          type="number"
          value={value.amount ?? ""}
          disabled={!canEdit}
          onChange={(event) =>
            patch({ amount: event.target.value ? Number(event.target.value) : null })
          }
        />
        <Select
          label="Валюта"
          value={value.currency ?? "UZS"}
          disabled={!canEdit}
          onChange={(event) => patch({ currency: event.target.value })}
        >
          <option>UZS</option>
          <option>USD</option>
          <option>EUR</option>
          <option>RUB</option>
        </Select>
        <Input
          label="Начало"
          type="date"
          value={value.start_date ?? ""}
          disabled={!canEdit}
          onChange={(event) => patch({ start_date: event.target.value })}
        />
        <Input
          label="Окончание"
          type="date"
          value={value.end_date ?? ""}
          disabled={!canEdit}
          onChange={(event) => patch({ end_date: event.target.value })}
        />
        <div className="md:col-span-2">
          <Input
            label="Подсудность"
            value={value.jurisdiction ?? ""}
            disabled={!canEdit}
            onChange={(event) => patch({ jurisdiction: event.target.value })}
          />
        </div>
      </div>
      )}

      {error && <ErrorNote message={error} />}

      {canEdit && draft && (
        <div className="flex gap-2">
          <Button onClick={() => save.mutate()} loading={save.isPending}>
            Сохранить контекст
          </Button>
          <Button variant="secondary" onClick={() => setDraft(null)}>
            Отмена
          </Button>
        </div>
      )}

      <ProjectMembers projectId={projectId} canEdit={canEdit} />
    </Card>
  );
}

function ProjectMembers({
  projectId,
  canEdit,
}: {
  projectId: string;
  canEdit: boolean;
}) {
  const qc = useQueryClient();
  const [userId, setUserId] = useState("");
  const [access, setAccess] = useState<ProjectMember["access"]>("write");
  const [error, setError] = useState("");

  const members = useQuery({
    queryKey: ["project-members", projectId],
    queryFn: () => api<ProjectMember[]>(`/api/projects/${projectId}/members`),
  });
  const staff = useQuery({
    queryKey: ["users", "all"],
    queryFn: () => api<UserList>("/api/users/?limit=100"),
    enabled: canEdit,
  });

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["project-members", projectId] });

  const add = useMutation({
    mutationFn: () =>
      api(`/api/projects/${projectId}/members`, {
        method: "POST",
        body: { user_id: userId, access },
      }),
    onSuccess: () => {
      setError("");
      setUserId("");
      invalidate();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Не удалось добавить участника"),
  });

  const remove = useMutation({
    mutationFn: (memberId: string) =>
      api(`/api/projects/${projectId}/members/${memberId}`, { method: "DELETE" }),
    onSuccess: () => {
      setError("");
      invalidate();
    },
    onError: (err) =>
      setError(
        err instanceof Error ? err.message : "Не удалось убрать участника",
      ),
  });

  const items = members.data ?? [];
  const candidates = (staff.data?.items ?? []).filter(
    (person: User) => !items.some((member) => member.user_id === person.id),
  );

  return (
    <div className="space-y-3 pt-4 border-t border-outline-variant">
      <h4 className="text-sm font-semibold">Участники проекта</h4>

      {members.isLoading && <Skeleton className="h-10" />}

      {members.isError && (
        <ErrorNote message="Не удалось загрузить участников проекта" />
      )}

      {/* Пустой список означает «проект открыт всем» — важное правило доступа,
          и путать его с несработавшей загрузкой нельзя. */}
      {!members.isLoading && !members.isError && items.length === 0 && (
        <p className="text-sm text-on-surface-variant">
          Участники не назначены — проект виден всем сотрудникам организации
          в рамках их роли.
        </p>
      )}

      {items.map((member) => (
        <div
          key={member.id}
          className="flex items-center justify-between gap-3 rounded-lg border border-outline-variant px-3 py-2"
        >
          <div className="min-w-0">
            <p className="text-sm font-medium truncate">
              {member.full_name || member.email}
            </p>
            <p className="text-xs text-on-surface-variant">
              {ROLE_LABELS[member.role ?? ""] ?? member.role}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Chip tone="neutral">{ACCESS_LABELS[member.access]}</Chip>
            {canEdit && (
              <ConfirmButton
                onConfirm={() => remove.mutate(member.id)}
                confirmLabel="Убрать"
                disabled={remove.isPending}
                title="Убрать участника"
              >
                <Trash2 size={16} />
              </ConfirmButton>
            )}
          </div>
        </div>
      ))}

      {error && <ErrorNote message={error} />}

      {canEdit && staff.isError && (
        <ErrorNote message="Не удалось загрузить список сотрудников" />
      )}

      {canEdit && !staff.isError && candidates.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-2 items-end">
          <Select
            value={userId}
            onChange={(event) => setUserId(event.target.value)}
          >
            <option value="">Выберите сотрудника</option>
            {candidates.map((person: User) => (
              <option key={person.id} value={person.id}>
                {person.full_name || person.email}
              </option>
            ))}
          </Select>
          <Select
            value={access}
            onChange={(event) =>
              setAccess(event.target.value as ProjectMember["access"])
            }
          >
            {(Object.keys(ACCESS_LABELS) as Array<ProjectMember["access"]>).map(
              (key) => (
                <option key={key} value={key}>
                  {ACCESS_LABELS[key]}
                </option>
              ),
            )}
          </Select>
          <Button
            variant="secondary"
            onClick={() => add.mutate()}
            disabled={!userId || add.isPending}
          >
            <span className="flex items-center gap-2">
              <UserPlus size={16} /> Добавить
            </span>
          </Button>
        </div>
      )}
    </div>
  );
}
