"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Gavel, ListChecks, ShieldAlert, Sparkles } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { Button, Card, Chip, ErrorNote } from "@/components/ui";

interface AnalyzerResult {
  errors?: {
    severity: string;
    location: string;
    description: string;
    recommendation: string;
  }[];
  missing_terms?: string[];
  summary?: string;
}

interface LawResult {
  legal_issues?: {
    issue: string;
    applicable_law: string;
    article: string;
    violation_type: string;
    recommendation?: string;
  }[];
  compliance_status?: string;
  recommendations?: string[];
  source?: string;
}

interface RiskResult {
  overall_score?: number;
  category?: string;
  risk_factors?: { factor: string; severity: number; impact: string }[];
  mitigation?: string[];
  recommendation?: string;
}

interface ComplianceResult {
  violations?: {
    policy: string;
    description: string;
    severity: string;
    recommendation?: string;
  }[];
  compliance_score?: number;
  status?: string;
  summary?: string;
}

interface AnalysisData {
  analyzed_at: string | null;
  analysis: {
    contract_analyzer?: AnalyzerResult;
    law_agent?: LawResult;
    risk_agent?: RiskResult;
    compliance_agent?: ComplianceResult;
  };
}

const SEVERITY_TONE: Record<string, "error" | "warning" | "info"> = {
  critical: "error",
  warning: "warning",
  info: "info",
};

const COMPLIANCE: Record<string, { label: string; tone: "success" | "warning" | "error" }> = {
  compliant: { label: "Соответствует", tone: "success" },
  partial: { label: "Частично соответствует", tone: "warning" },
  "non-compliant": { label: "Не соответствует", tone: "error" },
};

export function AnalysisSection({ contractId }: { contractId: string }) {
  const qc = useQueryClient();
  const [error, setError] = useState("");

  const analysis = useQuery({
    queryKey: ["analysis", contractId],
    queryFn: () => api<AnalysisData>(`/api/contracts/${contractId}/analysis`),
  });

  const run = useMutation({
    mutationFn: () =>
      api(`/api/contracts/${contractId}/analyze`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["analysis", contractId] });
      qc.invalidateQueries({ queryKey: ["contract", contractId] });
      qc.invalidateQueries({ queryKey: ["contracts"] });
      qc.invalidateQueries({ queryKey: ["dashboard-metrics"] });
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Ошибка анализа"),
  });

  const a = analysis.data?.analysis;
  const hasResults = a && Object.keys(a).length > 0;
  const risk = a?.risk_agent;
  const law = a?.law_agent;
  const analyzer = a?.contract_analyzer;
  const compliance = a?.compliance_agent;

  return (
    <Card className="p-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2 font-semibold">
          <Sparkles size={18} className="text-primary" />
          AI-анализ контракта
        </div>
        <Button
          loading={run.isPending}
          onClick={() => {
            setError("");
            run.mutate();
          }}
        >
          {run.isPending
            ? "Анализируем… (1-2 минуты)"
            : hasResults
              ? "Повторить анализ"
              : "Запустить AI-анализ"}
        </Button>
      </div>

      {error && <div className="mt-4"><ErrorNote message={error} /></div>}

      {run.isPending && (
        <p className="text-sm text-on-surface-variant mt-4">
          Три агента проверяют структуру, соответствие законодательству РУз и
          риски. Не закрывайте страницу.
        </p>
      )}

      {!hasResults && !run.isPending && !error && (
        <p className="text-sm text-on-surface-variant mt-4">
          Contract Analyzer найдёт ошибки в структуре, Law Agent проверит
          соответствие законодательству, Risk Agent оценит риски по шкале
          0-100.
        </p>
      )}

      {hasResults && !run.isPending && (
        <div className="mt-6 space-y-6">
          {/* Риск */}
          {risk && (
            <div>
              <div className="flex items-center gap-2 text-sm font-semibold mb-3">
                <ShieldAlert size={16} className="text-primary" /> Оценка рисков
              </div>
              <div className="flex items-center gap-4">
                <div
                  className={`text-4xl font-semibold ${
                    (risk.overall_score ?? 0) >= 70
                      ? "text-error"
                      : (risk.overall_score ?? 0) >= 40
                        ? "text-warning"
                        : "text-success"
                  }`}
                >
                  {risk.overall_score ?? "—"}
                </div>
                <div className="text-sm text-on-surface-variant">
                  из 100
                  {risk.recommendation && (
                    <div className="text-on-surface font-medium">
                      {risk.recommendation}
                    </div>
                  )}
                </div>
              </div>
              {risk.risk_factors && risk.risk_factors.length > 0 && (
                <ul className="mt-3 space-y-2">
                  {risk.risk_factors.map((f, i) => (
                    <li
                      key={i}
                      className="text-sm border border-outline-variant rounded-lg px-3 py-2 flex items-start justify-between gap-3"
                    >
                      <span>{f.factor}</span>
                      <Chip
                        tone={
                          f.severity >= 7
                            ? "error"
                            : f.severity >= 4
                              ? "warning"
                              : "neutral"
                        }
                      >
                        {f.severity}/10
                      </Chip>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Структура */}
          {analyzer && (
            <div>
              <div className="flex items-center gap-2 text-sm font-semibold mb-3">
                <ListChecks size={16} className="text-primary" /> Структура
                договора
              </div>
              {analyzer.summary && (
                <p className="text-sm text-on-surface-variant mb-3">
                  {analyzer.summary}
                </p>
              )}
              <ul className="space-y-2">
                {analyzer.errors?.map((e, i) => (
                  <li
                    key={i}
                    className="text-sm border border-outline-variant rounded-lg px-3 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <Chip tone={SEVERITY_TONE[e.severity] ?? "info"}>
                        {e.severity}
                      </Chip>
                      <span className="text-xs text-on-surface-variant">
                        {e.location}
                      </span>
                    </div>
                    <div className="mt-1.5">{e.description}</div>
                    {e.recommendation && (
                      <div className="text-xs text-on-surface-variant mt-1">
                        Рекомендация: {e.recommendation}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
              {analyzer.missing_terms && analyzer.missing_terms.length > 0 && (
                <div className="mt-3 text-sm">
                  <span className="text-on-surface-variant">
                    Отсутствуют условия:{" "}
                  </span>
                  {analyzer.missing_terms.join(", ")}
                </div>
              )}
            </div>
          )}

          {/* Закон */}
          {law && (
            <div>
              <div className="flex items-center gap-2 text-sm font-semibold mb-3">
                <Gavel size={16} className="text-primary" /> Соответствие
                законодательству РУз
                {law.compliance_status && COMPLIANCE[law.compliance_status] && (
                  <Chip tone={COMPLIANCE[law.compliance_status].tone}>
                    {COMPLIANCE[law.compliance_status].label}
                  </Chip>
                )}
              </div>
              <ul className="space-y-2">
                {law.legal_issues?.map((issue, i) => (
                  <li
                    key={i}
                    className="text-sm border border-outline-variant rounded-lg px-3 py-2"
                  >
                    <div>{issue.issue}</div>
                    <div className="text-xs text-on-surface-variant mt-1">
                      {issue.applicable_law}
                      {issue.article ? `, ${issue.article}` : ""}
                      {issue.recommendation
                        ? ` — ${issue.recommendation}`
                        : ""}
                    </div>
                  </li>
                ))}
              </ul>
              {law.source === "model_knowledge" && (
                <p className="text-xs text-outline mt-2">
                  Проверка выполнена по знаниям модели; интеграция с lex.uz
                  будет подключена при наличии API-ключа.
                </p>
              )}
            </div>
          )}

          {/* Внутренние политики */}
          {compliance && (
            <div>
              <div className="flex items-center gap-2 text-sm font-semibold mb-3">
                <BadgeCheck size={16} className="text-primary" /> Внутренние
                политики
                {compliance.status && COMPLIANCE[compliance.status] && (
                  <Chip tone={COMPLIANCE[compliance.status].tone}>
                    {COMPLIANCE[compliance.status].label}
                  </Chip>
                )}
                {typeof compliance.compliance_score === "number" && (
                  <span className="text-xs text-on-surface-variant font-normal">
                    {compliance.compliance_score}/100
                  </span>
                )}
              </div>
              {compliance.summary && (
                <p className="text-sm text-on-surface-variant mb-3">
                  {compliance.summary}
                </p>
              )}
              <ul className="space-y-2">
                {compliance.violations?.map((v, i) => (
                  <li
                    key={i}
                    className="text-sm border border-outline-variant rounded-lg px-3 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <Chip tone={SEVERITY_TONE[v.severity] ?? "info"}>
                        {v.severity}
                      </Chip>
                      <span className="text-xs text-on-surface-variant">
                        {v.policy}
                      </span>
                    </div>
                    <div className="mt-1.5">{v.description}</div>
                    {v.recommendation && (
                      <div className="text-xs text-on-surface-variant mt-1">
                        Рекомендация: {v.recommendation}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
