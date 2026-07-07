"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { IdCard, Lock, Mail, Scale, UserRound } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { homeFor } from "@/lib/permissions";
import { ErrorNote } from "@/components/ui";

/** Вход и регистрация в одной карточке: цветная панель переезжает
 *  между половинами при переключении (стили auth-* в globals.css). */
export function AuthCard({ initialMode }: { initialMode: "login" | "register" }) {
  const { login } = useAuth();
  const router = useRouter();
  const [active, setActive] = useState(initialMode === "register");

  const [loginForm, setLoginForm] = useState({ email: "", password: "" });
  const [regForm, setRegForm] = useState({
    full_name: "",
    email: "",
    username: "",
    password: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function switchMode(toRegister: boolean) {
    setActive(toRegister);
    setError("");
  }

  async function onLogin(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const me = await login(loginForm.email, loginForm.password);
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

  async function onRegister(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api("/api/auth/register", { method: "POST", body: regForm });
      await login(regForm.email, regForm.password);
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
    <div className="auth-page">
      <div className={`auth-container${active ? " active" : ""}`}>
        {/* Вход */}
        <div className="auth-form-box auth-login">
          <form onSubmit={onLogin}>
            <div className="auth-brand">
              <span className="auth-brand-badge">
                <Scale size={20} />
              </span>
              AI Legal Workspace
            </div>
            <h1>Вход</h1>
            <div className="auth-input">
              <input
                type="email"
                placeholder="Электронная почта"
                value={loginForm.email}
                onChange={(e) =>
                  setLoginForm({ ...loginForm, email: e.target.value })
                }
                required
              />
              <Mail size={19} />
            </div>
            <div className="auth-input">
              <input
                type="password"
                placeholder="Пароль"
                value={loginForm.password}
                onChange={(e) =>
                  setLoginForm({ ...loginForm, password: e.target.value })
                }
                required
              />
              <Lock size={19} />
            </div>
            {!active && error && <ErrorNote message={error} />}
            <button type="submit" className="auth-btn" disabled={busy}>
              {busy && !active ? "Входим..." : "Войти"}
            </button>
          </form>
        </div>

        {/* Регистрация */}
        <div className="auth-form-box auth-register">
          <form onSubmit={onRegister}>
            <div className="auth-brand">
              <span className="auth-brand-badge">
                <Scale size={20} />
              </span>
              AI Legal Workspace
            </div>
            <h1>Регистрация</h1>
            <div className="auth-input">
              <input
                type="text"
                placeholder="ФИО"
                value={regForm.full_name}
                onChange={(e) =>
                  setRegForm({ ...regForm, full_name: e.target.value })
                }
              />
              <IdCard size={19} />
            </div>
            <div className="auth-input">
              <input
                type="email"
                placeholder="Электронная почта"
                value={regForm.email}
                onChange={(e) => setRegForm({ ...regForm, email: e.target.value })}
                required
              />
              <Mail size={19} />
            </div>
            <div className="auth-input">
              <input
                type="text"
                placeholder="Логин"
                value={regForm.username}
                onChange={(e) =>
                  setRegForm({ ...regForm, username: e.target.value })
                }
                required
              />
              <UserRound size={19} />
            </div>
            <div className="auth-input">
              <input
                type="password"
                placeholder="Пароль (минимум 8 символов)"
                value={regForm.password}
                onChange={(e) =>
                  setRegForm({ ...regForm, password: e.target.value })
                }
                required
                minLength={8}
              />
              <Lock size={19} />
            </div>
            {active && error && <ErrorNote message={error} />}
            <button type="submit" className="auth-btn" disabled={busy}>
              {busy && active ? "Создаём..." : "Зарегистрироваться"}
            </button>
          </form>
        </div>

        {/* Переезжающая цветная панель */}
        <div className="auth-toggle">
          <div className="auth-panel auth-panel-left">
            <h1>Добро пожаловать!</h1>
            <p>Нет аккаунта? Создайте его за минуту — контракты и риски под контролем.</p>
            <button
              type="button"
              className="auth-btn auth-btn-outline"
              onClick={() => switchMode(true)}
            >
              Регистрация
            </button>
          </div>
          <div className="auth-panel auth-panel-right">
            <h1>С возвращением!</h1>
            <p>Уже есть аккаунт? Войдите, чтобы продолжить работу.</p>
            <button
              type="button"
              className="auth-btn auth-btn-outline"
              onClick={() => switchMode(false)}
            >
              Войти
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
