"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Eye, Plus, Scale, Shield, UserCog } from "lucide-react";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Organization, User, UserList } from "@/lib/types";
import { ROLE_LABELS } from "@/lib/types";
import {
  Button,
  Card,
  Chip,
  EmptyState,
  ErrorNote,
  Input,
  Modal,
  Select,
} from "@/components/ui";

const AVATAR_COLORS = [
  "bg-primary text-on-primary",
  "bg-warning text-on-primary",
  "bg-success text-on-primary",
  "bg-on-secondary-container text-on-primary",
];

function initials(u: User) {
  const source = u.full_name || u.username;
  return source
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}

export default function SettingsPage() {
  const { user: me } = useAuth();
  const qc = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);

  const org = useQuery({
    queryKey: ["org"],
    queryFn: () => api<Organization>("/api/organizations/me"),
  });
  const users = useQuery({
    queryKey: ["users"],
    queryFn: () => api<UserList>("/api/users/?limit=100"),
    retry: false,
  });

  const canManage = me && ["admin", "head"].includes(me.role);

  const patchUser = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api(`/api/users/${id}`, { method: "PATCH", body }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });

  return (
    <div className="max-w-5xl">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Роли и доступ</h1>
          <p className="text-on-surface-variant text-sm mt-1">
            {org.data
              ? `Организация: ${org.data.name}`
              : "Управление сотрудниками и уровнями доступа."}
          </p>
        </div>
        {canManage && (
          <Button onClick={() => setModalOpen(true)}>
            <span className="flex items-center gap-2">
              <Plus size={16} /> Добавить пользователя
            </span>
          </Button>
        )}
      </div>

      {/* Сотрудники */}
      <Card className="mt-6 overflow-hidden">
        <div className="px-6 py-4 bg-surface-container-low border-b border-outline-variant font-semibold">
          Активные пользователи
        </div>
        {users.error ? (
          <EmptyState
            title="Недостаточно прав"
            hint="Список сотрудников доступен администраторам и руководителям"
          />
        ) : users.data && users.data.items.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-on-surface-variant">
                <th className="px-6 py-3">Имя</th>
                <th className="px-6 py-3">Email</th>
                <th className="px-6 py-3">Роль</th>
                {canManage && <th className="px-6 py-3 text-right">Действия</th>}
              </tr>
            </thead>
            <tbody>
              {users.data.items.map((u, i) => (
                <tr key={u.id} className="border-t border-outline-variant">
                  <td className="px-6 py-3">
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-9 h-9 rounded-full flex items-center justify-center text-xs font-semibold ${AVATAR_COLORS[i % AVATAR_COLORS.length]}`}
                      >
                        {initials(u)}
                      </div>
                      <div>
                        <div className="font-medium">
                          {u.full_name || u.username}
                          {u.id === me?.id && (
                            <span className="text-outline"> (вы)</span>
                          )}
                        </div>
                        {!u.is_active && (
                          <Chip tone="error">Деактивирован</Chip>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-3 text-on-surface-variant">{u.email}</td>
                  <td className="px-6 py-3">
                    {canManage && u.id !== me?.id ? (
                      <Select
                        value={u.role}
                        onChange={(e) =>
                          patchUser.mutate({
                            id: u.id,
                            body: { role: e.target.value },
                          })
                        }
                        className="w-44 h-9"
                      >
                        {Object.entries(ROLE_LABELS).map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </Select>
                    ) : (
                      <Chip tone={u.role === "admin" ? "info" : "neutral"}>
                        {ROLE_LABELS[u.role] ?? u.role}
                      </Chip>
                    )}
                  </td>
                  {canManage && (
                    <td className="px-6 py-3 text-right">
                      {u.id !== me?.id && (
                        <Button
                          variant={u.is_active ? "danger" : "secondary"}
                          className="h-9"
                          onClick={() =>
                            patchUser.mutate({
                              id: u.id,
                              body: { is_active: !u.is_active },
                            })
                          }
                        >
                          {u.is_active ? "Деактивировать" : "Активировать"}
                        </Button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState title="Загрузка..." />
        )}
      </Card>

      {/* Обзор ролей */}
      <Card className="mt-6 p-6">
        <h2 className="font-semibold mb-4">Обзор системных ролей</h2>
        <div className="grid md:grid-cols-2 gap-4">
          {[
            {
              icon: Shield,
              title: "Администратор",
              text: "Полный доступ: настройки, пользователи, контракты, подписание.",
            },
            {
              icon: UserCog,
              title: "Руководитель",
              text: "Видит всю работу команды, согласует критичные этапы, управляет сотрудниками.",
            },
            {
              icon: Scale,
              title: "Юрист",
              text: "Создание и редактирование контрактов, работа с AI-агентами по своим задачам.",
            },
            {
              icon: Eye,
              title: "Внешний (просмотр)",
              text: "Только чтение выданных документов. Без права редактирования и согласования.",
            },
          ].map(({ icon: Icon, title, text }) => (
            <div
              key={title}
              className="border border-outline-variant rounded-xl p-4"
            >
              <div className="flex items-center gap-2 font-medium">
                <Icon size={18} className="text-primary" />
                {title}
              </div>
              <p className="text-sm text-on-surface-variant mt-2">{text}</p>
            </div>
          ))}
        </div>
      </Card>

      {/* Комплаенс-политики (Phase 2) */}
      {canManage && org.data && <PoliciesCard org={org.data} />}

      {modalOpen && <AddUserModal onClose={() => setModalOpen(false)} />}
    </div>
  );
}

function PoliciesCard({ org }: { org: Organization }) {
  const qc = useQueryClient();
  const [text, setText] = useState(org.compliance_policies ?? "");
  const [saved, setSaved] = useState(false);

  const save = useMutation({
    mutationFn: () =>
      api<Organization>("/api/organizations/me", {
        method: "PUT",
        body: { compliance_policies: text },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["org"] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  return (
    <Card className="mt-6 p-6">
      <div className="flex items-center gap-2 font-semibold">
        <BadgeCheck size={18} className="text-primary" />
        Комплаенс-политики организации
      </div>
      <p className="text-sm text-on-surface-variant mt-1 mb-4">
        Внутренние правила компании (лимиты предоплаты, запрещённые условия,
        требования к контрагентам). Compliance Agent проверяет каждый контракт
        по этим политикам при AI-анализе.
      </p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={7}
        placeholder={
          "Например:\n1. Предоплата поставщикам — не более 30%.\n2. Договоры дороже 500 млн UZS — только с банковской гарантией.\n3. Бессрочные договоры запрещены.\n4. Споры — только в судах Узбекистана."
        }
        className="w-full px-3 py-2 rounded-lg border border-outline-variant bg-surface-container-lowest text-sm outline-none focus:border-primary placeholder:text-outline"
      />
      <div className="flex items-center justify-end gap-3 mt-3">
        {saved && (
          <span className="text-sm text-success">Сохранено</span>
        )}
        <Button
          loading={save.isPending}
          disabled={text === (org.compliance_policies ?? "")}
          onClick={() => save.mutate()}
        >
          Сохранить политики
        </Button>
      </div>
    </Card>
  );
}

function AddUserModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    username: "",
    password: "",
    role: "lawyer",
  });
  const [error, setError] = useState("");

  const create = useMutation({
    mutationFn: () => api("/api/users/", { method: "POST", body: form }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      onClose();
    },
    onError: (err) => {
      setError(
        err instanceof ApiError && err.status === 409
          ? "Пользователь с такой почтой или логином уже существует"
          : err instanceof Error
            ? err.message
            : "Ошибка"
      );
    },
  });

  function set(field: keyof typeof form) {
    return (
      e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
    ) => setForm({ ...form, [field]: e.target.value });
  }

  return (
    <Modal title="Добавить пользователя" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError("");
          create.mutate();
        }}
        className="space-y-4"
      >
        <Input label="ФИО" value={form.full_name} onChange={set("full_name")} />
        <Input
          label="Электронная почта"
          type="email"
          value={form.email}
          onChange={set("email")}
          required
        />
        <Input
          label="Логин"
          value={form.username}
          onChange={set("username")}
          required
        />
        <Input
          label="Временный пароль"
          value={form.password}
          onChange={set("password")}
          required
          minLength={8}
        />
        <Select label="Роль" value={form.role} onChange={set("role")}>
          {Object.entries(ROLE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
        {error && <ErrorNote message={error} />}
        <Button type="submit" disabled={create.isPending} className="w-full">
          {create.isPending ? "Создаём..." : "Создать пользователя"}
        </Button>
      </form>
    </Modal>
  );
}
