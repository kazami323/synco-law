"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Building2, KeyRound } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button, Card, ErrorNote, Input } from "@/components/ui";

export default function OnboardingPage() {
  const { user, loading, refresh } = useAuth();
  const router = useRouter();
  const [joinCode, setJoinCode] = useState("");
  const [form, setForm] = useState({ name: "", email: "", phone: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<"join" | "create" | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
    if (!loading && user?.organization_id) router.replace("/dashboard");
  }, [loading, user, router]);

  async function finish() {
    await refresh();
    router.replace("/dashboard");
  }

  async function onJoin(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy("join");
    try {
      await api("/api/organizations/join", {
        method: "POST",
        body: { invite_code: joinCode },
      });
      await finish();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка присоединения");
      setBusy(null);
    }
  }

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy("create");
    try {
      await api("/api/organizations/", {
        method: "POST",
        body: {
          name: form.name,
          email: form.email || null,
          phone: form.phone || null,
        },
      });
      await finish();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка создания");
      setBusy(null);
    }
  }

  if (loading || !user) return null;

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <Card className="w-full max-w-lg p-8">
        <div className="w-12 h-12 rounded-lg bg-primary-fixed text-primary flex items-center justify-center mb-4">
          <KeyRound size={24} />
        </div>
        <h2 className="text-2xl font-semibold">Присоединитесь к организации</h2>
        <p className="text-sm text-on-surface-variant mt-1 mb-6">
          Введите код приглашения от администратора или создайте новую организацию.
        </p>

        <form onSubmit={onJoin} className="space-y-4">
          <Input
            label="Код приглашения"
            placeholder="Например: A1B2C3D4E5"
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
            required
          />
          <Button
            type="submit"
            loading={busy === "join"}
            disabled={!joinCode.trim() || busy !== null}
            className="w-full"
          >
            Присоединиться
          </Button>
        </form>

        <div className="my-6 border-t border-outline-variant" />

        <div className="flex items-center gap-2 mb-4">
          <Building2 size={18} className="text-primary" />
          <h3 className="font-semibold">Создать новую организацию</h3>
        </div>
        <form onSubmit={onCreate} className="space-y-4">
          <Input
            label="Название организации"
            placeholder='ООО "Компания"'
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />
          <Input
            label="Email организации"
            type="email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
          <Input
            label="Телефон"
            value={form.phone}
            onChange={(e) => setForm({ ...form, phone: e.target.value })}
          />
          {error && <ErrorNote message={error} />}
          <Button
            type="submit"
            variant="secondary"
            loading={busy === "create"}
            disabled={busy !== null}
            className="w-full"
          >
            Создать организацию
          </Button>
        </form>
      </Card>
    </div>
  );
}
