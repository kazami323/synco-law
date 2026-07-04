"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/lib/auth";
import { Sidebar } from "@/components/sidebar";
import { Header } from "@/components/header";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) router.replace("/login");
    else if (!user.organization_id) router.replace("/onboarding");
  }, [loading, user, router]);

  if (loading || !user || !user.organization_id) {
    return (
      <div className="min-h-screen flex items-center justify-center text-on-surface-variant">
        Загрузка...
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header />
        <main className="flex-1 overflow-y-auto p-8">{children}</main>
      </div>
    </div>
  );
}
