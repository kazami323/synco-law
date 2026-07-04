"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Check, FileText } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Notification as AppNotification } from "@/lib/types";
import { Button, Card, EmptyState, ErrorNote } from "@/components/ui";

export default function NotificationsPage() {
  const qc = useQueryClient();
  const notifications = useQuery({
    queryKey: ["notifications", "page"],
    queryFn: () => api<AppNotification[]>("/api/notifications/?limit=100"),
  });

  const markRead = useMutation({
    mutationFn: (id: string) =>
      api<AppNotification>(`/api/notifications/${id}/read`, {
        method: "PATCH",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
  });

  return (
    <div className="max-w-5xl">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-primary-fixed text-primary flex items-center justify-center">
          <Bell size={20} />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">Уведомления</h1>
          <p className="text-sm text-on-surface-variant mt-1">
            Сроки, подписи и системные события по контрактам.
          </p>
        </div>
      </div>

      <Card className="mt-6 overflow-hidden">
        {notifications.isLoading ? (
          <div className="p-6 space-y-3">
            {[0, 1, 2, 3].map((item) => (
              <div
                key={item}
                className="h-16 rounded-lg bg-surface-container animate-pulse"
              />
            ))}
          </div>
        ) : notifications.error ? (
          <div className="p-6">
            <ErrorNote
              message={
                notifications.error instanceof Error
                  ? notifications.error.message
                  : "Не удалось загрузить уведомления"
              }
            />
          </div>
        ) : notifications.data && notifications.data.length > 0 ? (
          <div className="divide-y divide-outline-variant">
            {notifications.data.map((item) => (
              <div
                key={item.id}
                className={`p-5 flex items-start gap-4 ${
                  item.read_at ? "" : "bg-primary-fixed/35"
                }`}
              >
                <div className="w-9 h-9 rounded-lg bg-surface-container text-primary flex items-center justify-center shrink-0">
                  <FileText size={18} />
                </div>
                <div className="min-w-0 flex-1">
                  {item.contract_id ? (
                    <Link
                      href={`/contracts/${item.contract_id}`}
                      className="font-medium hover:text-primary"
                    >
                      {item.contract_title || "Контракт"}
                    </Link>
                  ) : (
                    <div className="font-medium">Система</div>
                  )}
                  <div className="text-sm text-on-surface-variant mt-1">
                    {item.text}
                  </div>
                  <div className="text-xs text-outline mt-2">
                    {new Date(item.created_at).toLocaleString("ru-RU")}
                  </div>
                </div>
                {!item.read_at && (
                  <Button
                    variant="secondary"
                    disabled={markRead.isPending}
                    onClick={() => markRead.mutate(item.id)}
                  >
                    <span className="flex items-center gap-2">
                      <Check size={16} /> Прочитано
                    </span>
                  </Button>
                )}
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="Уведомлений нет" hint="Новые события появятся здесь." />
        )}
      </Card>
    </div>
  );
}
