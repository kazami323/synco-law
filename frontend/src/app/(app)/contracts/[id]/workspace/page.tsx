"use client";

import { useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  BadgeCheck,
  CheckCircle2,
  Gavel,
  ListChecks,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { api, apiBackgroundTask } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import type { ContractDetail } from "@/lib/types";
import { Button, Chip, ErrorNote, Skeleton } from "@/components/ui";
import { StatusChip, TypeChip, TypeIcon } from "@/components/contract-chips";

type Tone = "error" | "warning" | "info" | "success" | "neutral";

interface Comment {
  tone: Tone;
  tag?: string;
  title: string;
  body?: string;
  rec?: string;
}

interface AnalysisData {
  analyzed_at: string | null;
  analysis: {
    contract_analyzer?: {
      errors?: {
        severity: string;
        location: string;
        description: string;
        recommendation: string;
      }[];
      missing_terms?: string[];
      summary?: string;
    };
    law_agent?: {
      legal_issues?: {
        issue: string;
        applicable_law: string;
        article: string;
        recommendation?: string;
      }[];
      compliance_status?: string;
      source?: string;
    };
    risk_agent?: {
      overall_score?: number;
      risk_factors?: { factor: string; severity: number; impact: string }[];
      mitigation?: string[];
      recommendation?: string;
    };
    compliance_agent?: {
      violations?: {
        policy: string;
        description: string;
        severity: string;
        recommendation?: string;
      }[];
      compliance_score?: number;
      status?: string;
      summary?: string;
    };
  };
}

const SEVERITY_TONE: Record<string, Tone> = {
  critical: "error",
  high: "error",
  warning: "warning",
  medium: "warning",
  info: "info",
  low: "info",
};

function analyzerComments(a?: AnalysisData["analysis"]["contract_analyzer"]): Comment[] {
  if (!a) return [];
  const out: Comment[] = [];
  for (const e of a.errors ?? [])
    out.push({
      tone: SEVERITY_TONE[e.severity] ?? "info",
      tag: e.location,
      title: e.description,
      rec: e.recommendation,
    });
  if (a.missing_terms?.length)
    out.push({
      tone: "warning",
      title: "Отсутствуют условия",
      body: a.missing_terms.join(", "),
    });
  return out;
}

function lawComments(a?: AnalysisData["analysis"]["law_agent"]): Comment[] {
  if (!a) return [];
  return (a.legal_issues ?? []).map((i) => ({
    tone: "warning" as Tone,
    tag: [i.applicable_law, i.article].filter(Boolean).join(", ") || undefined,
    title: i.issue,
    rec: i.recommendation,
  }));
}

function riskComments(a?: AnalysisData["analysis"]["risk_agent"]): Comment[] {
  if (!a) return [];
  const out: Comment[] = [];
  for (const f of a.risk_factors ?? [])
    out.push({
      tone: f.severity >= 7 ? "error" : f.severity >= 4 ? "warning" : "neutral",
      tag: `${f.severity}/10`,
      title: f.factor,
      body: f.impact,
    });
  for (const m of a.mitigation ?? [])
    out.push({ tone: "success", title: "Как снизить риск", body: m });
  return out;
}

function complianceComments(
  a?: AnalysisData["analysis"]["compliance_agent"]
): Comment[] {
  if (!a) return [];
  return (a.violations ?? []).map((v) => ({
    tone: SEVERITY_TONE[v.severity] ?? "info",
    tag: v.policy,
    title: v.description,
    rec: v.recommendation,
  }));
}

const STATUS_LABEL: Record<string, { label: string; tone: Tone }> = {
  compliant: { label: "Соответствует", tone: "success" },
  partial: { label: "Частично", tone: "warning" },
  "non-compliant": { label: "Не соответствует", tone: "error" },
};

export default function WorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const qc = useQueryClient();
  const [error, setError] = useState("");
  const canRun = can(user, "edit");

  const contract = useQuery({
    queryKey: ["contract", id],
    queryFn: () => api<ContractDetail>(`/api/contracts/${id}`),
  });
  const analysis = useQuery({
    queryKey: ["analysis", id],
    queryFn: () => api<AnalysisData>(`/api/contracts/${id}/analysis`),
  });

  const run = useMutation({
    mutationFn: () =>
      apiBackgroundTask(`/api/contracts/${id}/analyze/jobs`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["analysis", id] });
      qc.invalidateQueries({ queryKey: ["contract", id] });
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "AI-анализ недоступен"),
  });

  const an = analysis.data?.analysis;
  const panels = useMemo(
    () => ({
      analyzer: analyzerComments(an?.contract_analyzer),
      law: lawComments(an?.law_agent),
      risk: riskComments(an?.risk_agent),
      compliance: complianceComments(an?.compliance_agent),
    }),
    [an]
  );
  const hasAnalysis = an && Object.keys(an).length > 0;

  if (contract.isLoading) {
    return (
      <div className="grid grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)_320px] gap-4">
        <Skeleton className="h-[70vh]" />
        <Skeleton className="h-[70vh]" />
        <Skeleton className="h-[70vh]" />
      </div>
    );
  }
  if (!contract.data) {
    return <ErrorNote message="Контракт не найден" />;
  }
  const c = contract.data;
  const riskScore = an?.risk_agent?.overall_score ?? c.risk_score;

  const leftPanels = [
    {
      id: "analyzer",
      name: "Структура",
      sub: "Contract Analyzer",
      icon: ListChecks,
      comments: panels.analyzer,
      note: an?.contract_analyzer?.summary,
    },
    {
      id: "law",
      name: "Закон РУз",
      sub: "Law Agent",
      icon: Gavel,
      comments: panels.law,
      chip: an?.law_agent?.compliance_status
        ? STATUS_LABEL[an.law_agent.compliance_status]
        : undefined,
    },
  ];
  const rightPanels = [
    {
      id: "risk",
      name: "Риски",
      sub: "Risk Agent",
      icon: ShieldAlert,
      comments: panels.risk,
      score: riskScore,
    },
    {
      id: "compliance",
      name: "Внутренние политики",
      sub: "Compliance Agent",
      icon: BadgeCheck,
      comments: panels.compliance,
      chip: an?.compliance_agent?.status
        ? STATUS_LABEL[an.compliance_agent.status]
        : undefined,
      note: an?.compliance_agent?.summary,
    },
  ];

  return (
    <div>
      {/* Шапка рабочего стола */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div className="min-w-0">
          <button
            onClick={() => router.push(`/contracts/${id}`)}
            className="flex items-center gap-1.5 text-sm text-on-surface-variant hover:text-primary cursor-pointer"
          >
            <ArrowLeft size={16} /> К контракту
          </button>
          <div className="flex items-center gap-2.5 mt-1.5 flex-wrap">
            <TypeIcon type={c.contract_type} size={17} className="h-8 w-8 shrink-0" />
            <h1 className="text-xl font-semibold truncate max-w-[50vw]">
              {c.title}
            </h1>
            <TypeChip type={c.contract_type} />
            <StatusChip status={c.status} />
          </div>
        </div>
        {canRun && (
          <Button
            loading={run.isPending}
            onClick={() => {
              setError("");
              run.mutate();
            }}
          >
            <Sparkles size={16} />
            {run.isPending
              ? "Агенты работают…"
              : hasAnalysis
                ? "Обновить анализ"
                : "Запустить агентов"}
          </Button>
        )}
      </div>

      {error && (
        <div className="mb-4">
          <ErrorNote message={error} />
        </div>
      )}

      {/* Три колонки: агенты | документ | агенты */}
      <div className="grid grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)_320px] gap-4 items-start">
        <div className="space-y-4 order-2 xl:order-1">
          {leftPanels.map((p) => (
            <AgentPanel
              key={p.id}
              {...p}
              loading={run.isPending}
              analyzed={!!hasAnalysis}
            />
          ))}
        </div>

        {/* Документ по центру */}
        <div className="order-1 xl:order-2 bg-surface-container-lowest border border-outline-variant rounded-xl xl:sticky xl:top-4">
          <div className="flex items-center justify-between px-6 py-3 border-b border-outline-variant">
            <span className="font-semibold text-sm">Текст договора</span>
            {typeof riskScore === "number" && (
              <span className="text-xs text-on-surface-variant">
                Риск:{" "}
                <span
                  className={
                    riskScore >= 70
                      ? "text-error font-semibold"
                      : riskScore >= 40
                        ? "text-warning font-semibold"
                        : "text-success font-semibold"
                  }
                >
                  {riskScore}/100
                </span>
              </span>
            )}
          </div>
          <div className="px-8 py-6 max-h-[calc(100vh-12rem)] overflow-y-auto">
            {c.content ? (
              <pre className="whitespace-pre-wrap font-body text-[15px] leading-7 text-on-surface">
                {c.content}
              </pre>
            ) : (
              <p className="text-sm text-on-surface-variant">
                Текст договора не заполнен.
              </p>
            )}
          </div>
        </div>

        <div className="space-y-4 order-3">
          {rightPanels.map((p) => (
            <AgentPanel
              key={p.id}
              {...p}
              loading={run.isPending}
              analyzed={!!hasAnalysis}
            />
          ))}
        </div>
      </div>

      {!hasAnalysis && !run.isPending && (
        <p className="text-sm text-on-surface-variant text-center mt-6">
          Четыре агента разберут договор и оставят замечания на своих панелях.
          {canRun ? " Нажмите «Запустить агентов»." : ""}
        </p>
      )}
    </div>
  );
}

function AgentPanel({
  name,
  sub,
  icon: Icon,
  comments,
  loading,
  note,
  chip,
  score,
  analyzed,
}: {
  name: string;
  sub: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  comments: Comment[];
  loading?: boolean;
  note?: string;
  chip?: { label: string; tone: Tone };
  score?: number | null;
  analyzed?: boolean;
}) {
  return (
    <div className="bg-surface-container-lowest border border-outline-variant rounded-xl overflow-hidden">
      <div className="flex items-center gap-2.5 px-4 py-3 border-b border-outline-variant">
        <span className="w-8 h-8 rounded-lg bg-primary-fixed text-primary flex items-center justify-center shrink-0">
          <Icon size={16} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold leading-tight">{name}</div>
          <div className="text-[11px] text-on-surface-variant">{sub}</div>
        </div>
        {typeof score === "number" && (
          <span
            className={`text-lg font-semibold ${
              score >= 70
                ? "text-error"
                : score >= 40
                  ? "text-warning"
                  : "text-success"
            }`}
          >
            {score}
          </span>
        )}
        {chip && <Chip tone={chip.tone}>{chip.label}</Chip>}
        {!chip && typeof score !== "number" && comments.length > 0 && (
          <Chip tone="neutral">{comments.length}</Chip>
        )}
      </div>

      <div className="p-3 space-y-2">
        {note && (
          <p className="text-xs text-on-surface-variant px-1 pb-1">{note}</p>
        )}
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-14" />
            <Skeleton className="h-14" />
          </div>
        ) : comments.length > 0 ? (
          comments.map((cm, i) => <CommentCard key={i} c={cm} />)
        ) : analyzed ? (
          <div className="flex items-center gap-2 text-sm text-success px-1 py-2">
            <CheckCircle2 size={16} /> Замечаний нет
          </div>
        ) : (
          <div className="flex items-center gap-2 text-sm text-on-surface-variant px-1 py-2">
            <Sparkles size={15} className="text-outline" /> Ещё не проверялось
          </div>
        )}
      </div>
    </div>
  );
}

const BORDER: Record<Tone, string> = {
  error: "border-l-error",
  warning: "border-l-warning",
  info: "border-l-primary",
  success: "border-l-success",
  neutral: "border-l-outline",
};

function CommentCard({ c }: { c: Comment }) {
  return (
    <div
      className={`border border-outline-variant border-l-[3px] ${BORDER[c.tone]} rounded-lg px-3 py-2 bg-surface`}
    >
      {c.tag && (
        <div className="text-[11px] uppercase tracking-wide text-on-surface-variant mb-1">
          {c.tag}
        </div>
      )}
      <div className="text-sm text-on-surface">{c.title}</div>
      {c.body && (
        <div className="text-xs text-on-surface-variant mt-1">{c.body}</div>
      )}
      {c.rec && (
        <div className="text-xs text-primary mt-1.5">→ {c.rec}</div>
      )}
    </div>
  );
}
