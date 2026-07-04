"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  ArrowLeft,
  Download,
  History,
  Pencil,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ContractDetail, ContractVersion } from "@/lib/types";
import {
  Button,
  Card,
  ErrorNote,
  Input,
  Modal,
} from "@/components/ui";
import { RiskChip, StatusChip, TypeChip } from "@/components/contract-chips";
import { AnalysisSection } from "@/components/analysis-section";

export default function ContractPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const qc = useQueryClient();
  const [editOpen, setEditOpen] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);

  const contract = useQuery({
    queryKey: ["contract", id],
    queryFn: () => api<ContractDetail>(`/api/contracts/${id}`),
  });
  const versions = useQuery({
    queryKey: ["contract-versions", id],
    queryFn: () => api<ContractVersion[]>(`/api/contracts/${id}/versions`),
  });

  const archive = useMutation({
    mutationFn: () => api(`/api/contracts/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["contracts"] });
      qc.invalidateQueries({ queryKey: ["contract", id] });
      setConfirmArchive(false);
    },
  });

  async function download() {
    const { url } = await api<{ url: string }>(`/api/contracts/${id}/download`);
    window.open(url, "_blank");
  }

  if (contract.isLoading) {
    return <div className="text-on-surface-variant">Загрузка...</div>;
  }
  if (contract.error || !contract.data) {
    return (
      <div>
        <ErrorNote
          message={
            contract.error instanceof Error
              ? contract.error.message
              : "Контракт не найден"
          }
        />
      </div>
    );
  }

  const c = contract.data;
  const canArchive = user?.role === "admin" && c.status !== "archived";

  return (
    <div className="max-w-6xl">
      <Link
        href="/contracts"
        className="inline-flex items-center gap-1.5 text-sm text-on-surface-variant hover:text-primary"
      >
        <ArrowLeft size={16} /> Все контракты
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4 mt-3">
        <div>
          <h1 className="text-2xl font-semibold">{c.title}</h1>
          <div className="flex flex-wrap items-center gap-2 mt-2">
            <TypeChip type={c.contract_type} />
            <StatusChip status={c.status} />
            <RiskChip score={c.risk_score} />
          </div>
        </div>
        <div className="flex gap-2">
          {c.file_path && (
            <Button variant="secondary" onClick={download}>
              <span className="flex items-center gap-2">
                <Download size={16} /> Исходный файл
              </span>
            </Button>
          )}
          <Button variant="secondary" onClick={() => setEditOpen(true)}>
            <span className="flex items-center gap-2">
              <Pencil size={16} /> Редактировать
            </span>
          </Button>
          {canArchive && (
            <Button variant="danger" onClick={() => setConfirmArchive(true)}>
              <span className="flex items-center gap-2">
                <Archive size={16} /> В архив
              </span>
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 mt-6">
        <div className="xl:col-span-2 space-y-6">
          {/* Реквизиты */}
          <Card className="p-6">
            <h2 className="font-semibold mb-4">Реквизиты</h2>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
              <div>
                <dt className="text-on-surface-variant">Контрагент</dt>
                <dd className="font-medium mt-0.5">{c.counterparty ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-on-surface-variant">Сумма</dt>
                <dd className="font-medium mt-0.5">
                  {c.amount
                    ? `${Number(c.amount).toLocaleString("ru-RU")} ${c.currency}`
                    : "—"}
                </dd>
              </div>
              <div>
                <dt className="text-on-surface-variant">Создан</dt>
                <dd className="font-medium mt-0.5">
                  {new Date(c.created_at).toLocaleString("ru-RU")}
                </dd>
              </div>
              <div>
                <dt className="text-on-surface-variant">Обновлён</dt>
                <dd className="font-medium mt-0.5">
                  {new Date(c.updated_at).toLocaleString("ru-RU")}
                </dd>
              </div>
            </dl>
          </Card>

          {/* Текст контракта */}
          <Card className="p-6">
            <h2 className="font-semibold mb-4">Текст контракта</h2>
            {c.content ? (
              <pre className="whitespace-pre-wrap text-sm font-body leading-relaxed max-h-[32rem] overflow-y-auto">
                {c.content}
              </pre>
            ) : (
              <p className="text-sm text-on-surface-variant">
                Текст не заполнен. Нажмите «Редактировать», чтобы добавить.
              </p>
            )}
          </Card>

          {/* AI-анализ */}
          <AnalysisSection contractId={c.id} />
        </div>

        {/* История версий */}
        <Card className="p-6 h-fit">
          <div className="flex items-center gap-2 font-semibold mb-4">
            <History size={18} />
            История версий
          </div>
          <div className="space-y-3">
            {versions.data?.map((v) => (
              <div
                key={v.id}
                className="border border-outline-variant rounded-lg p-3"
              >
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">Версия {v.version_number}</span>
                  <span className="text-xs text-on-surface-variant">
                    {new Date(v.created_at).toLocaleDateString("ru-RU")}
                  </span>
                </div>
                {v.changes_description && (
                  <p className="text-xs text-on-surface-variant mt-1">
                    {v.changes_description}
                  </p>
                )}
              </div>
            ))}
          </div>
        </Card>
      </div>

      {editOpen && (
        <EditModal contract={c} onClose={() => setEditOpen(false)} />
      )}

      {confirmArchive && (
        <Modal title="Отправить в архив?" onClose={() => setConfirmArchive(false)}>
          <p className="text-sm text-on-surface-variant">
            Контракт «{c.title}» будет переведён в статус «В архиве». Данные и
            история версий сохранятся.
          </p>
          <div className="flex justify-end gap-2 mt-6">
            <Button variant="secondary" onClick={() => setConfirmArchive(false)}>
              Отмена
            </Button>
            <Button
              variant="danger"
              disabled={archive.isPending}
              onClick={() => archive.mutate()}
            >
              {archive.isPending ? "Архивируем..." : "В архив"}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function EditModal({
  contract,
  onClose,
}: {
  contract: ContractDetail;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    title: contract.title,
    counterparty: contract.counterparty ?? "",
    content: contract.content ?? "",
    changes_description: "",
  });
  const [error, setError] = useState("");

  const save = useMutation({
    mutationFn: () =>
      api(`/api/contracts/${contract.id}`, {
        method: "PUT",
        body: {
          title: form.title,
          counterparty: form.counterparty || null,
          content: form.content || null,
          changes_description: form.changes_description || null,
        },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["contract", contract.id] });
      qc.invalidateQueries({ queryKey: ["contract-versions", contract.id] });
      qc.invalidateQueries({ queryKey: ["contracts"] });
      onClose();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Ошибка сохранения"),
  });

  return (
    <Modal title="Редактировать контракт" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError("");
          save.mutate();
        }}
        className="space-y-4"
      >
        <Input
          label="Название"
          value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
          required
        />
        <Input
          label="Контрагент"
          value={form.counterparty}
          onChange={(e) => setForm({ ...form, counterparty: e.target.value })}
        />
        <label className="block">
          <span className="block text-[13px] font-semibold mb-1.5">
            Текст контракта
          </span>
          <textarea
            value={form.content}
            onChange={(e) => setForm({ ...form, content: e.target.value })}
            rows={10}
            className="w-full px-3 py-2 rounded-lg border border-outline-variant bg-surface-container-lowest text-sm outline-none focus:border-primary"
          />
        </label>
        <Input
          label="Что изменилось (для истории версий)"
          placeholder="Правка раздела 3: сроки оплаты"
          value={form.changes_description}
          onChange={(e) =>
            setForm({ ...form, changes_description: e.target.value })
          }
        />
        {error && <ErrorNote message={error} />}
        <Button type="submit" disabled={save.isPending} className="w-full">
          {save.isPending ? "Сохраняем..." : "Сохранить"}
        </Button>
      </form>
    </Modal>
  );
}
