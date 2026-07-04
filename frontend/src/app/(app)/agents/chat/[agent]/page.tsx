"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, ChevronDown, Paperclip, Send, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, apiUpload } from "@/lib/api";
import { AGENTS, getAgent } from "@/lib/agents";
import type { ContractList } from "@/lib/types";
import { Card, ErrorNote } from "@/components/ui";

interface Msg {
  role: "user" | "assistant";
  content: string;
  agent?: string; // кто ответил
}

export default function AgentChatPage() {
  const params = useParams<{ agent: string }>();
  const router = useRouter();
  const [agent, setAgent] = useState(getAgent(params.agent).key);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [doc, setDoc] = useState<{ name: string; text: string } | null>(null);
  const [contractId, setContractId] = useState("");
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const active = getAgent(agent);
  const Icon = active.icon;

  const contracts = useQuery({
    queryKey: ["contracts", "for-chat"],
    queryFn: () => api<ContractList>("/api/contracts/?limit=50"),
  });

  // Смена агента — как смена модели: история остаётся, отвечает новый агент
  function switchAgent(key: string) {
    setAgent(key);
    router.replace(`/agents/chat/${key}`, { scroll: false });
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  const send = useMutation({
    mutationFn: async (history: Msg[]) =>
      api<{ reply: string }>("/api/agents/chat", {
        method: "POST",
        body: {
          agent,
          messages: history.map(({ role, content }) => ({ role, content })),
          contract_id: contractId || null,
          document_text: contractId ? null : (doc?.text ?? null),
          document_name: contractId ? null : (doc?.name ?? null),
        },
      }),
    onSuccess: (data, history) => {
      setMessages([
        ...history,
        { role: "assistant", content: data.reply, agent },
      ]);
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Ошибка запроса"),
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || send.isPending) return;
    setError("");
    const history: Msg[] = [
      ...messages,
      { role: "user", content: input.trim() },
    ];
    setMessages(history);
    setInput("");
    send.mutate(history);
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
    <div className="max-w-4xl mx-auto flex flex-col h-[calc(100vh-8.5rem)]">
      <Card className="flex flex-col flex-1 min-h-0">
        {/* Шапка чата: назад + переключатель агента + контекст */}
        <div className="flex items-center gap-3 px-5 py-3.5 border-b border-outline-variant">
          <Link
            href="/agents"
            title="Все агенты"
            className="w-9 h-9 shrink-0 rounded-lg border border-outline-variant flex items-center justify-center text-on-surface-variant hover:border-primary hover:text-primary"
          >
            <ArrowLeft size={18} />
          </Link>

          {/* Переключатель агента — как выбор модели */}
          <div className="relative">
            <select
              value={agent}
              onChange={(e) => switchAgent(e.target.value)}
              className="appearance-none h-10 pl-11 pr-9 rounded-lg border border-outline-variant bg-surface-container-lowest text-sm font-semibold outline-none focus:border-primary cursor-pointer"
            >
              {AGENTS.map((a) => (
                <option key={a.key} value={a.key}>
                  {a.name}
                </option>
              ))}
            </select>
            <div className="pointer-events-none absolute left-1.5 top-1/2 -translate-y-1/2 w-7 h-7 rounded-md bg-primary text-on-primary flex items-center justify-center">
              <Icon size={15} />
            </div>
            <ChevronDown
              size={15}
              className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-on-surface-variant"
            />
          </div>

          <div className="flex-1" />

          <select
            value={contractId}
            onChange={(e) => {
              setContractId(e.target.value);
              if (e.target.value) setDoc(null);
            }}
            className="h-9 px-2 rounded-lg border border-outline-variant bg-surface-container-lowest text-xs outline-none focus:border-primary max-w-48"
            title="Контракт как контекст разговора"
          >
            <option value="">Без контракта</option>
            {contracts.data?.items.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
          </select>
        </div>

        {/* Сообщения */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {messages.length === 0 && (
            <div className="text-center pt-20">
              <div className="w-12 h-12 rounded-xl bg-primary-fixed text-primary flex items-center justify-center mx-auto">
                <Icon size={24} />
              </div>
              <div className="font-semibold mt-3">{active.name}</div>
              <p className="text-sm text-on-surface-variant mt-1 max-w-md mx-auto">
                {active.text}
              </p>
              <p className="text-xs text-outline mt-3">{active.hint}</p>
            </div>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div className="max-w-[85%]">
                {m.role === "assistant" && m.agent && (
                  <div className="text-[11px] text-on-surface-variant mb-1 ml-1">
                    {getAgent(m.agent).name}
                  </div>
                )}
                <div
                  className={`rounded-xl px-4 py-2.5 text-sm whitespace-pre-wrap leading-relaxed ${
                    m.role === "user"
                      ? "bg-primary text-on-primary"
                      : "bg-surface-container-low border border-outline-variant"
                  }`}
                >
                  {m.content}
                </div>
              </div>
            </div>
          ))}
          {send.isPending && (
            <div className="flex justify-start">
              <div className="rounded-xl px-4 py-2.5 text-sm bg-surface-container-low border border-outline-variant text-on-surface-variant">
                {active.name} думает…
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Ввод */}
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
              placeholder={`Сообщение для ${active.name}...`}
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
  );
}
