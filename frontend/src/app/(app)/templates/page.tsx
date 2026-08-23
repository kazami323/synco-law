"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BadgeCheck,
  LayoutTemplate,
  Plus,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import type {
  DocumentTemplate,
  DocumentTemplateDetail,
  DocumentTypeInfo,
} from "@/lib/types";
import { TypeIcon } from "@/components/contract-chips";
import {
  Button,
  Card,
  Chip,
  ConfirmButton,
  EmptyState,
  ErrorNote,
  Input,
  Modal,
  Select,
  Skeleton,
} from "@/components/ui";

/**
 * База шаблонов (ТЗ, раздел 6): шаблоны по типам документов, дата
 * актуализации, отметка «верифицирован» с указанием юриста и предупреждение,
 * если законодательство изменилось.
 */
export default function TemplatesPage() {
  const qc = useQueryClient();
  const { user } = useAuth();
  const [createOpen, setCreateOpen] = useState(false);
  const [preview, setPreview] = useState<DocumentTemplateDetail | null>(null);
  const [typeFilter, setTypeFilter] = useState("");
  const [error, setError] = useState("");

  const [name, setName] = useState("");
  const [docType, setDocType] = useState("supply");
  const [content, setContent] = useState("");

  const types = useQuery({
    queryKey: ["document-types"],
    queryFn: () => api<DocumentTypeInfo[]>("/api/document-types?group=contract"),
  });
  const templates = useQuery({
    queryKey: ["templates", typeFilter],
    queryFn: () =>
      api<DocumentTemplate[]>(
        `/api/templates${typeFilter ? `?doc_type=${typeFilter}` : ""}`,
      ),
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["templates"] });

  const create = useMutation({
    mutationFn: () =>
      api<DocumentTemplateDetail>("/api/templates", {
        method: "POST",
        body: { name, doc_type: docType, content },
      }),
    onSuccess: () => {
      setCreateOpen(false);
      setName("");
      setContent("");
      setError("");
      invalidate();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Не удалось создать шаблон"),
  });

  const verify = useMutation({
    mutationFn: (id: string) =>
      api(`/api/templates/${id}/verify`, { method: "POST" }),
    onSuccess: invalidate,
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Не удалось верифицировать"),
  });

  const archive = useMutation({
    mutationFn: (id: string) => api(`/api/templates/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      setError("");
      invalidate();
    },
    // Без этого отказ бэкенда выглядел как «клик не сработал»: карточка
    // оставалась на месте, и юрист жал ещё раз.
    onError: (err) =>
      setError(
        err instanceof Error ? err.message : "Не удалось отправить шаблон в архив",
      ),
  });

  const items = templates.data ?? [];
  const canManage = can(user, "manage_templates");
  const canVerify = can(user, "verify_template");

  // Фильтр — только по типам, у которых шаблоны реально есть: пустые
  // варианты в списке заставляют юриста проверять их вручную.
  const usedTypes = new Set(items.map((item) => item.doc_type));

  return (
    <div className="space-y-5 animate-fade-in">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">База шаблонов</h1>
          <p className="text-sm text-on-surface-variant mt-1">
            Шаблоны по типам документов с датой актуализации и отметкой
            верификации
          </p>
        </div>
        {canManage && (
          <Button onClick={() => setCreateOpen(true)}>
            <Plus size={16} /> Новый шаблон
          </Button>
        )}
      </div>

      {/* Фильтр по типам: чипами, а не выпадающим списком — типов немного,
          и юристу видно, чего в базе нет. */}
      <div className="flex flex-wrap items-center gap-2">
        <FilterChip
          active={typeFilter === ""}
          onClick={() => setTypeFilter("")}
          label="Все типы"
          count={items.length}
        />
        {(types.data ?? [])
          .filter((type) => usedTypes.has(type.value) || typeFilter === type.value)
          .map((type) => (
            <FilterChip
              key={type.value}
              active={typeFilter === type.value}
              onClick={() => setTypeFilter(type.value)}
              label={type.title}
            />
          ))}
      </div>

      {error && <ErrorNote message={error} />}

      {templates.isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          <Skeleton className="h-52" />
          <Skeleton className="h-52" />
          <Skeleton className="h-52" />
        </div>
      )}

      {templates.isError && (
        <ErrorNote message="Не удалось загрузить шаблоны. Обновите страницу." />
      )}

      {!templates.isLoading && !templates.isError && !items.length && (
        <Card>
          <EmptyState
            icon={<LayoutTemplate size={20} />}
            title="Шаблонов пока нет"
            hint="Создайте шаблон вручную или сохраните подтверждённый документ как шаблон — со страницы договора."
            action={
              canManage ? (
                <Button onClick={() => setCreateOpen(true)}>
                  <Plus size={16} /> Новый шаблон
                </Button>
              ) : undefined
            }
          />
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {items.map((template, index) => (
          <Card
            key={template.id}
            interactive
            className="flex flex-col animate-fade-in-up"
            style={{ animationDelay: `${Math.min(index, 8) * 40}ms` }}
          >
            <div className="p-4 flex items-start gap-3">
              <TypeIcon type={template.doc_type} className="w-10 h-10 shrink-0" />
              <div className="min-w-0 flex-1">
                <button
                  onClick={async () =>
                    setPreview(
                      await api<DocumentTemplateDetail>(
                        `/api/templates/${template.id}`,
                      ),
                    )
                  }
                  className="text-left font-medium leading-snug hover:text-primary transition-colors cursor-pointer block w-full truncate"
                >
                  {template.name}
                </button>
                <p className="text-[13px] text-on-surface-variant truncate">
                  {template.doc_type_title ?? template.doc_type}
                </p>
              </div>
            </div>

            {template.description && (
              <p className="px-4 -mt-1 pb-3 text-[13px] text-on-surface-variant leading-relaxed line-clamp-2">
                {template.description}
              </p>
            )}

            <div className="px-4 pb-3">
              {template.verified_at ? (
                <Chip tone="success">
                  <BadgeCheck size={13} /> Верифицирован ·{" "}
                  {template.verified_by_name ?? "юрист"}
                </Chip>
              ) : (
                <Chip tone="neutral">Не верифицирован</Chip>
              )}
            </div>

            {template.stale_reason && (
              <div className="mx-4 mb-3 rounded-lg bg-warning/10 text-warning text-xs px-3 py-2 flex gap-2 leading-relaxed">
                <TriangleAlert size={14} className="shrink-0 mt-0.5" />
                <span>{template.stale_reason}. Требуется перепроверка.</span>
              </div>
            )}

            <div className="mt-auto px-4 py-3 border-t border-outline-variant flex items-center justify-between gap-2">
              <span className="text-xs text-outline">
                {template.actualized_at
                  ? `Актуализирован ${new Date(template.actualized_at).toLocaleDateString("ru-RU")}`
                  : "Дата актуализации не указана"}
              </span>
              <div className="flex items-center gap-1.5 shrink-0">
                {canVerify && !template.verified_at && (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => verify.mutate(template.id)}
                    disabled={verify.isPending}
                  >
                    Верифицировать
                  </Button>
                )}
                {canManage && (
                  <ConfirmButton
                    onConfirm={() => archive.mutate(template.id)}
                    confirmLabel="В архив"
                    disabled={archive.isPending}
                    title="Отправить в архив"
                  >
                    <Trash2 size={15} />
                  </ConfirmButton>
                )}
              </div>
            </div>
          </Card>
        ))}
      </div>

      {createOpen && (
        <Modal title="Новый шаблон" size="lg" onClose={() => setCreateOpen(false)}>
          <div className="space-y-3">
            <Input
              label="Название"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Поставка оборудования"
            />
            <Select
              label="Тип документа"
              value={docType}
              onChange={(event) => setDocType(event.target.value)}
            >
              {(types.data ?? []).map((type) => (
                <option key={type.value} value={type.value}>
                  {type.title}
                </option>
              ))}
            </Select>
            <label className="block">
              <span className="block text-[13px] font-semibold mb-1.5">
                Текст шаблона
              </span>
              <textarea
                value={content}
                onChange={(event) => setContent(event.target.value)}
                rows={12}
                placeholder={"1. ПРЕДМЕТ ДОГОВОРА\n1.1. …"}
                className="w-full rounded-lg border border-outline-variant bg-surface-container-lowest p-3 text-sm font-mono leading-relaxed outline-none focus:border-primary focus:ring-2 focus:ring-primary-fixed"
              />
            </label>
            {error && <ErrorNote message={error} />}
            <Button
              onClick={() => create.mutate()}
              loading={create.isPending}
              disabled={!name.trim() || !content.trim()}
              className="w-full"
            >
              Создать шаблон
            </Button>
          </div>
        </Modal>
      )}

      {preview && (
        <Modal title={preview.name} size="xl" onClose={() => setPreview(null)}>
          <pre className="text-sm whitespace-pre-wrap leading-relaxed font-sans text-on-surface-variant">
            {preview.content}
          </pre>
        </Modal>
      )}
    </div>
  );
}

function FilterChip({
  active,
  onClick,
  label,
  count,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  count?: number;
}) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 h-8 px-3 rounded-full text-[13px] font-medium
        border transition-colors cursor-pointer ${
          active
            ? "border-primary bg-primary-fixed text-primary"
            : "border-outline-variant text-on-surface-variant hover:border-primary/50 hover:text-on-surface"
        }`}
    >
      {label}
      {count != null && (
        <span className="text-xs opacity-70 tabular-nums">{count}</span>
      )}
    </button>
  );
}
