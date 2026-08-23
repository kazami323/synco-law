"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Download } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { api, apiDownload } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import type { ContractDetail, ReviewSummary } from "@/lib/types";
import { StatusChip } from "@/components/contract-chips";
import { ClauseReview } from "@/components/review/clause-review";
import { LogicFindings, RiskFindings } from "@/components/review/findings";
import {
  ReviewLauncher,
  ReviewSummaryStrip,
} from "@/components/review/review-launcher";
import { AuditTrail } from "@/components/review/audit-trail";
import { DocumentComments } from "@/components/review/comments";
import { Button, Card, Skeleton, Tabs, type Tone } from "@/components/ui";

type Tab = "clauses" | "logic" | "risks" | "comments" | "audit";

export default function ContractReviewPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>("clauses");
  const [exporting, setExporting] = useState(false);

  const contract = useQuery({
    queryKey: ["contract", id],
    queryFn: () => api<ContractDetail>(`/api/contracts/${id}`),
  });
  const summary = useQuery({
    queryKey: ["review-summary", id],
    queryFn: () => api<ReviewSummary>(`/api/contracts/${id}/review`),
  });

  const tabs: Array<{ value: Tab; label: string; count?: number | null; tone?: Tone }> = [
    {
      value: "clauses",
      label: "Пункты и нормы",
      count: summary.data?.clauses.total ?? null,
      tone: "neutral",
    },
    {
      value: "logic",
      label: "Логика документа",
      count: summary.data?.logic.open ?? null,
      tone: "warning",
    },
    {
      value: "risks",
      label: "Смысл и риски",
      count: summary.data?.risks.open ?? null,
      tone: "error",
    },
    { value: "comments", label: "Комментарии", count: null },
    { value: "audit", label: "Журнал действий", count: null },
  ];

  const exportWorking = async () => {
    setExporting(true);
    try {
      await apiDownload(
        `/api/contracts/${id}/export?fmt=docx&mode=working`,
        `${contract.data?.title ?? "документ"}-рабочая.docx`,
      );
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Шапка документа */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link
            href={`/contracts/${id}`}
            className="inline-flex items-center gap-1.5 text-sm text-on-surface-variant hover:text-primary transition-colors"
          >
            <ArrowLeft size={16} /> К документу
          </Link>
          <div className="flex flex-wrap items-center gap-3 mt-1.5">
            {contract.data ? (
              <h1 className="text-2xl font-semibold truncate">
                {contract.data.title}
              </h1>
            ) : (
              <Skeleton className="h-8 w-80" />
            )}
            {contract.data && <StatusChip status={contract.data.status} />}
          </div>
          <p className="text-sm text-on-surface-variant mt-1">
            Правовая проверка: разбивка на пункты, сверка с законодательством,
            логика и риски
          </p>
        </div>

        {can(user, "export") && (
          <Button variant="secondary" onClick={exportWorking} loading={exporting}>
            {!exporting && <Download size={16} />}
            Рабочая версия DOCX
          </Button>
        )}
      </div>

      {/* Сводка по документу — состояние читается до листания пунктов */}
      <Card className="px-4 py-1">
        <ReviewSummaryStrip contractId={id} />
      </Card>

      <ReviewLauncher contractId={id} />

      <Tabs items={tabs} value={tab} onChange={setTab} className="max-w-full overflow-x-auto" />

      <div className="min-w-0">
        {/*
          Работа по пунктам не размонтируется при переходе на другую вкладку,
          а только прячется: иначе набранная, но не сохранённая правка пункта
          исчезала молча, стоило заглянуть в «Логику» или «Журнал».
        */}
        <div className={tab === "clauses" ? "" : "hidden"}>
          <ClauseReview contractId={id} />
        </div>
        {tab === "logic" && <LogicFindings contractId={id} />}
        {tab === "risks" && <RiskFindings contractId={id} />}
        {tab === "comments" && <DocumentComments contractId={id} />}
        {tab === "audit" && <AuditTrail contractId={id} />}
      </div>
    </div>
  );
}
