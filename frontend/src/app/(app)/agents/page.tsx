"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Bot,
  FileText,
  Paperclip,
  PenLine,
  Scale,
  Send,
  ShieldAlert,
  X,
} from "lucide-react";
import { useRef, useState } from "react";
import { api, apiUpload } from "@/lib/api";
import type { ContractList } from "@/lib/types";
import { Card, Chip, ErrorNote } from "@/components/ui";

const AGENTS = [
  {
    key: "analyzer",
    name: "Contract Analyzer",
    text: "Извлекает ключевые условия, находит ошибки и противоречия в договорах.",
    icon: FileText,
  },
  {
    key: "law",
    name: "Law Agent",
    text: "Консультирует по законодательству РУз: ГК, ТК, НК, нормативные акты.",
    icon: Scale,
  },
  {
    key: "risk",
    name: "Risk Agent",
    text: "Оценивает юридические, финансовые и операционные риски сделок.",
    icon: ShieldAlert,
  },
  {
    key: "draft",
    name: "Draft Agent",
    text: "Составляет и редактирует тексты договоров и юридических документов.",
    icon: PenLine,
  },
];

interface Msg {
  role: "user" | "assistant";
  content: string;
}

export default function AgentsPage() {
  const [agent, setAgent] = useState("analyzer");
  const [histories, setHistories] = useState<Record<string, Msg[]>>({});
  const [input, setInput] = useState("");
  const [doc, setDoc] = useState<{ name: string; text: string } | null>(null);
  const [contractId, setContractId] = useState("");
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const contracts = useQuery({
    queryKey: ["contracts", "for-chat"],
    queryFn: () => api<ContractList>("/api/contracts/?limit=50"),
  });

  const messages = histories[agent] ?? [];
  const activeAgent = AGENTS.find((a) => a.key === agent)!;

  const send = useMutation({
    mutationFn: async (history: Msg[]) =>
      api<{ reply: string }>("/api/agents/chat", {
        method: "POST",
        body: {
          agent,
          messages: history,
          contract_id: contractId || null,
          document_text: contractId ? null : doc?.text ?? null,
          document_name: contractId ? null : doc?.name ?? null,
        },
      }),
    onSuccess: (data, history) => {
      setHistories((h) => ({
        ...h,
        [agent]: [...history, { role: "assistant", content: data.reply }],
      }));
      setTimeout(
        () => bottomRef.current?.scrollIntoView({ behavior: "smooth" }),
        50
      );
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Ошибка запроса"),
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || send.isPending) return;
    setError("");
    const history: Msg[] = [...messages, { role: "user", content: input.trim() }];
    setHistories((h) => ({ ...h, [agent]: history }));
    setInput("");
    send.mutate(history);
    setTimeout(
      () => bottomRef.current?.scrollIntoView({ behavior: "smooth" }),
      50
    );
  }

  async function attachFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const parsed = await apiUpload<{ filename: string; text: string }>(
        "/api/agents/parse-file",
        form
      );
      setDoc({ name: parsed.filename, text: parsed.text });
      setContractId("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось прочитать файл");
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div className="max-w-6xl h-full flex flex-col">
      <h1 className="text-2xl font-semibold">AI-агенты системы</h1>
      <p className="text-on-surface-variant text-sm mt-1">
        Выберите агента и задайте вопрос. Можно приложить документ или контракт
        из системы.
      </p>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 mt-6 flex-1 min-h-0">
        {/* Карточки агентов */}
        <div className="space-y-3">
          {AGENTS.map(({ key, name, text, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setAgent(key)}
              className={`w-full text-left border rounded-xl p-4 bg-surface-container-lowest transition-colors cursor-pointer ${
                agent === key
                  ? "border-primary ring-1 ring-primary"
                  : "border-outline-variant hover:border-primary"
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="w-10 h-10 rounded-lg bg-primary-fixed text-primary flex items-center justify-center">
                  <Icon size={20} />
                </div>
                <Chip tone="success">● Активен</Chip>
              </div>
              <div className="font-semibold mt-3">{name}</div>
              <div className="text-xs text-on-surface-variant mt-1">{text}</div>
            </button>
          ))}
        </div>

        {/* Чат */}
        <Card className="xl:col-span-2 flex flex-col min-h-[36rem]">
          <div className="flex items-center gap-3 px-5 py-4 border-b border-outline-variant">
            <div className="w-9 h-9 rounded-lg bg-primary text-on-primary flex items-center justify-center">
              <Bot size={18} />
            </div>
            <div className="flex-1">
              <div className="font-semibold text-sm">{activeAgent.name}</div>
              <div className="text-xs text-on-surface-variant">
                Чат с агентом
              </div>
            </div>
            <select
              value={contractId}
              onChange={(e) => {
                setContractId(e.target.value);
                if (e.target.value) setDoc(null);
              }}
              className="h-9 px-2 rounded-lg border border-outline-variant bg-surface-container-lowest text-xs outline-none focus:border-primary max-w-52"
            >
              <option value="">Без контракта</option>
              {contracts.data?.items.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </select>
          </div>

          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            {messages.length === 0 && (
              <div className="text-center text-sm text-on-surface-variant pt-16">
                Задайте вопрос агенту — например, «проверь сроки оплаты в
                приложенном договоре» или «какие обязательные условия у NDA
                по законодательству РУз?»
              </div>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded-xl px-4 py-2.5 text-sm whitespace-pre-wrap leading-relaxed ${
                    m.role === "user"
                      ? "bg-primary text-on-primary"
                      : "bg-surface-container-low border border-outline-variant"
                  }`}
                >
                  {m.content}
                </div>
              </div>
            ))}
            {send.isPending && (
              <div className="flex justify-start">
                <div className="rounded-xl px-4 py-2.5 text-sm bg-surface-container-low border border-outline-variant text-on-surface-variant">
                  Агент думает…
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="border-t border-outline-variant p-4 space-y-2">
            {error && <ErrorNote message={error} />}
            {doc && !contractId && (
              <div className="flex items-center gap-2 text-xs bg-primary-fixed/50 text-primary rounded-lg px-3 py-1.5 w-fit">
                <Paperclip size={12} />
                {doc.name}
                <button
                  onClick={() => setDoc(null)}
                  className="cursor-pointer hover:text-error"
                >
                  <X size={12} />
                </button>
              </div>
            )}
            <form onSubmit={submit} className="flex items-center gap-2">
              <input
                ref={fileRef}
                type="file"
                accept=".pdf,.docx,.txt"
                className="hidden"
                onChange={attachFile}
              />
              <button
                type="button"
                title="Приложить документ (PDF/DOCX/TXT)"
                onClick={() => fileRef.current?.click()}
                className="w-10 h-10 shrink-0 rounded-lg border border-outline-variant flex items-center justify-center text-on-surface-variant hover:border-primary hover:text-primary cursor-pointer"
              >
                <Paperclip size={18} />
              </button>
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Сообщение агенту..."
                className="flex-1 h-10 px-3 rounded-lg border border-outline-variant bg-surface-container-lowest text-sm outline-none focus:border-primary placeholder:text-outline"
              />
              <button
                type="submit"
                disabled={send.isPending || !input.trim()}
                className="w-10 h-10 shrink-0 rounded-lg bg-primary text-on-primary flex items-center justify-center hover:bg-primary-hover disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed"
              >
                <Send size={18} />
              </button>
            </form>
          </div>
        </Card>
      </div>
    </div>
  );
}
