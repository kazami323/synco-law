"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  CircleAlert,
  CornerDownRight,
  Scale,
  ShieldAlert,
  Wrench,
  X,
} from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import type {
  Clause,
  ClauseList,
  FindingStatus,
  LogicFinding,
  ReviewSummary,
  RiskFinding,
} from "@/lib/types";
import { RISK_LEVELS } from "@/lib/types";
import {
  Button,
  Card,
  Chip,
  EmptyState,
  ErrorNote,
  Skeleton,
  type Tone,
} from "@/components/ui";

const RESOLUTION_LABELS: Record<FindingStatus, string> = {
  open: "Открыто",
  accepted: "Правка принята",
  rejected: "Отклонено",
  fixed: "Исправлено вручную",
};

/** Цветная полоса слева — уровень внимания читается до чтения текста. */
const ACCENT: Record<Tone, string> = {
  error: "before:bg-error",
  warning: "before:bg-warning",
  success: "before:bg-success",
  info: "before:bg-primary",
  neutral: "before:bg-outline-variant",
};

function accentClass(tone: Tone) {
  return `relative overflow-hidden before:absolute before:inset-y-0 before:left-0 before:w-1 ${ACCENT[tone]}`;
}

/**
 * Модуль 2: расхождения внутри документа. ТЗ требует показывать оба
 * конфликтующих пункта рядом, чтобы юрист видел суть за секунду.
 */
export function LogicFindings({
  contractId,
  onJumpToClause,
}: {
  contractId: string;
  /** Переход к пункту. Не задан — номера пунктов остаются текстом. */
  onJumpToClause?: (anchor: string) => void;
}) {
  const qc = useQueryClient();
  const { user } = useAuth();
  const [error, setError] = useState("");

  const findings = useQuery({
    queryKey: ["logic-findings", contractId],
    queryFn: () =>
      api<LogicFinding[]>(`/api/contracts/${contractId}/logic-findings`),
  });
  const clauses = useQuery({
    queryKey: ["clauses", contractId],
    queryFn: () => api<ClauseList>(`/api/contracts/${contractId}/clauses`),
  });

  const resolve = useMutation({
    mutationFn: (payload: { id: string; status: FindingStatus }) =>
      api(`/api/logic-findings/${payload.id}`, {
        method: "PATCH",
        body: { status: payload.status },
      }),
    onSuccess: () => {
      setError("");
      qc.invalidateQueries({ queryKey: ["logic-findings", contractId] });
      qc.invalidateQueries({ queryKey: ["review-summary", contractId] });
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Не удалось сохранить решение"),
  });

  if (findings.isLoading) return <FindingsSkeleton />;
  if (findings.isError)
    return <ErrorNote message="Не удалось загрузить расхождения" />;

  const items = findings.data ?? [];
  if (!items.length) {
    return (
      <Card>
        <EmptyState
          icon={<Scale size={20} />}
          title="Расхождений не найдено"
          hint="Запустите модуль «Сверка логики между пунктами», если проверка ещё не проводилась."
        />
      </Card>
    );
  }

  const byAnchor = new Map(
    (clauses.data?.items ?? []).map((clause) => [clause.anchor, clause]),
  );
  const canResolve = can(user, "confirm_clause");
  const open = items.filter((item) => item.status === "open");
  const closed = items.filter((item) => item.status !== "open");

  return (
    <div className="space-y-3">
      {error && <ErrorNote message={error} />}

      {[...open, ...closed].map((finding, index) => {
        const resolved = finding.status !== "open";
        return (
          <Card
            key={finding.id}
            className={`${accentClass(resolved ? "neutral" : "warning")} animate-fade-in-up`}
            style={{ animationDelay: `${Math.min(index, 6) * 40}ms` }}
          >
            <div className="pl-5 pr-4 py-4 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Chip tone={resolved ? "neutral" : "warning"}>
                    {finding.category_title ?? finding.category}
                  </Chip>
                  <Chip tone="neutral">
                    {finding.detected_by === "rule" ? "Проверка кодом" : "ИИ"}
                  </Chip>
                </div>
                <Chip tone={resolved ? "success" : "info"}>
                  {RESOLUTION_LABELS[finding.status]}
                </Chip>
              </div>

              <p className="text-sm leading-[1.65]">{finding.description}</p>

              {/* Конфликтующие пункты рядом — обещание ТЗ. Битая ссылка
                  указывает на один пункт, ей половина ширины ни к чему. */}
              <div
                className={`grid gap-3 ${
                  finding.clause_anchors.length > 1
                    ? "grid-cols-1 md:grid-cols-2"
                    : "grid-cols-1"
                }`}
              >
                {finding.clause_anchors.map((anchor) => (
                  <ClauseExcerpt
                    key={anchor}
                    anchor={anchor}
                    clause={byAnchor.get(anchor)}
                    onJump={onJumpToClause}
                  />
                ))}
              </div>

              {finding.suggestion && (
                <div className="rounded-lg border border-primary/25 bg-primary-fixed/30 p-3">
                  <p className="text-xs font-semibold text-primary mb-1">
                    Предложение
                  </p>
                  <p className="text-sm leading-relaxed">{finding.suggestion}</p>
                </div>
              )}

              {canResolve && !resolved && (
                <div className="flex flex-wrap gap-2 pt-0.5">
                  <Button
                    size="sm"
                    onClick={() =>
                      resolve.mutate({ id: finding.id, status: "accepted" })
                    }
                    disabled={resolve.isPending}
                  >
                    <Check size={15} /> Принять правку
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => resolve.mutate({ id: finding.id, status: "fixed" })}
                    disabled={resolve.isPending}
                  >
                    <Wrench size={15} /> Поправил вручную
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      resolve.mutate({ id: finding.id, status: "rejected" })
                    }
                    disabled={resolve.isPending}
                  >
                    <X size={15} /> Отклонить
                  </Button>
                </div>
              )}
            </div>
          </Card>
        );
      })}
    </div>
  );
}

/**
 * Модуль 3: риски с позиции представляемой стороны — уровень, последствия
 * на практике и предложение по устранению.
 */
export function RiskFindings({
  contractId,
  onJumpToClause,
}: {
  contractId: string;
  /** Переход к пункту. Не задан — номера пунктов остаются текстом. */
  onJumpToClause?: (anchor: string) => void;
}) {
  const qc = useQueryClient();
  const { user } = useAuth();
  const [error, setError] = useState("");

  const findings = useQuery({
    queryKey: ["risk-findings", contractId],
    queryFn: () => api<RiskFinding[]>(`/api/contracts/${contractId}/risk-findings`),
  });

  // Якоря риска приходят от модели и бэкендом не сверяются с разбивкой
  // (services/review.py: `risk.get("clause_anchors")`). Ведём в пункт только
  // тогда, когда такой пункт в документе действительно есть.
  const clauses = useQuery({
    queryKey: ["clauses", contractId],
    queryFn: () => api<ClauseList>(`/api/contracts/${contractId}/clauses`),
  });

  // Резюме Модуля 3 — «что критично поправить до подписания» (ТЗ, раздел 4).
  const summary = useQuery({
    queryKey: ["review-summary", contractId],
    queryFn: () => api<ReviewSummary>(`/api/contracts/${contractId}/review`),
  });
  const verdict = summary.data?.risks.summary?.trim();

  const resolve = useMutation({
    mutationFn: (payload: { id: string; status: FindingStatus }) =>
      api(`/api/risk-findings/${payload.id}`, {
        method: "PATCH",
        body: { status: payload.status },
      }),
    onSuccess: () => {
      setError("");
      qc.invalidateQueries({ queryKey: ["risk-findings", contractId] });
      qc.invalidateQueries({ queryKey: ["review-summary", contractId] });
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Не удалось сохранить решение"),
  });

  if (findings.isLoading) return <FindingsSkeleton />;
  if (findings.isError) return <ErrorNote message="Не удалось загрузить риски" />;

  const items = findings.data ?? [];
  if (!items.length) {
    return (
      <Card>
        <EmptyState
          icon={<ShieldAlert size={20} />}
          title="Рисков не выявлено"
          hint="Запустите модуль «Сверка на смысл и риски», указав, чью сторону вы представляете."
        />
      </Card>
    );
  }

  const canResolve = can(user, "confirm_clause");
  const knownAnchors = new Set(
    (clauses.data?.items ?? []).map((clause) => clause.anchor),
  );

  return (
    <div className="space-y-3">
      {error && <ErrorNote message={error} />}

      {verdict && (
        <Card className={accentClass("warning")}>
          <div className="pl-5 pr-4 py-4">
            <h3 className="flex items-center gap-2 text-sm font-semibold">
              <ShieldAlert size={15} className="text-warning" />
              Что критично поправить до подписания
            </h3>
            <p className="mt-2 text-sm leading-relaxed whitespace-pre-wrap">
              {verdict}
            </p>
            <p className="mt-2.5 text-xs text-on-surface-variant">
              Вывод модели. Решение остаётся за юристом.
            </p>
          </div>
        </Card>
      )}

      {items.map((finding, index) => {
        const level = RISK_LEVELS[finding.level] ?? {
          label: finding.level,
          tone: "neutral" as const,
        };
        const resolved = finding.status !== "open";
        return (
          <Card
            key={finding.id}
            className={`${accentClass(resolved ? "neutral" : level.tone)} animate-fade-in-up`}
            style={{ animationDelay: `${Math.min(index, 6) * 40}ms` }}
          >
            <div className="pl-5 pr-4 py-4 space-y-2.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Chip tone={resolved ? "neutral" : level.tone}>
                    <CircleAlert size={13} /> Риск: {level.label}
                  </Chip>
                  <Chip tone="neutral">
                    {finding.category_title ?? finding.category}
                  </Chip>
                </div>
                <Chip tone={resolved ? "success" : "info"}>
                  {RESOLUTION_LABELS[finding.status]}
                </Chip>
              </div>

              <p className="text-sm leading-[1.65]">{finding.description}</p>

              {finding.consequence && (
                <p className="text-sm leading-[1.65] text-on-surface-variant">
                  <span className="font-semibold text-on-surface">
                    Последствия на практике:{" "}
                  </span>
                  {finding.consequence}
                </p>
              )}

              {finding.mitigation && (
                <div className="rounded-lg border border-success/25 bg-success/5 p-3">
                  <p className="text-xs font-semibold text-success mb-1">
                    Как устранить
                  </p>
                  <p className="text-sm leading-relaxed">{finding.mitigation}</p>
                </div>
              )}

              {finding.clause_anchors.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                  {finding.clause_anchors.map((anchor) => (
                    <ClauseJump
                      key={anchor}
                      anchor={anchor}
                      onJump={onJumpToClause}
                      known={knownAnchors.has(anchor)}
                    />
                  ))}
                </div>
              )}

              {canResolve && !resolved && (
                <div className="flex flex-wrap gap-2 pt-0.5">
                  <Button
                    size="sm"
                    onClick={() => resolve.mutate({ id: finding.id, status: "fixed" })}
                    disabled={resolve.isPending}
                  >
                    <Check size={15} /> Устранено
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() =>
                      resolve.mutate({ id: finding.id, status: "accepted" })
                    }
                    disabled={resolve.isPending}
                  >
                    Принять риск
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      resolve.mutate({ id: finding.id, status: "rejected" })
                    }
                    disabled={resolve.isPending}
                  >
                    <X size={15} /> Не относится
                  </Button>
                </div>
              )}
            </div>
          </Card>
        );
      })}
    </div>
  );
}

function ClauseExcerpt({
  anchor,
  clause,
  onJump,
}: {
  anchor: string;
  clause: Clause | undefined;
  onJump?: (anchor: string) => void;
}) {
  return (
    <div className="rounded-lg border border-outline-variant bg-surface-container-low p-3">
      <p className="text-[11px] font-bold text-primary uppercase tracking-wide mb-1.5">
        Пункт {anchor}
      </p>
      <p className="text-[13px] leading-relaxed text-on-surface-variant line-clamp-6">
        {clause?.content ?? "Пункт не найден в текущей редакции документа."}
      </p>
      {clause && onJump && (
        <div className="mt-2">
          <ClauseJump anchor={anchor} onJump={onJump} />
        </div>
      )}
    </div>
  );
}

/**
 * Номер пункта в находке — переход к самому пункту, а не строка на экране
 * (R13, docs/SVOD_PROTOTYPE_DELTA.md, раздел 4.2; в прототипе заказчика это
 * `jumpTo(id)`). Юрист не должен искать пункт руками по списку.
 *
 * Именно `<button>`: клик на неинтерактивном элементе — дефект доступности,
 * уже разбирался в docs/AUDIT_2026-08-22.md.
 */
function ClauseJump({
  anchor,
  onJump,
  known = true,
}: {
  anchor: string;
  /** Не задан, если переходить некуда — тогда это просто номер пункта. */
  onJump?: (anchor: string) => void;
  /** Есть ли такой пункт в текущей редакции документа. */
  known?: boolean;
}) {
  if (!onJump || !known) {
    return (
      <span className="text-xs text-outline">
        Пункт {anchor}
        {known ? "" : " — не найден в текущей редакции"}
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={() => onJump(anchor)}
      className="inline-flex items-center gap-1.5 rounded-md border border-outline-variant
        bg-surface-container-lowest px-2 h-7 text-xs font-medium text-primary
        cursor-pointer transition-colors hover:border-primary hover:bg-primary-fixed/40
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
    >
      <CornerDownRight size={13} aria-hidden />К пункту {anchor}
    </button>
  );
}

function FindingsSkeleton() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-44" />
      <Skeleton className="h-44" />
    </div>
  );
}
