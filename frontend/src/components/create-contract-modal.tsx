"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Briefcase,
  Ellipsis,
  FileUp,
  Hammer,
  KeySquare,
  Lock,
  ShoppingCart,
  Sparkles,
  Type,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, apiBackgroundTask, apiUpload } from "@/lib/api";
import type {
  ContractDetail,
  DocumentTemplate,
  DocumentTypeInfo,
  DraftParams,
} from "@/lib/types";
import { DraftTaskInput } from "@/components/draft-task-input";
import { Button, ErrorNote, Input, Modal, Select } from "@/components/ui";

// Иконка по типу документа; сам каталог приходит с бэкенда, чтобы список
// типов правился в одном месте (backend/app/core/document_types.py).
const TYPE_ICONS: Record<string, typeof ShoppingCart> = {
  supply: ShoppingCart,
  purchase: ShoppingCart,
  lease: KeySquare,
  service: Briefcase,
  contracting: Hammer,
  nda: Lock,
  license: KeySquare,
  employment: Briefcase,
  amendment: Ellipsis,
  other: Ellipsis,
};

const STEPS = ["Тип", "Детали", "Содержание"];

export function CreateContractModal({
  onClose,
  projectId,
}: {
  onClose: () => void;
  projectId?: string;
}) {
  const router = useRouter();
  const qc = useQueryClient();
  const [step, setStep] = useState(0);
  const [type, setType] = useState("supply");
  const [templateId, setTemplateId] = useState("");
  const [draftParams, setDraftParams] = useState<DraftParams | null>(null);
  const [details, setDetails] = useState({
    title: "",
    counterparty: "",
    amount: "",
    currency: "UZS",
  });
  const [source, setSource] = useState<"file" | "text" | "ai">("file");
  const [file, setFile] = useState<File | null>(null);
  const [content, setContent] = useState("");
  const [aiRequirements, setAiRequirements] = useState("");
  const [error, setError] = useState("");

  const types = useQuery({
    queryKey: ["document-types"],
    queryFn: () => api<DocumentTypeInfo[]>("/api/document-types?group=contract"),
  });
  // Шаблоны того же типа: шаг 2 ТЗ, выбор опционален.
  const templates = useQuery({
    queryKey: ["templates", type],
    queryFn: () => api<DocumentTemplate[]>(`/api/templates?doc_type=${type}`),
    enabled: source === "ai",
  });

  const create = useMutation({
    mutationFn: async (): Promise<ContractDetail> => {
      const common = {
        title: details.title,
        contract_type: type,
        counterparty: details.counterparty || null,
        amount: details.amount ? Number(details.amount) : null,
        currency: details.currency,
      };
      if (source === "file") {
        if (!file) throw new Error("Выберите файл PDF, DOCX или TXT");
        const form = new FormData();
        form.append("title", common.title);
        form.append("contract_type", type);
        if (common.counterparty) form.append("counterparty", common.counterparty);
        if (details.amount) form.append("amount", details.amount);
        form.append("currency", details.currency);
        if (projectId) form.append("project_id", projectId);
        form.append("file", file);
        return apiUpload<ContractDetail>("/api/contracts/upload", form);
      }
      let finalContent = content;
      if (source === "ai") {
        if (!aiRequirements.trim())
          throw new Error("Опишите требования к договору");
        // ТЗ, 3.1: параметры показываются юристу карточкой для подтверждения
        // перед генерацией. Без разбора генерация запускалась по одной лишь
        // постановке задачи — модель домысливала стороны, суммы и сроки, а
        // юрист узнавал об этом уже из готового текста.
        if (!draftParams)
          throw new Error(
            "Разберите условия и проверьте карточку параметров — по ней собирается документ",
          );
        if (draftParams.parsed_from !== undefined && draftParams.parsed_from !== aiRequirements)
          throw new Error(
            "Постановка задачи изменилась после разбора. Разберите условия заново.",
          );
        const draft = await apiBackgroundTask<{ content: string }>("/api/agents/draft/jobs", {
          method: "POST",
          body: {
            contract_type: type,
            template_id: templateId || null,
            project_id: projectId ?? null,
            requirements: {
              "название": common.title,
              "контрагент": common.counterparty,
              "сумма": details.amount
                ? `${details.amount} ${details.currency}`
                : null,
              "постановка задачи": aiRequirements,
              "подтверждённые параметры": draftParams,
            },
          },
        });
        finalContent = draft.content;
      }
      return api<ContractDetail>("/api/contracts/", {
        method: "POST",
        body: {
          ...common,
          content: finalContent || null,
          project_id: projectId ?? null,
          // Документ, собранный ИИ, заводится как «Сгенерирован» (ТЗ, 3.1).
          ai_generated: source === "ai",
        },
      });
    },
    onSuccess: (contract) => {
      qc.invalidateQueries({ queryKey: ["contracts"] });
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["dashboard-metrics"] });
      onClose();
      router.push(`/contracts/${contract.id}`);
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Ошибка создания"),
  });

  const canNext =
    step === 0 || (step === 1 && details.title.trim().length > 0);

  return (
    <Modal title={`Создать новый контракт — шаг ${step + 1} из 3`} onClose={onClose}>
      {/* Индикатор шагов */}
      <div className="flex items-center gap-2 mb-5">
        {STEPS.map((label, i) => (
          <div key={label} className="flex items-center gap-2 flex-1">
            <div
              className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold shrink-0 ${
                i <= step
                  ? "bg-primary text-on-primary"
                  : "bg-surface-container-high text-on-surface-variant"
              }`}
            >
              {i + 1}
            </div>
            <span
              className={`text-xs ${i === step ? "text-primary font-medium" : "text-on-surface-variant"}`}
            >
              {label}
            </span>
            {i < STEPS.length - 1 && (
              <div className="flex-1 h-px bg-outline-variant" />
            )}
          </div>
        ))}
      </div>

      {step === 0 && (
        <div className="grid grid-cols-2 gap-3 max-h-80 overflow-y-auto">
          {(types.data ?? []).map((item) => {
            const Icon = TYPE_ICONS[item.value] ?? Ellipsis;
            return (
              <button
                key={item.value}
                type="button"
                onClick={() => setType(item.value)}
                className={`text-left border rounded-xl p-3 transition-colors cursor-pointer ${
                  type === item.value
                    ? "border-primary ring-1 ring-primary"
                    : "border-outline-variant hover:border-primary"
                }`}
              >
                <div className="w-9 h-9 rounded-lg bg-primary-fixed text-primary flex items-center justify-center mb-2">
                  <Icon size={18} />
                </div>
                <div className="text-sm font-medium">{item.title}</div>
                <div className="text-xs text-on-surface-variant mt-1">
                  Обязательных блоков: {item.required_blocks.length}
                </div>
              </button>
            );
          })}
        </div>
      )}

      {step === 1 && (
        <div className="space-y-4">
          <Input
            label="Название контракта"
            placeholder="Договор поставки №45-А"
            value={details.title}
            onChange={(e) => setDetails({ ...details, title: e.target.value })}
            required
          />
          <Input
            label="Контрагент"
            placeholder='ООО "ТехноПром"'
            value={details.counterparty}
            onChange={(e) =>
              setDetails({ ...details, counterparty: e.target.value })
            }
          />
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2">
              <Input
                label="Сумма"
                type="number"
                placeholder="150000000"
                value={details.amount}
                onChange={(e) =>
                  setDetails({ ...details, amount: e.target.value })
                }
              />
            </div>
            <label className="block">
              <span className="block text-[13px] font-semibold mb-1.5">
                Валюта
              </span>
              <select
                value={details.currency}
                onChange={(e) =>
                  setDetails({ ...details, currency: e.target.value })
                }
                className="w-full h-10 px-3 rounded-lg border border-outline-variant bg-surface-container-lowest text-sm outline-none focus:border-primary"
              >
                <option>UZS</option>
                <option>USD</option>
                <option>EUR</option>
                <option>RUB</option>
              </select>
            </label>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <button
              type="button"
              onClick={() => setSource("file")}
              className={`border rounded-xl p-3 text-left cursor-pointer ${source === "file" ? "border-primary ring-1 ring-primary" : "border-outline-variant"}`}
            >
              <FileUp size={18} className="text-primary mb-1" />
              <div className="text-sm font-medium">Файл</div>
              <div className="text-xs text-on-surface-variant">
                PDF, DOCX, TXT
              </div>
            </button>
            <button
              type="button"
              onClick={() => setSource("text")}
              className={`border rounded-xl p-3 text-left cursor-pointer ${source === "text" ? "border-primary ring-1 ring-primary" : "border-outline-variant"}`}
            >
              <Type size={18} className="text-primary mb-1" />
              <div className="text-sm font-medium">Текст</div>
              <div className="text-xs text-on-surface-variant">
                Вставить вручную
              </div>
            </button>
            <button
              type="button"
              onClick={() => setSource("ai")}
              className={`border rounded-xl p-3 text-left cursor-pointer ${source === "ai" ? "border-primary ring-1 ring-primary" : "border-outline-variant"}`}
            >
              <Sparkles size={18} className="text-primary mb-1" />
              <div className="text-sm font-medium">Сгенерировать AI</div>
              <div className="text-xs text-on-surface-variant">
                Draft Agent по требованиям
              </div>
            </button>
          </div>

          {source === "file" && (
            <label className="block border-2 border-dashed border-outline-variant rounded-xl p-6 text-center cursor-pointer hover:border-primary">
              <input
                type="file"
                accept=".pdf,.docx,.txt"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              <FileUp size={22} className="mx-auto text-outline" />
              <div className="text-sm mt-2">
                {file ? (
                  <span className="font-medium text-primary">{file.name}</span>
                ) : (
                  "Нажмите, чтобы выбрать файл — текст извлечётся автоматически"
                )}
              </div>
            </label>
          )}
          {source === "text" && (
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={8}
              placeholder="ДОГОВОР ПОСТАВКИ №…"
              className="w-full px-3 py-2 rounded-lg border border-outline-variant bg-surface-container-lowest text-sm outline-none focus:border-primary"
            />
          )}
          {source === "ai" && (
            <div className="space-y-3">
              <Select
                label="Шаблон (необязательно)"
                value={templateId}
                onChange={(e) => setTemplateId(e.target.value)}
              >
                <option value="">
                  Без шаблона — общая структура для этого типа
                </option>
                {(templates.data ?? []).map((template) => (
                  <option key={template.id} value={template.id}>
                    {template.name}
                    {template.verified_at ? " · верифицирован" : ""}
                  </option>
                ))}
              </Select>
              <DraftTaskInput
                value={aiRequirements}
                onChange={setAiRequirements}
                params={draftParams}
                onParamsChange={setDraftParams}
              />
              {!draftParams && aiRequirements.trim() && (
                <p className="text-xs text-on-surface-variant">
                  Нажмите «Разобрать условия» и проверьте карточку параметров —
                  именно по ней собирается документ.
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {error && <div className="mt-4"><ErrorNote message={error} /></div>}

      <div className="flex items-center justify-between mt-6">
        <button
          onClick={onClose}
          className="text-sm text-on-surface-variant hover:text-on-surface cursor-pointer"
        >
          Отмена
        </button>
        <div className="flex gap-2">
          {step > 0 && (
            <Button variant="secondary" onClick={() => setStep(step - 1)}>
              Назад
            </Button>
          )}
          {step < 2 ? (
            <Button disabled={!canNext} onClick={() => setStep(step + 1)}>
              Далее
            </Button>
          ) : (
            <Button
              loading={create.isPending}
              onClick={() => {
                setError("");
                create.mutate();
              }}
            >
              {create.isPending
                ? source === "ai"
                  ? "Генерируем… (до минуты)"
                  : "Создаём..."
                : "Создать контракт"}
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
}
