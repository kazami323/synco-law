"use client";

import { ChevronDown, FileText, LoaderCircle, Paperclip, Send, X } from "lucide-react";
import type { ChangeEvent, FormEvent, KeyboardEvent, RefObject } from "react";
import { AgentSelector } from "@/components/ai-chat/agent-selector";

interface ContractOption {
  id: string;
  title: string;
}

interface DocumentPreview {
  name: string;
  size: number;
  type: string;
  extractionMethod: "text" | "ocr";
  textChars: number;
}

interface ChatComposerProps {
  value: string;
  agentKey: string;
  pending: boolean;
  documents: DocumentPreview[];
  uploading: boolean;
  persistedDocumentName: string | null;
  contractId: string;
  contracts: ContractOption[];
  error: string;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  fileRef: RefObject<HTMLInputElement | null>;
  onValueChange: (event: ChangeEvent<HTMLTextAreaElement>) => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onSubmit: (event: FormEvent) => void;
  onAgentChange: (key: string) => void;
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onRemoveFile: (index: number) => void;
  onClearPersistedDocument: () => void;
  onContractChange: (id: string) => void;
}

export function ChatComposer({
  value,
  agentKey,
  pending,
  documents,
  uploading,
  persistedDocumentName,
  contractId,
  contracts,
  error,
  textareaRef,
  fileRef,
  onValueChange,
  onKeyDown,
  onSubmit,
  onAgentChange,
  onFileChange,
  onRemoveFile,
  onClearPersistedDocument,
  onContractChange,
}: ChatComposerProps) {
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20 bg-surface px-3 pb-3 pt-3 sm:px-6 sm:pb-5">
      <div className="pointer-events-auto mx-auto w-full max-w-3xl">
        {error && (
          <div role="alert" className="mb-2 rounded-xl bg-error-container px-4 py-2.5 text-sm text-error">
            {error}
          </div>
        )}
        {documents.length > 0 && !contractId && (
          <div className="mb-2 flex max-w-full flex-wrap gap-2">
            {documents.map((document, index) => (
              <div key={`${document.name}-${index}`} className="flex min-w-0 max-w-full items-center gap-2 rounded-xl border border-outline-variant bg-surface-container-lowest px-3 py-2 text-xs text-on-surface">
                <FileText size={15} className="shrink-0 text-primary" />
                <span className="min-w-0">
                  <span className="block max-w-48 truncate">{document.name}</span>
                  <span className="block text-[10px] uppercase text-on-surface-variant">
                    {document.extractionMethod === "ocr" ? "OCR" : "Текст"} · {formatFileSize(document.size)} · {formatTextSize(document.textChars)}
                  </span>
                </span>
                <button type="button" title="Убрать файл" aria-label={`Убрать файл ${document.name}`} onClick={() => onRemoveFile(index)} className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md hover:bg-error-container hover:text-error">
                  <X size={13} />
                </button>
              </div>
            ))}
          </div>
        )}
        {persistedDocumentName && !contractId && (
          <div className="mb-2 flex w-fit max-w-full items-center gap-2 rounded-xl border border-outline-variant bg-surface-container-lowest px-3 py-2 text-xs text-on-surface">
            <FileText size={15} className="shrink-0 text-primary" />
            <span className="min-w-0">
              <span className="block max-w-80 truncate">{persistedDocumentName}</span>
              <span className="block text-[10px] uppercase text-success">Контекст сохранён в чате</span>
            </span>
            <button type="button" title="Отключить документы" aria-label="Отключить сохранённые документы" onClick={onClearPersistedDocument} className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md hover:bg-error-container hover:text-error">
              <X size={13} />
            </button>
          </div>
        )}
        {uploading && (
          <div className="mb-2 flex items-center gap-2 text-xs text-on-surface-variant" role="status">
            <LoaderCircle size={15} className="animate-spin text-primary" />
            Документ читается и подготавливается для анализа...
          </div>
        )}

        <form onSubmit={onSubmit} className="rounded-[1.5rem] border border-outline-variant bg-surface-container-lowest p-2 transition-colors focus-within:border-primary focus-within:bg-surface-container-lowest">
          <textarea
            ref={textareaRef}
            autoFocus
            rows={1}
            value={value}
            onChange={onValueChange}
            onKeyDown={onKeyDown}
            placeholder="Задайте вопрос..."
            aria-label="Сообщение"
            className="block max-h-44 min-h-14 w-full resize-none overflow-y-auto bg-transparent px-3 py-3 text-[15px] leading-relaxed text-on-surface outline-none placeholder:text-outline"
          />

          <div className="flex min-w-0 items-center justify-between gap-2 px-1 pb-1">
            <div className="flex min-w-0 items-center gap-1">
              <AgentSelector agentKey={agentKey} onSelect={onAgentChange} />
              <span className="mx-0.5 h-5 w-px shrink-0 bg-outline-variant" />
              <input
                ref={fileRef}
                type="file"
                multiple
                accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
                className="hidden"
                onChange={onFileChange}
              />
              <button
                type="button"
                title="Прикрепить до 3 файлов PDF, DOCX или TXT"
                aria-label="Прикрепить документы"
                onClick={() => fileRef.current?.click()}
                disabled={documents.length >= 3 || uploading}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-on-surface-variant outline-none transition-colors hover:bg-surface-container hover:text-on-surface focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Paperclip size={18} />
              </button>
              <div className="relative hidden min-w-0 sm:block">
                <select
                  value={contractId}
                  onChange={(event) => onContractChange(event.target.value)}
                  aria-label="Контракт как контекст"
                  title="Контракт как контекст"
                  className="h-9 max-w-40 cursor-pointer appearance-none truncate rounded-lg bg-transparent pl-2 pr-7 text-xs text-on-surface-variant outline-none hover:bg-surface-container focus-visible:ring-2 focus-visible:ring-primary"
                >
                  <option value="" className="bg-surface-container-lowest">Без контракта</option>
                  {contracts.map((contract) => (
                    <option key={contract.id} value={contract.id} className="bg-surface-container-lowest">
                      {contract.title}
                    </option>
                  ))}
                </select>
                <ChevronDown size={13} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-on-surface-variant" />
              </div>
            </div>

            <button
              type="submit"
              title="Отправить"
              aria-label="Отправить сообщение"
              disabled={pending || uploading || !value.trim()}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary text-on-primary outline-none transition hover:bg-primary-hover active:scale-95 disabled:cursor-not-allowed disabled:bg-surface-container-high disabled:text-outline focus-visible:ring-2 focus-visible:ring-primary"
            >
              <Send size={17} />
            </button>
          </div>
        </form>
        <p className="mt-2 text-center text-[11px] text-outline">
          ИИ может ошибаться. Важные юридические выводы проверяйте по первоисточникам.
        </p>
      </div>
    </div>
  );
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

function formatTextSize(chars: number): string {
  if (chars < 1000) return `${chars} зн.`;
  return `${Math.round(chars / 1000)} тыс. зн.`;
}
