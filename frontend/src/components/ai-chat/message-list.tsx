"use client";

import { BadgeCheck, Check, Copy, ExternalLink, RefreshCw, ThumbsDown, ThumbsUp } from "lucide-react";
import { type RefObject, useState } from "react";
import { Markdown } from "@/components/markdown";
import { getAgent } from "@/lib/agents";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  agent?: string;
  feedback?: "up" | "down";
  sources?: ChatSource[];
}

export interface ChatSource {
  text: string;
  document_title?: string | null;
  article_number?: string | null;
  article_title?: string | null;
  url?: string | null;
  current_revision_date?: string | null;
  status?: string | null;
  reference_status?: string | null;
  repealed_at?: string | null;
  repeal_law_url?: string | null;
  historical_revision_date?: string | null;
}

interface MessageListProps {
  messages: ChatMessage[];
  agentKey: string;
  pending: boolean;
  bottomRef: RefObject<HTMLDivElement | null>;
  onPrompt: (text: string) => void;
  onRegenerate: () => void;
  onFeedback: (messageIndex: number, rating: "up" | "down" | null) => void;
}

export function MessageList({
  messages,
  agentKey,
  pending,
  bottomRef,
  onPrompt,
  onRegenerate,
  onFeedback,
}: MessageListProps) {
  const active = getAgent(agentKey);
  const ActiveIcon = active.icon;

  if (messages.length === 0 && !pending) {
    return (
      <div className="flex min-h-full items-center justify-center px-4 pb-32 pt-20">
        <div className="w-full max-w-3xl text-center">
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-primary-fixed text-primary">
            <ActiveIcon size={24} />
          </span>
          <h1 className="mt-5 text-3xl font-medium text-on-surface sm:text-4xl">
            Чем я могу вам помочь?
          </h1>
          <p className="mt-3 text-sm text-on-surface-variant">
            Выберите специализированного AI-агента и задайте вопрос
          </p>
          <div className="mx-auto mt-8 grid max-w-2xl gap-2 sm:grid-cols-3">
            {active.prompts.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => onPrompt(prompt)}
                className="min-h-20 rounded-2xl border border-outline-variant bg-surface-container-lowest px-4 py-3 text-left text-sm leading-relaxed text-on-surface-variant outline-none transition-colors hover:border-primary hover:bg-surface-container-low hover:text-on-surface focus-visible:ring-2 focus-visible:ring-primary"
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-8 px-4 pb-44 pt-8 sm:px-8">
      {messages.map((message, index) => {
        if (message.role === "user") {
          return (
            <div key={`${message.role}-${index}`} className="flex justify-end">
              <div className="max-w-[85%] rounded-3xl rounded-br-lg bg-primary px-5 py-3 text-sm leading-relaxed text-on-primary sm:max-w-[72%]">
                <p className="whitespace-pre-wrap">{message.content}</p>
              </div>
            </div>
          );
        }

        return (
          <AssistantMessage
            key={`${message.role}-${index}`}
            content={message.content}
            agentKey={message.agent ?? agentKey}
            sources={message.sources ?? []}
            rating={message.feedback ?? null}
            onRating={(rating) => onFeedback(index, rating)}
            onRegenerate={index === messages.length - 1 ? onRegenerate : undefined}
          />
        );
      })}

      {pending && (
        <div className="flex gap-3">
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-primary-fixed text-primary">
            <ActiveIcon size={17} />
          </span>
          <div>
            <div className="mb-2 text-xs font-medium text-on-surface-variant">{active.name}</div>
            <div className="flex h-8 items-center gap-1.5">
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-on-surface-variant" />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-on-surface-variant" />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-on-surface-variant" />
            </div>
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}

function AssistantMessage({
  content,
  agentKey,
  sources,
  rating,
  onRating,
  onRegenerate,
}: {
  content: string;
  agentKey: string;
  sources: ChatSource[];
  rating: "up" | "down" | null;
  onRating: (rating: "up" | "down" | null) => void;
  onRegenerate?: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const agent = getAgent(agentKey);
  const Icon = agent.icon;

  async function copyAnswer() {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <div className="flex gap-3 text-on-surface">
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-primary-fixed text-primary">
        <Icon size={17} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="mb-2 text-xs font-medium text-on-surface-variant">{agent.name}</div>
        <div className="max-w-none [&_a]:text-primary [&_code]:bg-surface-container [&_hr]:border-outline-variant">
          <Markdown content={content} />
        </div>
        {sources.length > 0 && (
          <div className="mt-4 border-t border-outline-variant pt-3">
            <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-success">
              <BadgeCheck size={15} />
              Проверенные источники Lex.uz
            </div>
            <div className="flex flex-wrap gap-2">
              {sources.map((source, index) => (
                <a
                  key={`${source.url ?? "source"}-${index}`}
                  href={source.url ?? undefined}
                  target="_blank"
                  rel="noreferrer"
                  className="group flex max-w-full items-start gap-2 rounded-lg border border-outline-variant bg-surface-container-lowest px-3 py-2 text-left hover:border-primary hover:bg-surface-container-low"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-xs font-medium text-on-surface">
                      {source.document_title || "НПА Республики Узбекистан"}
                    </span>
                    <span className="mt-0.5 block text-[11px] text-on-surface-variant">
                      {source.article_number ? `Статья ${source.article_number}` : "Фрагмент"}
                      {source.reference_status === "repealed"
                        ? ` · утратила силу${source.repealed_at ? ` ${source.repealed_at}` : ""}`
                        : source.current_revision_date
                          ? ` · редакция ${source.current_revision_date}`
                          : ""}
                    </span>
                  </span>
                  <ExternalLink size={13} className="mt-0.5 shrink-0 text-primary" />
                </a>
              ))}
            </div>
          </div>
        )}
        <div className="mt-3 flex items-center gap-1 text-on-surface-variant">
          <ActionButton label="Копировать ответ" onClick={copyAnswer}>
            {copied ? <Check size={15} /> : <Copy size={15} />}
          </ActionButton>
          <ActionButton label="Полезный ответ" active={rating === "up"} onClick={() => onRating(rating === "up" ? null : "up")}>
            <ThumbsUp size={15} />
          </ActionButton>
          <ActionButton label="Неполезный ответ" active={rating === "down"} onClick={() => onRating(rating === "down" ? null : "down")}>
            <ThumbsDown size={15} />
          </ActionButton>
          {onRegenerate && (
            <ActionButton label="Повторить ответ" onClick={onRegenerate}>
              <RefreshCw size={15} />
            </ActionButton>
          )}
        </div>
      </div>
    </div>
  );
}

function ActionButton({
  label,
  active = false,
  onClick,
  children,
}: {
  label: string;
  active?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      className={`flex h-8 w-8 items-center justify-center rounded-lg outline-none transition-colors hover:bg-surface-container hover:text-on-surface focus-visible:ring-2 focus-visible:ring-primary ${active ? "bg-primary-fixed text-primary" : ""}`}
    >
      {children}
    </button>
  );
}
