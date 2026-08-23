import type { User } from "@/lib/types";

/** Зеркало backend/app/core/permissions.py — только для показа/скрытия UI.
 *  Реальную защиту делает бэкенд. */
export const ROLE_PERMISSIONS: Record<string, string[]> = {
  admin: [
    "view_all",
    "view_all_projects",
    "create",
    "edit",
    "delete",
    "comment",
    "confirm_clause",
    "run_review",
    "export",
    "approve",
    "archive",
    "finalize",
    "sign",
    "verify_template",
    "manage_templates",
    "manage_catalog",
    "manage_users",
  ],
  head: [
    "view_all",
    "view_all_projects",
    "create",
    "edit",
    "comment",
    "confirm_clause",
    "run_review",
    "export",
    "approve",
    "archive",
    "finalize",
    "verify_template",
    "manage_templates",
    "manage_users",
  ],
  senior_lawyer: [
    "view_all",
    "view_all_projects",
    "create",
    "edit",
    "comment",
    "confirm_clause",
    "run_review",
    "export",
    "approve",
    "archive",
    "finalize",
    "verify_template",
    "manage_templates",
  ],
  lawyer: [
    "view_assigned",
    "create",
    "edit",
    "comment",
    "confirm_clause",
    "run_review",
    "export",
    "approve",
    "archive",
    "manage_templates",
  ],
  compliance: ["view_all", "comment", "approve_compliance"],
  finance: ["view_all", "comment", "approve_finance"],
  // Наблюдатель по ТЗ: смотрит и комментирует, статусы не меняет.
  observer: ["view_all", "comment"],
  external: ["view_assigned"],
};

export function can(user: User | null, right: string): boolean {
  if (!user) return false;
  return (ROLE_PERMISSIONS[user.role] ?? []).includes(right);
}

/** Стартовая страница по роли: руководство — дашборд, остальные — контракты. */
export function homeFor(user: User | null): string {
  return can(user, "view_all") ? "/dashboard" : "/contracts";
}
