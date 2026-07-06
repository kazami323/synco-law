"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  ArrowLeft,
  CalendarClock,
  CheckCircle2,
  Download,
  FileSignature,
  History,
  Languages,
  Pencil,
  Plus,
  QrCode,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type {
  ContractDeadline,
  ContractDetail,
  ContractVersion,
  SignConfirm,
  SignRequest,
} from "@/lib/types";
import { Button, Card, Chip, ErrorNote, Input, Modal, Select } from "@/components/ui";
import { RiskChip, StatusChip, TypeChip } from "@/components/contract-chips";
import { AnalysisSection } from "@/components/analysis-section";
import { TranslateModal } from "@/components/translate-modal";
import { WorkflowPanel } from "@/components/workflow-panel";

const DEADLINE_LABELS: Record<string, string> = {
  payment: "Оплата",
  delivery: "Поставка",
  report: "Отчет",
  other: "Другое",
};

function deadlineText(daysLeft: number) {
  if (daysLeft < 0) return `Просрочено на ${Math.abs(daysLeft)} дн.`;
  if (daysLeft === 0) return "Сегодня";
  return `${daysLeft} дн.`;
}

function formatDateOnly(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("ru-RU");
}

export default function ContractPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const qc = useQueryClient();
  const [editOpen, setEditOpen] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [signOpen, setSignOpen] = useState(false);
  const [translateOpen, setTranslateOpen] = useState(false);
  const [signRequestData, setSignRequestData] = useState<SignRequest | null>(null);
  const [pin, setPin] = useState("");
  const [signError, setSignError] = useState("");

  const contract = useQuery({
    queryKey: ["contract", id],
    queryFn: () => api<ContractDetail>(`/api/contracts/${id}`),
  });
  const versions = useQuery({
    queryKey: ["contract-versions", id],
    queryFn: () => api<ContractVersion[]>(`/api/contracts/${id}/versions`),
  });

  const signRequest = useMutation({
    mutationFn: () => api<SignRequest>(`/api/contracts/${id}/sign-request`, { method: "POST" }),
    onSuccess: (data) => setSignRequestData(data),
    onError: (err) =>
      setSignError(err instanceof Error ? err.message : "Не удалось создать запрос подписи"),
  });

  const signConfirm = useMutation({
    mutationFn: () =>
      api<SignConfirm>(`/api/contracts/${id}/sign-confirm`, {
        method: "POST",
        body: { request_id: signRequestData?.request_id, pin: pin || null },
      }),
    onSuccess: () => {
      setSignOpen(false);
      setSignRequestData(null);
      setPin("");
      qc.invalidateQueries({ queryKey: ["contract", id] });
      qc.invalidateQueries({ queryKey: ["workflow", id] });
      qc.invalidateQueries({ queryKey: ["contracts"] });
      qc.invalidateQueries({ queryKey: ["dashboard-metrics"] });
    },
    onError: (err) =>
      setSignError(err instanceof Error ? err.message : "Не удалось подтвердить подпись"),
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

  function openSignModal() {
    setSignOpen(true);
    setSignError("");
    setSignRequestData(null);
    setPin("");
    signRequest.mutate();
  }

  if (contract.isLoading) {
    return (
      <div className="max-w-6xl space-y-4">
        <div className="h-8 w-64 rounded-lg bg-surface-container animate-pulse" />
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <div className="xl:col-span-2 h-96 rounded-xl bg-surface-container animate-pulse" />
          <div className="h-96 rounded-xl bg-surface-container animate-pulse" />
        </div>
      </div>
    );
  }
  if (contract.error || !contract.data) {
    return (
      <ErrorNote
        message={
          contract.error instanceof Error
            ? contract.error.message
            : "Контракт не найден"
        }
      />
    );
  }

  const c = contract.data;
  const canArchive = user?.role === "admin" && c.status !== "archived";
  const canSign = user?.role === "admin" && c.status === "ready_to_sign";

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
        <div className="flex flex-wrap gap-2">
          {canSign && (
            <Button onClick={openSignModal} disabled={signRequest.isPending}>
              <span className="flex items-center gap-2">
                <FileSignature size={16} /> Подписать
              </span>
            </Button>
          )}
          {c.file_path && (
            <Button variant="secondary" onClick={download}>
              <span className="flex items-center gap-2">
                <Download size={16} /> Исходный файл
              </span>
            </Button>
          )}
          {c.content && (
            <Button variant="secondary" onClick={() => setTranslateOpen(true)}>
              <span className="flex items-center gap-2">
                <Languages size={16} /> Перевести
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

      {c.signature_timestamp && (
        <div className="mt-5 rounded-xl border border-success/30 bg-success/10 px-5 py-4 flex flex-wrap items-center gap-3 text-sm">
          <CheckCircle2 size={18} className="text-success" />
          <span className="font-medium text-success">
            Подписано {new Date(c.signature_timestamp).toLocaleString("ru-RU")}
          </span>
          {c.certificate_thumbprint && (
            <span className="text-on-surface-variant">
              Сертификат: {c.certificate_thumbprint}
            </span>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 mt-6">
        <div className="xl:col-span-2 space-y-6">
          <Card className="p-6">
            <h2 className="font-semibold mb-4">Реквизиты</h2>
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3 text-sm">
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
                <dt className="text-on-surface-variant">Обновлен</dt>
                <dd className="font-medium mt-0.5">
                  {new Date(c.updated_at).toLocaleString("ru-RU")}
                </dd>
              </div>
            </dl>
          </Card>

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

          <AnalysisSection contractId={c.id} />
        </div>

        <div className="space-y-6">
          <WorkflowPanel contractId={c.id} />
          <DeadlinesPanel contractId={c.id} />

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
      </div>

      {editOpen && (
        <EditModal contract={c} onClose={() => setEditOpen(false)} />
      )}

      {translateOpen && (
        <TranslateModal contractId={c.id} onClose={() => setTranslateOpen(false)} />
      )}

      {signOpen && (
        <Modal title="E-IMZO подпись" onClose={() => setSignOpen(false)}>
          <div className="space-y-4">
            <div className="rounded-xl border border-outline-variant bg-surface-container-low p-4 flex items-center gap-4">
              <div className="w-24 h-24 rounded-lg bg-surface-container-lowest border border-outline-variant flex items-center justify-center text-primary">
                <QrCode size={52} />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-semibold">Запрос на подпись</div>
                <div className="text-xs text-on-surface-variant mt-1 break-all">
                  {signRequestData?.hash ?? "Создаем хеш контракта..."}
                </div>
              </div>
            </div>
            <Input
              label="PIN E-IMZO"
              type="password"
              inputMode="numeric"
              value={pin}
              onChange={(event) => setPin(event.target.value)}
              placeholder="123456"
            />
            {signError && <ErrorNote message={signError} />}
            <Button
              className="w-full"
              disabled={!signRequestData}
              loading={signConfirm.isPending}
              onClick={() => {
                setSignError("");
                signConfirm.mutate();
              }}
            >
              <span className="flex items-center justify-center gap-2">
                {!signConfirm.isPending && <ShieldCheck size={16} />}
                {signConfirm.isPending ? "Подписываем..." : "Подтвердить подпись"}
              </span>
            </Button>
          </div>
        </Modal>
      )}

      {confirmArchive && (
        <Modal title="Отправить в архив?" onClose={() => setConfirmArchive(false)}>
          <p className="text-sm text-on-surface-variant">
            Контракт «{c.title}» будет переведен в статус «В архиве». Данные и
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

function DeadlinesPanel({ contractId }: { contractId: string }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ deadline_date: "", type: "payment" });
  const [error, setError] = useState("");

  const deadlines = useQuery({
    queryKey: ["contract-deadlines", contractId],
    queryFn: () => api<ContractDeadline[]>(`/api/contracts/${contractId}/deadlines`),
  });

  const create = useMutation({
    mutationFn: () =>
      api<ContractDeadline>(`/api/contracts/${contractId}/deadlines`, {
        method: "POST",
        body: form,
      }),
    onSuccess: () => {
      setOpen(false);
      setForm({ deadline_date: "", type: "payment" });
      qc.invalidateQueries({ queryKey: ["contract-deadlines", contractId] });
      qc.invalidateQueries({ queryKey: ["dashboard-metrics"] });
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Не удалось добавить срок"),
  });

  return (
    <Card className="p-6 h-fit">
      <div className="flex items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-2 font-semibold">
          <CalendarClock size={18} />
          Критичные сроки
        </div>
        <Button variant="secondary" className="px-3" onClick={() => setOpen(true)}>
          <Plus size={16} />
        </Button>
      </div>

      {deadlines.isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((item) => (
            <div key={item} className="h-12 rounded-lg bg-surface-container animate-pulse" />
          ))}
        </div>
      ) : deadlines.error ? (
        <ErrorNote
          message={
            deadlines.error instanceof Error
              ? deadlines.error.message
              : "Не удалось загрузить сроки"
          }
        />
      ) : deadlines.data && deadlines.data.length > 0 ? (
        <div className="space-y-2">
          {deadlines.data.map((deadline) => {
            const urgent = deadline.days_left < 7;
            return (
              <div
                key={deadline.id}
                className={`rounded-lg border px-3 py-2 text-sm ${
                  urgent
                    ? "border-error/30 bg-error-container/60"
                    : "border-outline-variant"
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="font-medium">
                    {formatDateOnly(deadline.deadline_date)}
                  </span>
                  <Chip tone={urgent ? "error" : "neutral"}>
                    {deadlineText(deadline.days_left)}
                  </Chip>
                </div>
                <div className="text-xs text-on-surface-variant mt-1">
                  {DEADLINE_LABELS[deadline.type] ?? deadline.type}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-sm text-on-surface-variant">
          Сроки не найдены. Их можно добавить вручную после проверки текста.
        </p>
      )}

      {open && (
        <Modal title="Добавить срок" onClose={() => setOpen(false)}>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              setError("");
              create.mutate();
            }}
          >
            <Input
              label="Дата"
              type="date"
              value={form.deadline_date}
              onChange={(event) =>
                setForm({ ...form, deadline_date: event.target.value })
              }
              required
            />
            <Select
              label="Тип"
              value={form.type}
              onChange={(event) => setForm({ ...form, type: event.target.value })}
            >
              <option value="payment">Оплата</option>
              <option value="delivery">Поставка</option>
              <option value="report">Отчет</option>
              <option value="other">Другое</option>
            </Select>
            {error && <ErrorNote message={error} />}
            <Button type="submit" loading={create.isPending} className="w-full">
              {create.isPending ? "Добавляем..." : "Добавить"}
            </Button>
          </form>
        </Modal>
      )}
    </Card>
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
      qc.invalidateQueries({ queryKey: ["contract-deadlines", contract.id] });
      qc.invalidateQueries({ queryKey: ["contracts"] });
      qc.invalidateQueries({ queryKey: ["dashboard-metrics"] });
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
          label="Что изменилось"
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
