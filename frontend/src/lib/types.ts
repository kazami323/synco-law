export interface User {
  id: string;
  email: string;
  username: string;
  full_name: string | null;
  role: string;
  organization_id: string | null;
  is_active: boolean;
  mfa_enabled: boolean;
}

export interface Organization {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  address: string | null;
  country: string;
  invite_code: string;
  compliance_policies: string | null;
}

export interface DashboardMetrics {
  total_reviewed: number;
  high_risk: number;
  medium_risk: number;
  low_risk: number;
  pending_approval: number;
  signed: number;
  upcoming_deadlines_count: number;
  overdue_deadlines_count: number;
  in_work: number;
  /** Прирост за 7 дней по фактическим датам created_at / signed_at. */
  created_last_7d: number;
  signed_last_7d: number;
  upcoming_deadlines: UpcomingDeadline[];
  avg_review_time: number | null;
}

/** Ответ /api/dashboard/analytics — используют дашборд и страница анализа. */
export interface Analytics {
  months: { month: string; created: number; signed: number }[];
  by_type: { type: string; count: number }[];
  top_counterparties: {
    counterparty: string;
    total_amount: number;
    count: number;
  }[];
  risk: { high: number; medium: number; low: number; unscored: number };
  totals: {
    contracts: number;
    signed_amount: number;
    avg_risk: number | null;
    in_work: number;
  };
}

/** Отметка («плашка») на документе: кто и что с ним сделал. */
export interface DocumentLabel {
  kind: string;
  actor_type: "agent" | "user";
  actor_name: string | null;
  actor_role: string | null;
  created_at: string;
}

export interface Contract {
  id: string;
  title: string;
  contract_type: string | null;
  counterparty: string | null;
  status: string;
  risk_score: number | null;
  project_id: string | null;
  labels: DocumentLabel[];
  created_at: string;
  updated_at: string;
}

export interface Project {
  id: string;
  name: string;
  client: string | null;
  description: string | null;
  status: "active" | "closed";
  created_by: string | null;
  created_at: string;
  updated_at: string;
  contracts_count: number;
}

export interface ContractDetail extends Contract {
  content: string | null;
  file_path: string | null;
  amount: number | null;
  currency: string;
  created_by: string | null;
  signed_at: string | null;
  signed_by: string | null;
  signature: string | null;
  signature_timestamp: string | null;
  certificate_thumbprint: string | null;
}

export interface ContractVersion {
  id: string;
  version_number: number;
  changes_description: string | null;
  created_by: string | null;
  created_at: string;
}

export interface SignRequest {
  request_id: string;
  hash: string;
}

export interface SignConfirm {
  signature: string;
  timestamp: string;
  certificate_thumbprint: string;
}

export interface ContractDeadline {
  id: string;
  contract_id: string;
  deadline_date: string;
  type: string;
  days_left: number;
  is_notified: boolean;
}

export interface UpcomingDeadline {
  id: string;
  contract_id: string;
  contract_title: string;
  deadline_date: string;
  type: string;
  days_left: number;
}

export interface Notification {
  id: string;
  user_id: string;
  contract_id: string | null;
  text: string;
  read_at: string | null;
  created_at: string;
  contract_title: string | null;
}

/** Зеркало backend/app/core/document_types.py (каталог ТЗ, раздел 3.1). */
export const CONTRACT_TYPES: Record<string, string> = {
  supply: "Договор поставки",
  service: "Договор оказания услуг",
  contracting: "Договор подряда",
  lease: "Договор аренды",
  purchase: "Договор купли-продажи",
  employment: "Трудовой договор",
  nda: "Соглашение о конфиденциальности (NDA)",
  license: "Лицензионный договор",
  amendment: "Дополнительное соглашение",
  // Продукты работы юриста и агентов — тоже документы проекта
  risk_map: "Риск-карта",
  legal_opinion: "Правовое заключение",
  contract_review: "Проверка контракта",
  other: "Другой документ",
};

export interface ContractList {
  total: number;
  page: number;
  items: Contract[];
}

export interface UserList {
  total: number;
  page: number;
  items: User[];
}

export const ROLE_LABELS: Record<string, string> = {
  admin: "Администратор",
  head: "Руководитель отдела",
  senior_lawyer: "Старший юрист",
  lawyer: "Юрист",
  compliance: "Комплаенс",
  finance: "Финансы",
  observer: "Наблюдатель",
  external: "Внешний (просмотр)",
};


/* ---------------------------------------------------------------------------
 * Правовой движок (ТЗ, раздел 4): пункты, вердикты, решения юриста
 * ------------------------------------------------------------------------ */

/** Норма со снимком редакции на дату проверки. */
export interface ClauseSource {
  document_title: string | null;
  document_number: string | null;
  article_number: string | null;
  article_title: string | null;
  content: string | null;
  url: string | null;
  current_revision_date: string | null;
  status: string | null;
}

export type ClauseVerdict = "compliant" | "conflicts" | "attention" | "no_norm";

export interface ClauseCheck {
  verdict: ClauseVerdict;
  rationale: string | null;
  suggested_text: string | null;
  sources: ClauseSource[];
  checked_on: string | null;
  created_at: string | null;
  /** Текст пункта изменился после проверки — вердикт относится к прежней редакции. */
  stale: boolean;
}

export type ClauseAction = "confirm" | "edit" | "comment" | "defer";

export interface ClauseDecision {
  id: string;
  action: ClauseAction;
  comment: string | null;
  new_text: string | null;
  decided_by: string | null;
  decided_by_name: string | null;
  created_at: string;
  /** Решение принято по другой редакции пункта: текст изменили после него. */
  stale: boolean;
}

export interface Clause {
  id: string;
  anchor: string;
  number: string | null;
  level: number;
  title: string | null;
  content: string;
  position: number;
  parent_anchor: string | null;
  check: ClauseCheck | null;
  decision: ClauseDecision | null;
  comments_count: number;
}

export interface ClauseProgress {
  total: number;
  confirmed: number;
  edited: number;
  deferred: number;
  commented: number;
  untouched: number;
  stale: number;
  resolved: number;
  complete: boolean;
}

export interface ClauseList {
  contract_id: string;
  status: string;
  locked: boolean;
  progress: ClauseProgress;
  items: Clause[];
}

export type ReviewModule = "clauses" | "logic" | "risks";

export interface ReviewRun {
  id: string;
  module: ReviewModule;
  status: "running" | "done" | "failed";
  party_side: string | null;
  clauses_total: number;
  findings_total: number;
  summary: string | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface ReviewSummary {
  contract_id: string;
  status: string;
  clauses: ClauseProgress & {
    checked: number;
    verdicts: Record<ClauseVerdict, number>;
  };
  logic: {
    total: number;
    open: number;
    resolved: number;
    by_category: Record<string, number>;
  };
  risks: {
    total: number;
    open: number;
    resolved: number;
    by_level: Record<string, number>;
    by_category: Record<string, number>;
    score: number | null;
    /** «Что критично поправить до подписания» — резюме Модуля 3 (ТЗ, 4). */
    summary: string | null;
  };
  modules: Array<{
    module: ReviewModule;
    title: string;
    status: "running" | "done" | "failed" | "not_started";
    party_side: string | null;
    findings_total: number;
    summary: string | null;
    error: string | null;
    finished_at: string | null;
  }>;
}

export interface AuditEntry {
  id: string;
  action: string;
  title: string;
  detail: string | null;
  author_name: string | null;
  author_role: string | null;
  author_role_title: string | null;
  created_at: string;
}

export interface AuditPage {
  items: AuditEntry[];
  total: number;
}

export type FindingStatus = "open" | "accepted" | "rejected" | "fixed";

export interface LogicFinding {
  id: string;
  category: string;
  category_title: string | null;
  description: string;
  suggestion: string | null;
  clause_anchors: string[];
  detected_by: "rule" | "ai";
  status: FindingStatus;
  resolution_note: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface RiskFinding {
  id: string;
  category: string;
  category_title: string | null;
  level: "high" | "medium" | "low";
  level_title: string | null;
  description: string;
  consequence: string | null;
  mitigation: string | null;
  clause_anchors: string[];
  status: FindingStatus;
  resolved_at: string | null;
  created_at: string;
}

export interface DocumentComment {
  id: string;
  contract_id: string;
  clause_id: string | null;
  clause_anchor: string | null;
  text: string;
  author_id: string | null;
  author_name: string | null;
  author_role: string | null;
  resolved_at: string | null;
  created_at: string;
}

/* ---------------------------------------------------------------------------
 * База шаблонов (ТЗ, раздел 6)
 * ------------------------------------------------------------------------ */

export interface DocumentTemplate {
  id: string;
  name: string;
  doc_type: string;
  doc_type_title: string | null;
  description: string | null;
  actualized_at: string | null;
  verified_by: string | null;
  verified_by_name: string | null;
  verified_at: string | null;
  stale_reason: string | null;
  stale_since: string | null;
  is_archived: boolean;
  created_by: string | null;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentTemplateDetail extends DocumentTemplate {
  content: string;
}

export interface DocumentTypeInfo {
  value: string;
  title: string;
  group: "contract" | "work";
  required_blocks: string[];
}

/* ---------------------------------------------------------------------------
 * Версии и генерация (ТЗ, разделы 3 и 5)
 * ------------------------------------------------------------------------ */

export interface DiffPart {
  text: string;
  changed: boolean;
}

export interface DiffBlock {
  type: "equal" | "insert" | "delete" | "replace";
  old_start: number;
  new_start: number;
  old_lines: string[];
  new_lines: string[];
  inline?: Array<{ old: DiffPart[]; new: DiffPart[] }>;
}

export interface VersionDiff {
  from_version: number;
  to_version: number;
  blocks: DiffBlock[];
  summary: { added: number; removed: number; changed: number; identical: boolean };
}

/** Карточка параметров, которую юрист подтверждает перед генерацией. */
export interface DraftParams {
  contract_type: string | null;
  parties: Array<{ role: string | null; name: string | null; form: string | null }>;
  subject: string | null;
  amount: string | null;
  currency: string | null;
  payment_terms: string | null;
  deadlines: Array<{ what: string | null; value: string | null }>;
  penalties: Array<{ what: string | null; value: string | null }>;
  jurisdiction: string | null;
  other_terms: string[];
  transcript?: string | null;
  /**
   * Текст постановки задачи, по которому карточку разобрали. Нужен, чтобы
   * поймать случай «разобрали одно, дописали другое, сгенерировали третье»:
   * юрист подтверждает конкретную карточку, и документ должен собираться
   * именно по ней.
   */
  parsed_from?: string;
}

export interface ProjectContext {
  our_party?: string | null;
  counterparty?: string | null;
  parties_note?: string | null;
  amount?: number | null;
  currency?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  jurisdiction?: string | null;
  notes?: string | null;
}

export interface ProjectMember {
  id: string;
  user_id: string;
  access: "read" | "comment" | "write";
  full_name: string | null;
  email: string | null;
  role: string | null;
  created_at: string;
}

/* ---------------------------------------------------------------------------
 * Справочники интерфейса
 * ------------------------------------------------------------------------ */

export const VERDICT_LABELS: Record<
  ClauseVerdict,
  { label: string; tone: "success" | "warning" | "error" | "info" | "neutral" }
> = {
  compliant: { label: "Соответствует", tone: "success" },
  conflicts: { label: "Противоречит", tone: "error" },
  attention: { label: "Требует внимания", tone: "warning" },
  no_norm: { label: "Норма не найдена", tone: "neutral" },
};

export const CLAUSE_ACTION_LABELS: Record<ClauseAction, string> = {
  confirm: "Подтверждено",
  edit: "Изменено",
  comment: "Комментарий",
  defer: "Отложено",
};

/** Зеркало backend/app/services/logic_check.py */
export const LOGIC_CATEGORIES: Record<string, string> = {
  deadlines: "Противоречия по срокам",
  amounts: "Противоречия по суммам",
  broken_refs: "Битые перекрёстные ссылки",
  undefined_terms: "Неопределённые термины",
  duplication: "Дублирование",
  chain_gaps: "Разрывы в цепочках",
  party_naming: "Несогласованность сторон",
};

/** Зеркало backend/app/agents/risk_agent.py */
export const RISK_CATEGORIES: Record<string, string> = {
  asymmetry: "Асимметрия условий",
  gaps: "Пробелы",
  vague: "Размытые формулировки",
  financial: "Финансовые риски",
  operational: "Операционные риски",
  enforcement: "Риски исполнения",
};

export const RISK_LEVELS: Record<
  string,
  { label: string; tone: "success" | "warning" | "error" | "neutral" }
> = {
  high: { label: "Высокий", tone: "error" },
  medium: { label: "Средний", tone: "warning" },
  low: { label: "Низкий", tone: "success" },
};

export const MODULE_TITLES: Record<ReviewModule, string> = {
  clauses: "Разбивка на пункты и сверка с правовой базой",
  logic: "Сверка логики между пунктами",
  risks: "Сверка на смысл и риски",
};
