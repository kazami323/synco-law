"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, Scale } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import type { ReviewModule, ReviewRun, ReviewSummary } from "@/lib/types";
import { MODULE_TITLES } from "@/lib/types";
import {
  Button,
  Chip,
  Disclosure,
  ErrorNote,
  Input,
  Metric,
  MetricRow,
  Skeleton,
  Spinner,
} from "@/components/ui";

const MODULE_ORDER: ReviewModule[] = ["clauses", "logic", "risks"];

const MODULE_NUMBERS: Record<ReviewModule, string> = {
  clauses: "Модуль 1",
  logic: "Модуль 2",
  risks: "Модуль 3",
};

/**
 * Запуск модулей проверки (ТЗ, раздел 4: по отдельности или все сразу).
 *
 * Панель свёрнута по умолчанию: запуск нужен раз в сессию, а место на экране
 * нужно постоянно — его забирает работа по пунктам.
 *
 * Модуль 3 без указания представляемой стороны не запускается: сторона меняет
 * всю оптику анализа.
 */
export function ReviewLauncher({ contractId }: { contractId: string }) {
  const qc = useQueryClient();
  const { user } = useAuth();
  const [selected, setSelected] = useState<ReviewModule[]>([...MODULE_ORDER]);
  // null — юрист поля не трогал, показываем сторону из прошлого прогона.
  const [partyOverride, setPartyOverride] = useState<string | null>(null);
  const [error, setError] = useState("");

  const summary = useQuery({
    queryKey: ["review-summary", contractId],
    queryFn: () => api<ReviewSummary>(`/api/contracts/${contractId}/review`),
    // Пока модуль идёт, сводка сама подтягивает свежий статус.
    refetchInterval: (query) =>
      query.state.data?.modules.some((module) => module.status === "running")
        ? 4000
        : false,
  });

  const storedParty =
    summary.data?.modules.find((item) => item.module === "risks")?.party_side ?? "";
  const partySide = partyOverride ?? storedParty;

  const start = useMutation({
    mutationFn: () =>
      api<ReviewRun[]>(`/api/contracts/${contractId}/review`, {
        method: "POST",
        body: { modules: selected, party_side: partySide || null },
      }),
    onSuccess: () => {
      setError("");
      qc.invalidateQueries({ queryKey: ["review-summary", contractId] });
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Не удалось запустить проверку"),
  });

  const running = summary.data?.modules.some((item) => item.status === "running");
  useEffect(() => {
    if (running === false) {
      qc.invalidateQueries({ queryKey: ["clauses", contractId] });
      qc.invalidateQueries({ queryKey: ["logic-findings", contractId] });
      qc.invalidateQueries({ queryKey: ["risk-findings", contractId] });
      qc.invalidateQueries({ queryKey: ["contract", contractId] });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running]);

  const toggle = (module: ReviewModule) =>
    setSelected((current) =>
      current.includes(module)
        ? current.filter((item) => item !== module)
        : [...current, module],
    );

  const canRun = can(user, "run_review");
  const needsParty = selected.includes("risks") && !partySide.trim();

  // Отказ сводки нельзя показывать бесконечным скелетоном: юрист будет ждать
  // экран, который уже не загрузится (аудит, P1-13).
  if (summary.isError)
    return (
      <ErrorNote message="Не удалось загрузить состояние проверки. Обновите страницу." />
    );
  // Пока сводка не пришла, неизвестно, свёрнута панель или развёрнута:
  // Disclosure читает defaultOpen один раз при монтировании.
  if (!summary.data) return <Skeleton className="h-16" />;

  const doneCount = summary.data.modules.filter(
    (item) => item.status === "done",
  ).length;

  return (
    <Disclosure
      defaultOpen={doneCount === 0}
      title={
        <span className="flex items-center gap-2">
          <Scale size={16} className="text-primary" />
          Модули проверки
        </span>
      }
      subtitle={
        running
          ? "Проверка идёт — результаты появятся автоматически"
          : `Отработало ${doneCount} из 3 · запускаются по отдельности или все сразу`
      }
      right={
        running ? (
          <Chip tone="info">
            <Spinner /> Идёт
          </Chip>
        ) : (
          <Chip tone={doneCount === 3 ? "success" : "neutral"}>
            {doneCount} / 3
          </Chip>
        )
      }
    >
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        {MODULE_ORDER.map((module) => {
          const state = summary.data?.modules.find((item) => item.module === module);
          const active = selected.includes(module);
          return (
            <label
              key={module}
              className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer
                transition-[border-color,background-color] duration-150 ${
                  active
                    ? "border-primary/60 bg-primary-fixed/25"
                    : "border-outline-variant hover:border-primary/40"
                }`}
            >
              <input
                type="checkbox"
                checked={active}
                onChange={() => toggle(module)}
                className="mt-0.5 accent-primary"
              />
              <span className="flex-1 min-w-0">
                <span className="block text-[13px] font-semibold">
                  {MODULE_NUMBERS[module]}
                </span>
                <span className="block text-xs text-on-surface-variant leading-snug mt-0.5">
                  {MODULE_TITLES[module]}
                </span>
                <span className="mt-2 flex flex-wrap items-center gap-1.5">
                  <ModuleChip status={state?.status} />
                  {state?.status === "done" && (
                    <span className="text-xs text-on-surface-variant">
                      замечаний: {state.findings_total}
                    </span>
                  )}
                </span>
                {state?.status === "failed" && state.error && (
                  <span className="block text-xs text-error mt-1 leading-snug">
                    {state.error}
                  </span>
                )}
              </span>
            </label>
          );
        })}
      </div>

      {selected.includes("risks") && (
        <div className="mt-3 rounded-lg bg-surface-container-low p-3">
          <Input
            label="Чью сторону вы представляете"
            placeholder="например: ООО «Альфа», Поставщик"
            value={partySide}
            onChange={(event) => setPartyOverride(event.target.value)}
          />
          <p className="text-xs text-on-surface-variant mt-1.5">
            Модуль 3 оценивает договор с позиции защищённости указанной стороны —
            без неё анализ теряет смысл.
          </p>
        </div>
      )}

      {error && <div className="mt-3"><ErrorNote message={error} /></div>}

      {canRun ? (
        <Button
          onClick={() => start.mutate()}
          loading={start.isPending}
          disabled={!selected.length || needsParty || running}
          className="w-full mt-3"
        >
          {!start.isPending && <Play size={16} />}
          {running ? "Проверка идёт…" : "Запустить проверку"}
        </Button>
      ) : (
        <p className="text-xs text-on-surface-variant mt-3">
          У вас нет права запускать проверки.
        </p>
      )}
    </Disclosure>
  );
}

function ModuleChip({ status }: { status: string | undefined }) {
  if (!status || status === "not_started")
    return <Chip tone="neutral">Не запускался</Chip>;
  if (status === "running")
    return (
      <Chip tone="info">
        <Spinner /> Идёт
      </Chip>
    );
  if (status === "failed") return <Chip tone="error">Ошибка</Chip>;
  return <Chip tone="success">Отработал</Chip>;
}

/**
 * Сводка по документу (ТЗ, раздел 5) — полосой над рабочей областью, чтобы
 * состояние читалось до того, как юрист начнёт листать пункты.
 */
export function ReviewSummaryStrip({ contractId }: { contractId: string }) {
  const summary = useQuery({
    queryKey: ["review-summary", contractId],
    queryFn: () => api<ReviewSummary>(`/api/contracts/${contractId}/review`),
  });

  if (summary.isError)
    return <ErrorNote message="Не удалось загрузить сводку по документу" />;
  if (!summary.data) return null;
  const { clauses, logic, risks } = summary.data;

  return (
    <MetricRow>
      <Metric
        label="Пунктов подтверждено"
        value={`${clauses.resolved} / ${clauses.total}`}
        hint={clauses.stale > 0 ? `устарело: ${clauses.stale}` : undefined}
        tone={clauses.complete ? "success" : "neutral"}
      />
      <Metric
        label="Противоречат норме"
        value={clauses.verdicts.conflicts}
        tone={clauses.verdicts.conflicts > 0 ? "error" : "neutral"}
      />
      <Metric
        label="Требуют внимания"
        value={clauses.verdicts.attention}
        tone={clauses.verdicts.attention > 0 ? "warning" : "neutral"}
      />
      <Metric
        label="Расхождений в логике"
        value={logic.open}
        hint={logic.total > 0 ? `всего ${logic.total}` : undefined}
        tone={logic.open > 0 ? "warning" : "neutral"}
      />
      <Metric
        label="Высоких рисков"
        value={risks.by_level.high ?? 0}
        hint={risks.total > 0 ? `всего ${risks.total}` : undefined}
        tone={(risks.by_level.high ?? 0) > 0 ? "error" : "neutral"}
      />
      {risks.score != null && (
        <Metric
          label="Оценка риска"
          value={`${risks.score}/100`}
          tone={risks.score >= 70 ? "error" : risks.score >= 40 ? "warning" : "success"}
        />
      )}
    </MetricRow>
  );
}
