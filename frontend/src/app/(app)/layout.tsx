"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { Sidebar } from "@/components/sidebar";
import { Header } from "@/components/header";
import { Spinner } from "@/components/ui";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (loading) return;
    if (!user) router.replace("/login");
    else if (!user.organization_id) router.replace("/onboarding");
  }, [loading, user, router]);

  if (loading || !user || !user.organization_id) {
    return (
      <div className="min-h-screen flex items-center justify-center gap-3 text-on-surface-variant">
        <Spinner className="text-primary" />
        Загрузка...
      </div>
    );
  }

  if (pathname.startsWith("/agents")) {
    return <main className="h-dvh overflow-hidden">{children}</main>;
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar mobileOpen={menuOpen} onClose={() => setMenuOpen(false)} />
      <div className="flex-1 flex flex-col min-w-0">
        <Header onMenu={() => setMenuOpen(true)} />
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
          {/* key по маршруту перезапускает анимацию появления при навигации */}
          <div key={pathname} className="animate-fade-in-up">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
