"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  BookOpen,
  Check,
  ExternalLink,
  FileText,
  MessageSquare,
  Pencil,
  SkipForward,
} from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import type { Clause, ClauseAction, ClauseList } from "@/lib/types";
import { CLAUSE_ACTION_LABELS, VERDICT_LABELS } from "@/lib/types";
import {
  Button,
  Card,
  Chip,
  Dot,
  ErrorNote,
  SegmentedProgress,
  Skeleton,
  type Tone,
} from "@/components/ui";

/**
 * Интерфейс «пункт за пунктом» из ТЗ, раздел 4: слева текст пункта, справа
 * найденные нормы и вердикт системы. Решение по каждому пункту принимает
 * юрист — система только предлагает.
 */
export function ClauseReview({ contractId }: { contractId: string }) {
  const qc = useQueryClient();
  const { user } = useAuth();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [draftText, setDraftText] = useState("");
  const [comment, setComment] = useState("");
  const [mode, setMode] = useState<"view" | "edit" | "comment">("view");
  const [error, setError] = useState("");

  const clauses = useQuery({
    queryKey: ["clauses", contractId],
    queryFn: () => api<ClauseList>(`/api/contracts/${contractId}/clauses`),
  });

  const decide = useMutation({
    mutationFn: (payload: {
      clauseId: string;
      action: ClauseAction;
      new_text?: string;
      comment?: string;
    }) =>
      api(`/api/clauses/${payload.clauseId}/decision`, {
        method: "POST",
        body: {
          action: payload.action,
          new_text: payload.new_text,
          comment: payload.comment,
        },
      }),
    onSuccess: (_data, variables) => {
      setError("");
      setMode("view");
      setComment("");
      qc.invalidateQueries({ queryKey: ["clauses", contractId] });
      qc.invalidateQueries({ queryKey: ["review-summary", contractId] });
      qc.invalidateQueries({ queryKey: ["contract", contractId] });
      // Подтвердил — сразу к следующему непройденному: проход по документу
      // не должен требовать возврата к списку после каждого пункта.
      if (variables.action === "confirm" || variables.action === "edit") {
        goToNextUnresolved(variables.clauseId);
      }
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Не удалось сохранить решение"),
  });

  const items = clauses.data?.items ?? [];

  function goToNextUnresolved(fromId: string) {
    const index = items.findIndex((item) => item.id === fromId);
    if (index === -1) return;
    const rest = [...items.slice(index + 1), ...items.slice(0, index)];
    const target = rest.find((item) => !isResolved(item) && item.id !== fromId);
    if (target) openClause(target);
  }

  /** Есть ли несохранённый набранный текст — правка пункта или комментарий. */
  function hasUnsaved() {
    if (mode === "edit") return draftText.trim() !== (active?.content ?? "").trim();
    if (mode === "comment") return comment.trim().length > 0;
    return false;
  }

  function openClause(clause: Clause) {
    // Юрист набирал новую формулировку пункта и кликал по соседнему в списке —
    // текст исчезал без единого слова. Правка пункта стоит юристу времени и
    // мысли, терять её молча нельзя.
    if (
      clause.id !== activeId &&
      hasUnsaved() &&
      !window.confirm(
        "В пункте есть несохранённый текст. Перейти к другому пункту и потерять его?",
      )
    ) {
      return;
    }
    setActiveId(clause.id);
    setDraftText(clause.content);
    setMode("view");
    setComment("");
    setError("");
    if (typeof window !== "undefined" && window.innerWidth < 1024) {
      document
        .getElementById("clause-card")
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  if (clauses.isLoading) {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,260px)_minmax(0,1fr)] gap-4">
        <Skeleton className="h-[60vh]" />
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <Skeleton className="h-80" />
          <Skeleton className="h-80" />
        </div>
      </div>
    );
  }
  if (clauses.isError) {
    return <ErrorNote message="Не удалось загрузить пункты документа" />;
  }
  if (!items.length) {
    return (
      <Card className="p-6 text-sm text-on-surface-variant">
        В документе нет текста для разбивки на пункты.
      </Card>
    );
  }

  const data = clauses.data!;
  const active = items.find((item) => item.id === activeId) ?? items[0];
  const readOnly = data.locked || !can(user, "confirm_clause");

  return (
    <div className="space-y-4">
      <ProgressBar progress={data.progress} locked={data.locked} />

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,260px)_minmax(0,1fr)] gap-4 items-start">
        <ClauseList items={items} activeId={active.id} onOpen={openClause} />

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 min-w-0">
          {/* Текст пункта и решение юриста */}
          <Card
            id="clause-card"
            className="flex flex-col min-w-0 overflow-hidden scroll-mt-4 lg:sticky lg:top-4 lg:h-[calc(100vh-9rem)]"
          >
            <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-outline-variant bg-surface-container-low">
              <h3 className="font-semibold text-sm flex items-center gap-2 min-w-0">
                <FileText size={15} className="text-primary shrink-0" />
                <span className="truncate">{clauseTitle(active)}</span>
              </h3>
              {active.decision && (
                <Chip tone={active.decision.stale ? "warning" : "success"}>
                  {CLAUSE_ACTION_LABELS[active.decision.action]}
                  {active.decision.stale ? " · устарело" : ""}
                </Chip>
              )}
            </div>

            <div className="p-4 space-y-3 flex-1 min-h-0 overflow-y-auto">
              {mode === "edit" ? (
                <textarea
                  value={draftText}
                  onChange={(event) => setDraftText(event.target.value)}
                  rows={14}
                  autoFocus
                  className="w-full rounded-lg border border-outline-variant bg-surface-container-lowest p-3 text-sm leading-relaxed outline-none focus:border-primary focus:ring-2 focus:ring-primary-fixed"
                />
              ) : (
                <p className="text-sm leading-[1.7] whitespace-pre-wrap">
                  {active.content}
                </p>
              )}

              {active.decision?.stale && (
                <p className="text-xs text-warning flex items-start gap-1.5">
                  <span aria-hidden>⟳</span>
                  Текст пункта изменился после подтверждения — пройдите по нему
                  заново.
                </p>
              )}

              {mode === "comment" && (
                <textarea
                  value={comment}
                  onChange={(event) => setComment(event.target.value)}
                  rows={3}
                  autoFocus
                  placeholder="Заметка для коллеги или для себя"
                  className="w-full rounded-lg border border-outline-variant bg-surface-container-lowest p-3 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary-fixed"
                />
              )}

              {active.decision && (
                <p className="text-xs text-on-surface-variant border-t border-outline-variant pt-3">
                  {CLAUSE_ACTION_LABELS[active.decision.action]} ·{" "}
                  {active.decision.decided_by_name ?? "юрист"} ·{" "}
                  {new Date(active.decision.created_at).toLocaleString("ru-RU")}
                  {active.decision.comment ? ` · ${active.decision.comment}` : ""}
                </p>
              )}
            </div>

            {error && <div className="px-4 pb-3"><ErrorNote message={error} /></div>}

            {/* Панель решения прилипает к низу карточки: это главное действие
                экрана, оно не должно уезжать за пределы видимой области. */}
            <div className="shrink-0 px-4 py-3 border-t border-outline-variant bg-surface-container-lowest">
              {readOnly ? (
                <p className="text-xs text-on-surface-variant">
                  {data.locked
                    ? "Документ в статусе «Финальный»: редактирование заблокировано."
                    : "У вас нет права подтверждать пункты."}
                </p>
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  {mode === "view" && (
                    <>
                      <Button
                        size="sm"
                        onClick={() =>
                          decide.mutate({ clauseId: active.id, action: "confirm" })
                        }
                        disabled={decide.isPending}
                      >
                        <Check size={15} /> Подтвердить
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => {
                          setDraftText(active.content);
                          setMode("edit");
                        }}
                      >
                        <Pencil size={15} /> Изменить
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => setMode("comment")}
                      >
                        <MessageSquare size={15} /> Комментарий
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          decide.mutate({ clauseId: active.id, action: "defer" })
                        }
                        disabled={decide.isPending}
                      >
                        <SkipForward size={15} /> Отложить
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="ml-auto"
                        onClick={() => goToNextUnresolved(active.id)}
                      >
                        Следующий <ArrowRight size={15} />
                      </Button>
                    </>
                  )}
                  {mode === "edit" && (
                    <>
                      <Button
                        size="sm"
                        onClick={() =>
                          decide.mutate({
                            clauseId: active.id,
                            action: "edit",
                            new_text: draftText,
                          })
                        }
                        loading={decide.isPending}
                        disabled={!draftText.trim()}
                      >
                        Сохранить правку
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setMode("view")}>
                        Отмена
                      </Button>
                    </>
                  )}
                  {mode === "comment" && (
                    <>
                      <Button
                        size="sm"
                        onClick={() =>
                          decide.mutate({
                            clauseId: active.id,
                            action: "comment",
                            comment,
                          })
                        }
                        loading={decide.isPending}
                        disabled={!comment.trim()}
                      >
                        Сохранить комментарий
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setMode("view")}>
                        Отмена
                      </Button>
                    </>
                  )}
                </div>
              )}
            </div>
          </Card>

          <ClauseVerdictPanel
            clause={active}
            onUseSuggestion={
              readOnly
                ? undefined
                : (text) => {
                    setDraftText(text);
                    setMode("edit");
                  }
            }
          />
        </div>
      </div>
    </div>
  );
}

function ClauseList({
  items,
  activeId,
  onOpen,
}: {
  items: Clause[];
  activeId: string;
  onOpen: (clause: Clause) => void;
}) {
  return (
    <Card className="p-1.5 max-h-[45vh] overflow-y-auto lg:max-h-none lg:sticky lg:top-4 lg:h-[calc(100vh-9rem)]">
      <ul>
        {items.map((clause) => {
          const active = clause.id === activeId;
          // Раздел без собственного текста — это оглавление, а не условие:
          // показываем его как разделитель, чтобы список читался структурой.
          const isSection = clause.level === 1 && Boolean(clause.title);
          return (
            <li key={clause.id}>
              <button
                onClick={() => onOpen(clause)}
                className={`w-full text-left rounded-lg transition-colors cursor-pointer flex items-center gap-2
                  ${isSection ? "mt-2 first:mt-0 px-2.5 py-1.5" : "px-2.5 py-1.5"}
                  ${
                    active
                      ? "bg-primary-fixed text-primary"
                      : "hover:bg-surface-container"
                  }`}
                style={{ paddingLeft: `${10 + (clause.level - 1) * 12}px` }}
              >
                <Dot tone={dotTone(clause)} />
                <span
                  className={`shrink-0 tabular-nums ${
                    isSection
                      ? "text-[11px] font-bold uppercase tracking-wide"
                      : "text-xs font-semibold"
                  }`}
                >
                  {clause.number ?? clause.anchor}
                </span>
                <span
                  className={`truncate ${
                    isSection
                      ? "text-[11px] font-bold uppercase tracking-wide"
                      : "text-[13px] text-on-surface-variant"
                  } ${active ? "text-primary" : ""}`}
                >
                  {clause.title ?? clause.content.slice(0, 70)}
                </span>
                {clause.comments_count > 0 && (
                  <MessageSquare
                    size={12}
                    className="ml-auto shrink-0 text-outline"
                  />
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function ClauseVerdictPanel({
  clause,
  onUseSuggestion,
}: {
  clause: Clause;
  /** Не задан, если юрист не вправе править пункт. */
  onUseSuggestion?: (text: string) => void;
}) {
  const check = clause.check;

  if (!check) {
    return (
      <Card className="p-6 text-center">
        <div className="w-11 h-11 mx-auto mb-3 rounded-xl bg-surface-container flex items-center justify-center text-outline">
          <BookOpen size={18} />
        </div>
        <p className="text-sm font-medium">Сверка не проводилась</p>
        <p className="text-sm text-on-surface-variant mt-1.5 leading-relaxed">
          Запустите модуль «Разбивка на пункты и сверка с правовой базой», чтобы
          увидеть регулирующие нормы и вердикт по этому пункту.
        </p>
      </Card>
    );
  }

  const verdict = VERDICT_LABELS[check.verdict];

  return (
    <Card className="flex flex-col min-w-0 overflow-hidden lg:sticky lg:top-4 lg:h-[calc(100vh-9rem)]">
      <div className="shrink-0 flex items-center justify-between gap-2 px-4 py-3 border-b border-outline-variant bg-surface-container-low">
        <h3 className="font-semibold text-sm flex items-center gap-2">
          <BookOpen size={15} className="text-primary shrink-0" />
          Вердикт системы
        </h3>
        <Chip tone={check.stale ? "neutral" : verdict.tone}>{verdict.label}</Chip>
      </div>

      <div className="p-4 space-y-4 overflow-y-auto">
        {check.stale && (
          <div className="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2.5 text-sm">
            Текст пункта изменился после проверки. Вердикт относится к прежней
            редакции — запустите модуль заново, прежде чем на него опираться.
          </div>
        )}

        {check.rationale && (
          <p className="text-sm leading-[1.7]">{check.rationale}</p>
        )}

        {check.suggested_text && (
          <div className="rounded-lg border border-success/30 bg-success/5 p-3">
            <p className="text-xs font-semibold text-success mb-1.5">
              Предложенная формулировка
            </p>
            <p className="text-sm whitespace-pre-wrap leading-relaxed">
              {check.suggested_text}
            </p>
            {onUseSuggestion && (
              <Button
                size="sm"
                variant="secondary"
                className="mt-2.5"
                onClick={() => onUseSuggestion(check.suggested_text ?? "")}
              >
                <Pencil size={14} /> Взять эту формулировку
              </Button>
            )}
            {onUseSuggestion && (
              <p className="mt-1.5 text-xs text-on-surface-variant">
                Формулировка откроется в поле правки — сохранится она только
                после вашего решения.
              </p>
            )}
          </div>
        )}

        {check.sources.length > 0 ? (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wide">
              Нормы, регулирующие пункт
            </p>
            {check.sources.map((source, index) => (
              <div
                key={`${source.url ?? "src"}-${index}`}
                className="rounded-lg border border-outline-variant p-3 space-y-1.5 transition-colors hover:border-primary/40"
              >
                <p className="text-sm font-medium leading-snug">
                  {source.document_title}
                  {source.article_number ? `, ст. ${source.article_number}` : ""}
                </p>
                {source.article_title && (
                  <p className="text-xs text-on-surface-variant">
                    {source.article_title}
                  </p>
                )}
                {source.content && (
                  <p className="text-xs leading-relaxed text-on-surface-variant line-clamp-5">
                    {source.content}
                  </p>
                )}
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-1">
                  {/* Редакция обязательна: без неё результат проверки
                      невоспроизводим после обновления законодательства. */}
                  <span className="text-[11px] text-outline">
                    Редакция: {source.current_revision_date ?? "не указана"}
                  </span>
                  {check.checked_on && (
                    <span className="text-[11px] text-outline">
                      Проверено{" "}
                      {new Date(check.checked_on).toLocaleDateString("ru-RU")}
                    </span>
                  )}
                  {source.url && (
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[11px] text-primary hover:underline inline-flex items-center gap-1"
                    >
                      lex.uz <ExternalLink size={11} />
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-on-surface-variant leading-relaxed rounded-lg bg-surface-container-low p-3">
            Регулирующая норма в локальной базе lex.uz не найдена — требуется
            проверка первоисточника.
          </p>
        )}
      </div>
    </Card>
  );
}

function ProgressBar({
  progress,
  locked,
}: {
  progress: ClauseList["progress"];
  locked: boolean;
}) {
  const percent = progress.total
    ? Math.round((progress.resolved / progress.total) * 100)
    : 0;

  return (
    <Card className="p-4 space-y-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm">
          <span className="font-semibold text-base tabular-nums">
            {progress.resolved}
          </span>
          <span className="text-on-surface-variant">
            {" "}
            из {progress.total} пунктов подтверждено
          </span>
          <span className="text-outline"> · {percent}%</span>
        </p>
        <div className="flex flex-wrap gap-1.5">
          {progress.deferred > 0 && (
            <Chip tone="warning">Отложено: {progress.deferred}</Chip>
          )}
          {progress.stale > 0 && (
            <Chip tone="warning">Устарело: {progress.stale}</Chip>
          )}
          {progress.complete && !locked && (
            <Chip tone="success">
              <Check size={13} /> Можно подтверждать документ
            </Chip>
          )}
        </div>
      </div>

      <SegmentedProgress
        total={progress.total}
        segments={[
          { value: progress.confirmed, tone: "success", label: "Подтверждено" },
          { value: progress.edited, tone: "info", label: "Изменено" },
          { value: progress.deferred, tone: "warning", label: "Отложено" },
        ]}
      />

      {!progress.complete && (
        <p className="text-xs text-on-surface-variant">
          Пока не подтверждены все пункты, документ не может перейти в статус
          «Подтверждён юристом».
        </p>
      )}
    </Card>
  );
}

/** «§1» — техническая метка разбивщика, юристу показываем человеческое имя. */
function clauseTitle(clause: Clause): string {
  if (clause.anchor.startsWith("преамбула")) return "Преамбула";
  if (clause.anchor.startsWith("§")) return clause.title ?? "Вводная часть";
  return `Пункт ${clause.anchor}`;
}

function dotTone(clause: Clause): Tone {
  if (isResolved(clause)) return "success";
  if (clause.decision) return "warning";
  if (clause.check?.verdict === "conflicts") return "error";
  if (clause.check?.verdict === "attention") return "warning";
  return "neutral";
}

function isResolved(clause: Clause): boolean {
  const decision = clause.decision;
  if (!decision || decision.stale) return false;
  return decision.action === "confirm" || decision.action === "edit";
}
