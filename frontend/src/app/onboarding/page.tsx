"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Building2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button, Card, ErrorNote, Input } from "@/components/ui";

export default function OnboardingPage() {
  const { user, loading, refresh } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState({ name: "", email: "", phone: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
    if (!loading && user?.organization_id) router.replace("/dashboard");
  }, [loading, user, router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api("/api/organizations/", {
        method: "POST",
        body: {
          name: form.name,
          email: form.email || null,
          phone: form.phone || null,
        },
      });
      await refresh();
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка");
      setBusy(false);
    }
  }

  if (loading || !user) return null;

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <Card className="w-full max-w-md p-8">
        <div className="w-12 h-12 rounded-lg bg-primary-fixed text-primary flex items-center justify-center mb-4">
          <Building2 size={24} />
        </div>
        <h2 className="text-2xl font-semibold">Создайте организацию</h2>
        <p className="text-sm text-on-surface-variant mt-1 mb-6">
          Вы станете её администратором и сможете пригласить команду.
        </p>

        <form onSubmit={onSubmit} className="space-y-4">
          <Input
            label="Название организации"
            placeholder='ООО "Компания"'
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />
          <Input
            label="Email организации (необязательно)"
            type="email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
          <Input
            label="Телефон (необязательно)"
            value={form.phone}
            onChange={(e) => setForm({ ...form, phone: e.target.value })}
          />
          {error && <ErrorNote message={error} />}
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Создаём..." : "Создать организацию"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
