import type { User } from "@/lib/types";

/** Зеркало backend/app/core/permissions.py — только для показа/скрытия UI.
 *  Реальную защиту делает бэкенд. */
export const ROLE_PERMISSIONS: Record<string, string[]> = {
  admin: ["view_all", "create", "edit", "delete", "approve", "sign", "manage_users"],
  head: ["view_all", "create", "edit", "approve", "manage_users"],
  senior_lawyer: ["view_all", "create", "edit", "approve"],
  lawyer: ["view_assigned", "create", "edit"],
  compliance: ["view_all", "approve_compliance"],
  finance: ["view_all", "approve_finance"],
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
