"use client";

import { ArrowLeft, Mail } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { Button, Card, ErrorNote, Input } from "@/components/ui";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/api/auth/password/forgot", {
        method: "POST",
        body: { email },
      });
      setSent(true);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Не удалось отправить письмо");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-surface p-5">
      <Card className="w-full max-w-md p-7">
        <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary-fixed text-primary">
          <Mail size={21} />
        </span>
        <h1 className="mt-4 text-2xl font-semibold">Восстановление пароля</h1>
        <p className="mt-2 text-sm text-on-surface-variant">
          Укажите рабочую почту. Ссылка для смены пароля действует 30 минут.
        </p>
        {sent ? (
          <div className="mt-6 rounded-lg bg-success/10 px-4 py-3 text-sm text-success">
            Если аккаунт существует, письмо отправлено.
          </div>
        ) : (
          <form onSubmit={submit} className="mt-6 space-y-4">
            <Input label="Электронная почта" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            {error && <ErrorNote message={error} />}
            <Button type="submit" loading={busy} className="w-full">Отправить ссылку</Button>
          </form>
        )}
        <Link href="/login" className="mt-5 flex items-center justify-center gap-2 text-sm text-primary hover:underline">
          <ArrowLeft size={15} /> Вернуться ко входу
        </Link>
      </Card>
    </main>
  );
}
