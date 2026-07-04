"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
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
import { api, apiUpload } from "@/lib/api";
import type { ContractDetail } from "@/lib/types";
import { Button, ErrorNote, Input, Modal } from "@/components/ui";

const TYPES = [
  {
    value: "purchase",
    label: "Купля-продажа",
    text: "Договор купли-продажи товаров, оборудования или недвижимости.",
    icon: ShoppingCart,
  },
  {
    value: "lease",
    label: "Аренда",
    text: "Договор аренды коммерческой или жилой недвижимости, транспорта.",
    icon: KeySquare,
  },
  {
    value: "service",
    label: "Подряд",
    text: "Договор на выполнение строительных, ремонтных или иных работ.",
    icon: Hammer,
  },
  {
    value: "nda",
    label: "NDA",
    text: "Соглашение о неразглашении конфиденциальной информации.",
    icon: Lock,
  },
  {
    value: "employment",
    label: "Трудовой",
    text: "Трудовой договор с сотрудником, контракт с руководителем.",
    icon: Briefcase,
  },
  {
    value: "other",
    label: "Другое",
    text: "Создать контракт с нуля или использовать свой шаблон.",
    icon: Ellipsis,
  },
];

const STEPS = ["Тип", "Детали", "Содержание"];

export function CreateContractModal({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [step, setStep] = useState(0);
  const [type, setType] = useState("purchase");
  const [details, setDetails] = useState({
    title: "",
    counterparty: "",
    amount: "",
    currency: "UZS",
  });
  const [source, setSource] = useState<"file" | "text">("file");
  const [file, setFile] = useState<File | null>(null);
  const [content, setContent] = useState("");
  const [error, setError] = useState("");

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
        form.append("file", file);
        return apiUpload<ContractDetail>("/api/contracts/upload", form);
      }
      return api<ContractDetail>("/api/contracts/", {
        method: "POST",
        body: { ...common, content: content || null },
      });
    },
    onSuccess: (contract) => {
      qc.invalidateQueries({ queryKey: ["contracts"] });
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
          {TYPES.map(({ value, label, text, icon: Icon }) => (
            <button
              key={value}
              type="button"
              onClick={() => setType(value)}
              className={`text-left border rounded-xl p-3 transition-colors cursor-pointer ${
                type === value
                  ? "border-primary ring-1 ring-primary"
                  : "border-outline-variant hover:border-primary"
              }`}
            >
              <div className="w-9 h-9 rounded-lg bg-primary-fixed text-primary flex items-center justify-center mb-2">
                <Icon size={18} />
              </div>
              <div className="text-sm font-medium">{label}</div>
              <div className="text-xs text-on-surface-variant mt-1">{text}</div>
            </button>
          ))}
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
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => setSource("file")}
              className={`border rounded-xl p-3 text-left cursor-pointer ${source === "file" ? "border-primary ring-1 ring-primary" : "border-outline-variant"}`}
            >
              <FileUp size={18} className="text-primary mb-1" />
              <div className="text-sm font-medium">Загрузить файл</div>
              <div className="text-xs text-on-surface-variant">
                PDF, DOCX или TXT — текст извлечётся автоматически
              </div>
            </button>
            <button
              type="button"
              onClick={() => setSource("text")}
              className={`border rounded-xl p-3 text-left cursor-pointer ${source === "text" ? "border-primary ring-1 ring-primary" : "border-outline-variant"}`}
            >
              <Type size={18} className="text-primary mb-1" />
              <div className="text-sm font-medium">Вставить текст</div>
              <div className="text-xs text-on-surface-variant">
                Скопируйте текст договора в поле
              </div>
            </button>
          </div>

          {source === "file" ? (
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
                  "Нажмите, чтобы выбрать файл"
                )}
              </div>
            </label>
          ) : (
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={8}
              placeholder="ДОГОВОР ПОСТАВКИ №…"
              className="w-full px-3 py-2 rounded-lg border border-outline-variant bg-surface-container-lowest text-sm outline-none focus:border-primary"
            />
          )}

          <div className="flex items-center gap-2 text-xs text-on-surface-variant">
            <Sparkles size={14} />
            Генерация контракта AI-агентом появится на этапе Weeks 7-8
          </div>
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
              disabled={create.isPending}
              onClick={() => {
                setError("");
                create.mutate();
              }}
            >
              {create.isPending ? "Создаём..." : "Создать контракт"}
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
}
