"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, FolderKanban, Pencil, Plus } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import type { Contract, Project } from "@/lib/types";
import {
  Button,
  Card,
  Chip,
  EmptyState,
  ErrorNote,
  Input,
  Modal,
  Skeleton,
} from "@/components/ui";
import { RiskChip, StatusChip, TypeChip } from "@/components/contract-chips";
import { CreateContractModal } from "@/components/create-contract-modal";

interface ContractList {
  total: number;
  page: number;
  items: Contract[];
}

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const canCreate = can(user, "create");

  const project = useQuery({
    queryKey: ["project", id],
    queryFn: () => api<Project>(`/api/projects/${id}`),
  });
  const contracts = useQuery({
    queryKey: ["contracts", "project", id],
    queryFn: () =>
      api<ContractList>(`/api/contracts/?project_id=${id}&limit=100`),
  });

  const toggleStatus = useMutation({
    mutationFn: () =>
      api<Project>(`/api/projects/${id}`, {
        method: "PATCH",
        body: {
          status: project.data?.status === "active" ? "closed" : "active",
        },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["project", id] });
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });

  if (project.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40" />
      </div>
    );
  }
  if (!project.data) {
    return (
      <Card>
        <EmptyState title="Проект не найден" />
      </Card>
    );
  }
  const p = project.data;

  return (
    <div>
      <button
        onClick={() => router.push("/projects")}
        className="flex items-center gap-1.5 text-sm text-on-surface-variant hover:text-primary cursor-pointer"
      >
        <ArrowLeft size={16} /> Все проекты
      </button>

      <div className="flex flex-wrap items-start justify-between gap-3 mt-3">
        <div className="flex items-start gap-3 min-w-0">
          <div className="w-11 h-11 rounded-lg bg-primary-fixed text-primary flex items-center justify-center shrink-0">
            <FolderKanban size={22} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-2xl font-semibold">{p.name}</h1>
              <Chip tone={p.status === "active" ? "success" : "neutral"}>
                {p.status === "active" ? "Активен" : "Закрыт"}
              </Chip>
            </div>
            <p className="text-sm text-on-surface-variant mt-0.5">
              {p.client || "Заказчик не указан"} ·{" "}
              {new Date(p.created_at).toLocaleDateString("ru-RU")}
            </p>
          </div>
        </div>
        {canCreate && (
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setEditOpen(true)}>
              <Pencil size={16} /> Изменить
            </Button>
            <Button
              variant="secondary"
              onClick={() => toggleStatus.mutate()}
              disabled={toggleStatus.isPending}
            >
              {p.status === "active" ? "Закрыть проект" : "Открыть заново"}
            </Button>
          </div>
        )}
      </div>

      {p.description && (
        <Card className="p-4 mt-4 text-sm text-on-surface-variant whitespace-pre-wrap">
          {p.description}
        </Card>
      )}

      <Card className="mt-6 overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 bg-surface-container-low border-b border-outline-variant">
          <h2 className="font-semibold">
            Договоры и документы ({contracts.data?.total ?? 0})
          </h2>
          {canCreate && p.status === "active" && (
            <Button onClick={() => setCreateOpen(true)}>
              <Plus size={16} /> Договор
            </Button>
          )}
        </div>
        {contracts.isLoading ? (
          <div className="p-6 space-y-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-12" />
            ))}
          </div>
        ) : contracts.data && contracts.data.items.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-on-surface-variant">
                  <th className="px-6 py-3">Название</th>
                  <th className="px-6 py-3">Тип</th>
                  <th className="px-6 py-3">Риск</th>
                  <th className="px-6 py-3">Статус</th>
                  <th className="px-6 py-3">Создан</th>
                </tr>
              </thead>
              <tbody>
                {contracts.data.items.map((c) => (
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
                    <td className="px-6 py-4">
                      <RiskChip score={c.risk_score} />
                    </td>
                    <td className="px-6 py-4">
                      <StatusChip status={c.status} />
                    </td>
                    <td className="px-6 py-4">
                      {new Date(c.created_at).toLocaleDateString("ru-RU")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="В проекте пока нет договоров"
            hint="Создайте первый — из файла, текста или с помощью AI"
            action={
              canCreate && p.status === "active" ? (
                <Button onClick={() => setCreateOpen(true)}>
                  <Plus size={16} /> Создать договор
                </Button>
              ) : undefined
            }
          />
        )}
      </Card>

      {createOpen && (
        <CreateContractModal
          onClose={() => {
            setCreateOpen(false);
            qc.invalidateQueries({ queryKey: ["contracts", "project", id] });
            qc.invalidateQueries({ queryKey: ["project", id] });
          }}
          projectId={id}
        />
      )}
      {editOpen && (
        <EditProjectModal project={p} onClose={() => setEditOpen(false)} />
      )}
    </div>
  );
}

function EditProjectModal({
  project,
  onClose,
}: {
  project: Project;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    name: project.name,
    client: project.client ?? "",
    description: project.description ?? "",
  });
  const [error, setError] = useState("");

  const save = useMutation({
    mutationFn: () =>
      api<Project>(`/api/projects/${project.id}`, {
        method: "PATCH",
        body: {
          name: form.name,
          client: form.client,
          description: form.description,
        },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["project", project.id] });
      qc.invalidateQueries({ queryKey: ["projects"] });
      onClose();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Ошибка сохранения"),
  });

  return (
    <Modal title="Изменить проект" onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <Input
          label="Название"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          required
        />
        <Input
          label="Заказчик"
          value={form.client}
          onChange={(e) => setForm({ ...form, client: e.target.value })}
        />
        <div>
          <label className="block text-sm font-medium mb-1.5">Описание</label>
          <textarea
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            rows={3}
            className="w-full rounded-lg bg-surface-container-lowest border border-outline-variant px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary-fixed placeholder:text-outline"
          />
        </div>
        {error && <ErrorNote message={error} />}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" type="button" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" disabled={save.isPending || !form.name.trim()}>
            {save.isPending ? "Сохраняем..." : "Сохранить"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
