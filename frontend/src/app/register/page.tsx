"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Scale } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button, ErrorNote, Input } from "@/components/ui";

export default function RegisterPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    username: "",
    password: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function set(field: keyof typeof form) {
    return (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm({ ...form, [field]: e.target.value });
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api("/api/auth/register", { method: "POST", body: form });
      await login(form.email, form.password);
      router.replace("/onboarding");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? "Пользователь с такой почтой или логином уже существует"
          : err instanceof Error
            ? err.message
            : "Ошибка регистрации"
      );
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <form onSubmit={onSubmit} className="w-full max-w-md space-y-4">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-lg bg-primary text-on-primary flex items-center justify-center">
            <Scale size={22} />
          </div>
          <span className="font-semibold text-primary text-lg">
            AI Legal Workspace
          </span>
        </div>

        <div>
          <h2 className="text-2xl font-semibold">Регистрация</h2>
          <p className="text-sm text-on-surface-variant mt-1">
            Создайте аккаунт, затем — организацию для вашей команды.
          </p>
        </div>

        <Input label="ФИО" value={form.full_name} onChange={set("full_name")} />
        <Input
          label="Электронная почта"
          type="email"
          placeholder="your@company.uz"
          value={form.email}
          onChange={set("email")}
          required
        />
        <Input
          label="Логин"
          value={form.username}
          onChange={set("username")}
          required
        />
        <Input
          label="Пароль"
          type="password"
          value={form.password}
          onChange={set("password")}
          required
          minLength={8}
        />

        {error && <ErrorNote message={error} />}

        <Button type="submit" disabled={busy} className="w-full">
          {busy ? "Создаём..." : "Создать аккаунт"}
        </Button>

        <p className="text-sm text-center text-on-surface-variant">
          Уже есть аккаунт?{" "}
          <Link href="/login" className="text-primary hover:underline">
            Войти
          </Link>
        </p>
      </form>
    </div>
  );
}
