"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Scale, ShieldCheck } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { homeFor } from "@/lib/permissions";
import { Button, ErrorNote, Input } from "@/components/ui";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const me = await login(email, password);
      router.replace(me.organization_id ? homeFor(me) : "/onboarding");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Неверная почта или пароль"
          : err instanceof Error
            ? err.message
            : "Ошибка входа"
      );
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex">
      {/* Левая панель — бренд */}
      <div className="hidden lg:flex flex-col justify-between w-1/2 bg-surface-container p-10">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-primary text-on-primary flex items-center justify-center">
            <Scale size={22} />
          </div>
          <span className="font-semibold text-primary text-lg">
            AI Legal Workspace
          </span>
        </div>
        <div>
          <h1 className="text-4xl font-semibold leading-tight max-w-lg">
            Операционная система юридического отдела
          </h1>
          <p className="mt-4 text-on-surface-variant max-w-md">
            Управление контрактами, анализ рисков, соответствие
            законодательству РУз.
          </p>
          <div className="flex items-center gap-6 mt-8 pt-6 border-t border-outline-variant text-sm text-on-surface-variant">
            <span className="flex items-center gap-2">
              <ShieldCheck size={16} /> ISO 27001 Certified
            </span>
            <span>Uzbekistan Data Privacy</span>
          </div>
        </div>
        <div className="text-sm text-outline">© 2026 AI Legal Workspace</div>
      </div>

      {/* Правая панель — форма */}
      <div className="flex-1 flex items-center justify-center p-6">
        <form onSubmit={onSubmit} className="w-full max-w-md space-y-4">
          <div>
            <h2 className="text-2xl font-semibold">Вход в систему</h2>
            <p className="text-sm text-on-surface-variant mt-1">
              Пожалуйста, введите ваши учётные данные.
            </p>
          </div>

          <Input
            label="Электронная почта"
            type="email"
            placeholder="your@company.uz"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <Input
            label="Пароль"
            type="password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />

          {error && <ErrorNote message={error} />}

          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Входим..." : "Войти"}
          </Button>

          <p className="text-sm text-center text-on-surface-variant">
            Нет аккаунта?{" "}
            <Link href="/register" className="text-primary hover:underline">
              Зарегистрируйтесь
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
