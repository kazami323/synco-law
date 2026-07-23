"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  ArrowLeft,
  Building2,
  CalendarClock,
  CalendarDays,
  CheckCircle2,
  Clock,
  Coins,
  Download,
  FileSignature,
  History,
  Languages,
  LayoutPanelLeft,
  Pencil,
  Plus,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { api, apiDownload } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import type {
  ContractDeadline,
  ContractDetail,
  ContractVersion,
  SignConfirm,
  SignRequest,
} from "@/lib/types";
import {
  Button,
  Card,
  Chip,
  ErrorNote,
  Input,
  Modal,
  Select,
  Spinner,
} from "@/components/ui";
import {
  RiskChip,
  StatusChip,
  TypeChip,
  TypeIcon,
} from "@/components/contract-chips";
import { AnalysisSection } from "@/components/analysis-section";
import { TranslateModal } from "@/components/translate-modal";
import { WorkflowPanel } from "@/components/workflow-panel";
import {
  eimzoAvailable,
  eimzoInit,
  listCertificates,
  signWithCertificate,
  type EimzoCertificate,
} from "@/lib/eimzo";

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
  const router = useRouter();
  const { user } = useAuth();
  const qc = useQueryClient();
  const [editOpen, setEditOpen] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [signOpen, setSignOpen] = useState(false);
  const [translateOpen, setTranslateOpen] = useState(false);
  const [signRequestData, setSignRequestData] = useState<SignRequest | null>(null);
  const [pin, setPin] = useState("");
  const [signError, setSignError] = useState("");
  // E-IMZO: null — ищем клиент; [] — клиент есть, ключей нет; false — не найден
  const [eimzoCerts, setEimzoCerts] = useState<EimzoCertificate[] | false | null>(null);
  const [selectedCert, setSelectedCert] = useState<EimzoCertificate | null>(null);
  const [eimzoSigning, setEimzoSigning] = useState(false);

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
    mutationFn: (body: Record<string, unknown>) =>
      api<SignConfirm>(`/api/contracts/${id}/sign-confirm`, {
        method: "POST",
        body: { request_id: signRequestData?.request_id, ...body },
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

  // Живая подпись через локальный клиент E-IMZO
  async function signWithEimzo() {
    if (!selectedCert || !signRequestData) return;
    setSignError("");
    setEimzoSigning(true);
    try {
      const { pkcs7, serial } = await signWithCertificate(
        selectedCert,
        signRequestData.hash
      );
      signConfirm.mutate({
        signature: pkcs7,
        certificate: selectedCert.alias,
        certificate_thumbprint: serial,
      });
    } catch (err) {
      setSignError(err instanceof Error ? err.message : "Ошибка подписи E-IMZO");
    } finally {
      setEimzoSigning(false);
    }
  }

  const archive = useMutation({
    mutationFn: () => api(`/api/contracts/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["contracts"] });
      qc.invalidateQueries({ queryKey: ["contract", id] });
      setConfirmArchive(false);
    },
  });

  async function download() {
    if (!c?.file_path) return;
    const filename = c.file_path.split("/").pop() || "document";
    await apiDownload(`/api/contracts/${id}/download`, filename);
  }

  function openSignModal() {
    setSignOpen(true);
    setSignError("");
    setSignRequestData(null);
    setPin("");
    setEimzoCerts(null);
    setSelectedCert(null);
    signRequest.mutate();
    // Параллельно ищем локальный клиент E-IMZO и ключи пользователя
    void (async () => {
      if (!(await eimzoAvailable())) {
        setEimzoCerts(false);
        return;
      }
      try {
        await eimzoInit();
        const certs = await listCertificates();
        setEimzoCerts(certs);
        if (certs.length === 1) setSelectedCert(certs[0]);
      } catch {
        setEimzoCerts(false);
      }
    })();
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
  const canEdit = can(user, "edit");
  const canArchive = can(user, "delete") && c.status !== "archived";
  const canSign = can(user, "sign") && c.status === "ready_to_sign";

  return (
    <div className="max-w-6xl">
      <Link
        href="/contracts"
        className="inline-flex items-center gap-1.5 text-sm text-on-surface-variant hover:text-primary"
      >
        <ArrowLeft size={16} /> Все контракты
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4 mt-3">
        <div className="flex items-start gap-3.5">
          <TypeIcon type={c.contract_type} size={24} className="mt-0.5 h-12 w-12 shrink-0" />
          <div>
            <h1 className="text-2xl font-semibold leading-tight">{c.title}</h1>
            <div className="mt-1 text-sm text-on-surface-variant">
              {c.counterparty ?? "Контрагент не указан"}
            </div>
            <div className="flex flex-wrap items-center gap-2 mt-2.5">
              <TypeChip type={c.contract_type} />
              <StatusChip status={c.status} />
              <RiskChip score={c.risk_score} />
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            onClick={() => router.push(`/contracts/${c.id}/workspace`)}
          >
            <span className="flex items-center gap-2">
              <LayoutPanelLeft size={16} /> Рабочий стол
            </span>
          </Button>
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
          {canEdit && (
            <Button variant="secondary" onClick={() => setEditOpen(true)}>
              <span className="flex items-center gap-2">
                <Pencil size={16} /> Редактировать
              </span>
            </Button>
          )}
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
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {[
                {
                  icon: Building2,
                  label: "Контрагент",
                  value: c.counterparty ?? "—",
                },
                {
                  icon: Coins,
                  label: "Сумма",
                  value: c.amount
                    ? `${Number(c.amount).toLocaleString("ru-RU")} ${c.currency}`
                    : "—",
                },
                {
                  icon: CalendarDays,
                  label: "Создан",
                  value: new Date(c.created_at).toLocaleString("ru-RU"),
                },
                {
                  icon: Clock,
                  label: "Обновлен",
                  value: new Date(c.updated_at).toLocaleString("ru-RU"),
                },
              ].map(({ icon: Icon, label, value }) => (
                <div key={label} className="flex items-start gap-3">
                  <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-container-low text-on-surface-variant">
                    <Icon size={16} />
                  </span>
                  <div className="min-w-0">
                    <dt className="text-xs text-on-surface-variant">{label}</dt>
                    <dd className="mt-0.5 text-sm font-medium break-words">{value}</dd>
                  </div>
                </div>
              ))}
            </dl>
          </Card>

          <Card className="p-6">
            <h2 className="font-semibold mb-4">Текст контракта</h2>
            {c.content ? (
              <pre className="max-h-[32rem] overflow-y-auto whitespace-pre-wrap rounded-lg border border-outline-variant bg-surface-container-low p-5 font-body text-sm leading-relaxed">
                {c.content}
              </pre>
            ) : (
              <p className="text-sm text-on-surface-variant">
                Текст не заполнен. Нажмите «Редактировать», чтобы добавить.
              </p>
            )}
          </Card>

          <AnalysisSection contractId={c.id} canRun={canEdit} />
        </div>

        <div className="space-y-6">
          <WorkflowPanel contractId={c.id} />
          <DeadlinesPanel contractId={c.id} canEdit={canEdit} />

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
        <Modal title="Подписание E-IMZO" onClose={() => setSignOpen(false)}>
          <div className="space-y-4">
            <div className="rounded-xl border border-outline-variant bg-surface-container-low px-4 py-3">
              <div className="text-xs font-semibold text-on-surface-variant uppercase">
                Хеш документа (SHA-256)
              </div>
              <div className="text-xs mt-1 break-all font-mono">
                {signRequestData?.hash ?? "Создаём хеш контракта..."}
              </div>
            </div>

            {/* Поиск клиента E-IMZO */}
            {eimzoCerts === null && (
              <div className="flex items-center gap-2 text-sm text-on-surface-variant py-2">
                <Spinner className="text-primary" /> Ищем клиент E-IMZO на этом
                компьютере…
              </div>
            )}

            {/* Клиент найден: выбор сертификата */}
            {Array.isArray(eimzoCerts) && (
              <div className="space-y-2">
                <div className="text-[13px] font-semibold">
                  Ключ электронной подписи
                </div>
                {eimzoCerts.length === 0 && (
                  <p className="text-sm text-on-surface-variant">
                    E-IMZO запущен, но ключи не найдены. Подключите носитель с
                    ЭЦП или скопируйте ключ в C:\DSKEYS.
                  </p>
                )}
                {eimzoCerts.map((cert) => (
                  <button
                    key={`${cert.disk}${cert.path}${cert.name}`}
                    type="button"
                    onClick={() => setSelectedCert(cert)}
                    className={`w-full text-left border rounded-lg px-3 py-2.5 cursor-pointer transition-colors ${
                      selectedCert === cert
                        ? "border-primary ring-1 ring-primary"
                        : "border-outline-variant hover:border-primary"
                    }`}
                  >
                    <div className="text-sm font-medium">{cert.cn}</div>
                    <div className="text-xs text-on-surface-variant mt-0.5">
                      {cert.organization ?? "Физическое лицо"}
                      {cert.tin ? ` · ИНН ${cert.tin}` : ""}
                      {cert.validTo ? ` · до ${cert.validTo}` : ""}
                    </div>
                  </button>
                ))}
                {eimzoCerts.length > 0 && (
                  <Button
                    className="w-full"
                    disabled={!selectedCert || !signRequestData}
                    loading={eimzoSigning || signConfirm.isPending}
                    onClick={signWithEimzo}
                  >
                    <span className="flex items-center justify-center gap-2">
                      {!eimzoSigning && !signConfirm.isPending && (
                        <ShieldCheck size={16} />
                      )}
                      {eimzoSigning
                        ? "Введите пароль ключа в окне E-IMZO…"
                        : signConfirm.isPending
                          ? "Сохраняем подпись..."
                          : "Подписать через E-IMZO"}
                    </span>
                  </Button>
                )}
              </div>
            )}

            {/* Клиент не найден: инструкция + тестовая подпись */}
            {eimzoCerts === false && (
              <>
                <div className="rounded-lg bg-warning-container/50 text-sm px-3 py-2.5">
                  Клиент E-IMZO не найден. Установите его с{" "}
                  <a
                    href="https://e-imzo.uz/#/downloads"
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary font-medium hover:underline"
                  >
                    e-imzo.uz
                  </a>
                  , запустите и откройте это окно снова.
                </div>
                <div className="border-t border-outline-variant pt-3">
                  <div className="text-[13px] font-semibold mb-2">
                    Тестовая подпись (для демо, без юридической силы)
                  </div>
                  <Input
                    label="PIN"
                    type="password"
                    inputMode="numeric"
                    value={pin}
                    onChange={(event) => setPin(event.target.value)}
                    placeholder="123456"
                  />
                  <Button
                    variant="secondary"
                    className="w-full mt-3"
                    disabled={!signRequestData}
                    loading={signConfirm.isPending}
                    onClick={() => {
                      setSignError("");
                      signConfirm.mutate({ pin: pin || null });
                    }}
                  >
                    Подписать тестовой подписью
                  </Button>
                </div>
              </>
            )}

            {signError && <ErrorNote message={signError} />}
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

function DeadlinesPanel({
  contractId,
  canEdit,
}: {
  contractId: string;
  canEdit: boolean;
}) {
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
        {canEdit && (
          <Button variant="secondary" className="px-3" onClick={() => setOpen(true)}>
            <Plus size={16} />
          </Button>
        )}
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
