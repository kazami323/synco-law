"use client";

import { useMutation } from "@tanstack/react-query";
import { Check, Copy, Languages } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { Button, ErrorNote, Modal, Select } from "@/components/ui";

const LANGS = [
  { value: "uz", label: "Узбекский (латиница)" },
  { value: "uz_cyrl", label: "Узбекский (кириллица)" },
  { value: "en", label: "Английский" },
  { value: "ru", label: "Русский" },
];

export function TranslateModal({
  contractId,
  onClose,
}: {
  contractId: string;
  onClose: () => void;
}) {
  const [lang, setLang] = useState("uz");
  const [result, setResult] = useState("");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  const translate = useMutation({
    mutationFn: () =>
      api<{ content: string }>(`/api/contracts/${contractId}/translate`, {
        method: "POST",
        body: { target_lang: lang },
      }),
    onSuccess: (data) => setResult(data.content),
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Ошибка перевода"),
  });

  async function copy() {
    await navigator.clipboard.writeText(result);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <Modal title="Перевод контракта" onClose={onClose}>
      <div className="space-y-4">
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <Select
              label="Язык перевода"
              value={lang}
              onChange={(e) => setLang(e.target.value)}
            >
              {LANGS.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </Select>
          </div>
          <Button
            loading={translate.isPending}
            onClick={() => {
              setError("");
              translate.mutate();
            }}
          >
            <span className="flex items-center gap-2">
              {!translate.isPending && <Languages size={16} />}
              {translate.isPending ? "Переводим…" : "Перевести"}
            </span>
          </Button>
        </div>

        {translate.isPending && (
          <p className="text-xs text-on-surface-variant">
            Translation Agent переводит с сохранением юридической
            терминологии — до минуты на длинных договорах.
          </p>
        )}
        {error && <ErrorNote message={error} />}

        {result && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[13px] font-semibold">Результат</span>
              <button
                onClick={copy}
                className="flex items-center gap-1.5 text-xs text-primary hover:underline cursor-pointer"
              >
                {copied ? <Check size={13} /> : <Copy size={13} />}
                {copied ? "Скопировано" : "Копировать"}
              </button>
            </div>
            <pre className="whitespace-pre-wrap text-sm font-body leading-relaxed max-h-72 overflow-y-auto border border-outline-variant rounded-lg p-3 bg-surface-container-low">
              {result}
            </pre>
          </div>
        )}
      </div>
    </Modal>
  );
}
