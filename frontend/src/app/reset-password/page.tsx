"use client";

import { LockKeyhole } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api } from "@/lib/api";
import { Button, Card, ErrorNote, Input } from "@/components/ui";

function ResetPasswordForm() {
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (password !== confirm) {
      setError("Пароли не совпадают");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api("/api/auth/password/reset", {
        method: "POST",
        body: { token, password },
      });
      setDone(true);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Не удалось изменить пароль");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="w-full max-w-md p-7">
      <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary-fixed text-primary"><LockKeyhole size={21} /></span>
      <h1 className="mt-4 text-2xl font-semibold">Новый пароль</h1>
      {done ? (
        <div className="mt-6">
          <div className="rounded-lg bg-success/10 px-4 py-3 text-sm text-success">Пароль изменён. Все прежние сессии завершены.</div>
          <Link href="/login" className="mt-5 block text-center text-sm text-primary hover:underline">Войти</Link>
        </div>
      ) : (
        <form onSubmit={submit} className="mt-6 space-y-4">
          <Input label="Новый пароль" type="password" minLength={10} value={password} onChange={(e) => setPassword(e.target.value)} required />
          <Input label="Повторите пароль" type="password" minLength={10} value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
          {error && <ErrorNote message={error} />}
          <Button type="submit" loading={busy} disabled={!token} className="w-full">Изменить пароль</Button>
        </form>
      )}
    </Card>
  );
}

export default function ResetPasswordPage() {
  return <main className="flex min-h-screen items-center justify-center bg-surface p-5"><Suspense><ResetPasswordForm /></Suspense></main>;
}
