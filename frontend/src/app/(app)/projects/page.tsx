"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderKanban, Plus, Search } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import type { Project } from "@/lib/types";
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

export default function ProjectsPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [q, setQ] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const canCreate = can(user, "create");

  const projects = useQuery({
    queryKey: ["projects", q],
    queryFn: () =>
      api<Project[]>(`/api/projects/${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  });

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Проекты</h1>
          <p className="text-on-surface-variant text-sm mt-1">
            Дела и заказы: договоры и документы одного клиента — в одной папке.
          </p>
        </div>
        {canCreate && (
          <Button onClick={() => setCreateOpen(true)}>
            <Plus size={18} /> Новый проект
          </Button>
        )}
      </div>

      <div className="relative max-w-md mt-6">
        <Search
          size={18}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-outline"
        />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Название проекта или заказчик..."
          className="w-full h-10 pl-10 pr-3 rounded-lg bg-surface-container-lowest border border-outline-variant text-sm outline-none focus:ring-2 focus:ring-primary-fixed placeholder:text-outline"
        />
      </div>

      {projects.isLoading ? (
        <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4 mt-6">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-40" />
          ))}
        </div>
      ) : projects.data && projects.data.length > 0 ? (
        <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4 mt-6">
          {projects.data.map((project) => (
            <Card
              key={project.id}
              className="group p-5 cursor-pointer transition-all hover:-translate-y-0.5 hover:border-primary hover:shadow-sm"
              onClick={() => router.push(`/projects/${project.id}`)}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="w-10 h-10 rounded-lg bg-primary-fixed text-primary flex items-center justify-center shrink-0 transition-colors group-hover:bg-primary group-hover:text-on-primary">
                  <FolderKanban size={20} />
                </div>
                <Chip tone={project.status === "active" ? "success" : "neutral"}>
                  {project.status === "active" ? "Активен" : "Закрыт"}
                </Chip>
              </div>
              <div className="font-semibold mt-3 line-clamp-1">{project.name}</div>
              <div className="text-sm text-on-surface-variant mt-0.5 line-clamp-1">
                {project.client || "Заказчик не указан"}
              </div>
              <div className="flex items-center justify-between text-sm text-on-surface-variant mt-4 pt-3 border-t border-outline-variant">
                <span>
                  {project.contracts_count}{" "}
                  {plural(project.contracts_count, "договор", "договора", "договоров")}
                </span>
                <span>
                  {new Date(project.created_at).toLocaleDateString("ru-RU")}
                </span>
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <Card className="mt-6">
          <EmptyState
            title={q ? "Ничего не найдено" : "Проектов пока нет"}
            hint={
              q
                ? "Попробуйте другое название"
                : "Создайте первый проект — например, под новый заказ клиента"
            }
          />
        </Card>
      )}

      {createOpen && <CreateProjectModal onClose={() => setCreateOpen(false)} />}
    </div>
  );
}

function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

function CreateProjectModal({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [form, setForm] = useState({ name: "", client: "", description: "" });
  const [error, setError] = useState("");

  const create = useMutation({
    mutationFn: () =>
      api<Project>("/api/projects/", {
        method: "POST",
        body: {
          name: form.name,
          client: form.client || null,
          description: form.description || null,
        },
      }),
    onSuccess: (project) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      onClose();
      router.push(`/projects/${project.id}`);
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Ошибка создания"),
  });

  return (
    <Modal title="Новый проект" onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <Input
          label="Название"
          placeholder="Например: Сопровождение сделки — Проект1"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          required
        />
        <Input
          label="Заказчик"
          placeholder="ООО Клиент"
          value={form.client}
          onChange={(e) => setForm({ ...form, client: e.target.value })}
        />
        <div>
          <label className="block text-sm font-medium mb-1.5">Описание</label>
          <textarea
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="Что за заказ, что входит в работу..."
            rows={3}
            className="w-full rounded-lg bg-surface-container-lowest border border-outline-variant px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary-fixed placeholder:text-outline"
          />
        </div>
        {error && <ErrorNote message={error} />}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" type="button" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" disabled={create.isPending || !form.name.trim()}>
            {create.isPending ? "Создаём..." : "Создать проект"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
