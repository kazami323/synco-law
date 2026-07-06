"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, FileText, Search, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { Button, Card, EmptyState, Input, Select, Skeleton } from "@/components/ui";
import { RiskChip, STATUS_LABELS, StatusChip, TypeChip } from "@/components/contract-chips";
import { CONTRACT_TYPES } from "@/lib/types";

interface SearchItem {
  id: string;
  title: string;
  title_highlight: string | null;
  snippets: string[];
  counterparty: string | null;
  contract_type: string | null;
  status: string | null;
  risk_score: number | null;
  created_at: string | null;
  updated_at: string | null;
}

interface SearchResponse {
  total: number;
  items: SearchItem[];
  engine: "elasticsearch" | "sql";
}

const PAGE_SIZE = 10;

const EMPTY_FILTERS = {
  contract_type: "",
  status: "",
  risk: "",
  counterparty: "",
  date_from: "",
  date_to: "",
};

export default function ArchivePage() {
  const [q, setQ] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [draft, setDraft] = useState(EMPTY_FILTERS);
  const [applied, setApplied] = useState(EMPTY_FILTERS);
  const [page, setPage] = useState(1);

  const params = new URLSearchParams();
  if (q.trim()) params.set("q", q.trim());
  Object.entries(applied).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  params.set("page", String(page));
  params.set("size", String(PAGE_SIZE));

  const results = useQuery({
    queryKey: ["archive-search", params.toString()],
    queryFn: () => api<SearchResponse>(`/api/search/?${params.toString()}`),
    placeholderData: (prev) => prev,
  });

  const total = results.data?.total ?? 0;
  const pages = Math.max(Math.ceil(total / PAGE_SIZE), 1);

  function applyFilters() {
    setApplied(draft);
    setPage(1);
  }

  function resetFilters() {
    setDraft(EMPTY_FILTERS);
    setApplied(EMPTY_FILTERS);
    setPage(1);
  }

  return (
    <div className="max-w-5xl">
      <h1 className="text-2xl font-semibold">Архив документов</h1>
      <p className="text-on-surface-variant text-sm mt-1">
        Полнотекстовый поиск по всем контрактам организации — названию,
        тексту и контрагентам.
      </p>

      {/* Поиск + фильтры */}
      <Card className="mt-6 p-4">
        <div className="flex items-center gap-3">
          <div className="relative flex-1">
            <Search
              size={18}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-outline"
            />
            <input
              autoFocus
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(1);
              }}
              placeholder="Введите поисковый запрос..."
              className="w-full h-11 pl-10 pr-3 rounded-lg border border-outline-variant bg-surface-container-lowest text-sm outline-none focus:border-primary placeholder:text-outline"
            />
          </div>
          <Button
            variant="secondary"
            onClick={() => setFiltersOpen((v) => !v)}
            className={filtersOpen ? "border-primary" : ""}
          >
            <span className="flex items-center gap-2">
              <SlidersHorizontal size={16} /> Фильтры
            </span>
          </Button>
        </div>

        {filtersOpen && (
          <div className="border-t border-outline-variant mt-4 pt-4 animate-fade-in-up">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Select
                label="Тип документа"
                value={draft.contract_type}
                onChange={(e) =>
                  setDraft({ ...draft, contract_type: e.target.value })
                }
              >
                <option value="">Все типы</option>
                {Object.entries(CONTRACT_TYPES).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
              <Select
                label="Статус"
                value={draft.status}
                onChange={(e) => setDraft({ ...draft, status: e.target.value })}
              >
                <option value="">Все статусы</option>
                {Object.entries(STATUS_LABELS).map(([value, { label }]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
              <Select
                label="Уровень риска"
                value={draft.risk}
                onChange={(e) => setDraft({ ...draft, risk: e.target.value })}
              >
                <option value="">Все уровни</option>
                <option value="high">Высокий (&gt;70)</option>
                <option value="medium">Средний (40-70)</option>
                <option value="low">Низкий (&lt;40)</option>
              </Select>
              <Input
                label="Контрагент"
                placeholder="Поиск контрагента..."
                value={draft.counterparty}
                onChange={(e) =>
                  setDraft({ ...draft, counterparty: e.target.value })
                }
              />
              <Input
                label="Период с"
                type="date"
                value={draft.date_from}
                onChange={(e) =>
                  setDraft({ ...draft, date_from: e.target.value })
                }
              />
              <Input
                label="Период по"
                type="date"
                value={draft.date_to}
                onChange={(e) => setDraft({ ...draft, date_to: e.target.value })}
              />
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <Button variant="secondary" onClick={resetFilters}>
                Сброс
              </Button>
              <Button onClick={applyFilters}>Применить</Button>
            </div>
          </div>
        )}
      </Card>

      {/* Результаты */}
      <div className="flex items-center justify-between mt-6">
        <div className="text-sm">
          Найдено результатов:{" "}
          <span className="font-semibold text-primary">
            {results.isLoading ? "…" : total}
          </span>
        </div>
        {results.data?.engine === "sql" && (
          <span className="text-xs text-outline">
            Elasticsearch офлайн — упрощённый поиск
          </span>
        )}
      </div>

      <Card className="mt-3 overflow-hidden">
        {results.isLoading ? (
          <div className="p-6 space-y-3">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-20" />
            ))}
          </div>
        ) : results.data && results.data.items.length > 0 ? (
          <div className="divide-y divide-outline-variant">
            {results.data.items.map((item) => (
              <Link
                key={item.id}
                href={`/contracts/${item.id}`}
                className="flex gap-4 px-6 py-4 hover:bg-surface-container-low transition-colors"
              >
                <div className="w-10 h-10 shrink-0 rounded-lg bg-primary-fixed text-primary flex items-center justify-center">
                  <FileText size={18} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    {item.title_highlight ? (
                      // Бэкенд экранирует HTML в подсветке (encoder=html)
                      <span
                        className="font-semibold [&_mark]:bg-warning-container [&_mark]:text-on-surface [&_mark]:rounded-sm [&_mark]:px-0.5"
                        dangerouslySetInnerHTML={{ __html: item.title_highlight }}
                      />
                    ) : (
                      <span className="font-semibold">{item.title}</span>
                    )}
                    {item.contract_type && <TypeChip type={item.contract_type} />}
                    {item.status && <StatusChip status={item.status} />}
                    <RiskChip score={item.risk_score} />
                  </div>
                  {item.snippets.length > 0 && (
                    <div className="text-sm text-on-surface-variant mt-1.5 space-y-0.5">
                      {item.snippets.map((snippet, i) => (
                        <p
                          key={i}
                          className="[&_mark]:bg-warning-container [&_mark]:text-on-surface [&_mark]:rounded-sm [&_mark]:px-0.5"
                          dangerouslySetInnerHTML={{ __html: snippet }}
                        />
                      ))}
                    </div>
                  )}
                  <div className="text-xs text-on-surface-variant mt-1.5">
                    {item.counterparty ?? "Без контрагента"}
                    {item.updated_at &&
                      ` · обновлён ${new Date(item.updated_at).toLocaleDateString("ru-RU")}`}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <EmptyState
            title="Ничего не найдено"
            hint="Измените запрос или сбросьте фильтры"
          />
        )}
      </Card>

      {/* Пагинация */}
      {pages > 1 && (
        <div className="flex items-center justify-end gap-2 mt-4">
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="w-9 h-9 rounded-lg border border-outline-variant flex items-center justify-center text-on-surface-variant hover:border-primary disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
          >
            <ChevronLeft size={16} />
          </button>
          <span className="text-sm text-on-surface-variant">
            {page} / {pages}
          </span>
          <button
            disabled={page >= pages}
            onClick={() => setPage((p) => p + 1)}
            className="w-9 h-9 rounded-lg border border-outline-variant flex items-center justify-center text-on-surface-variant hover:border-primary disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      )}
    </div>
  );
}
