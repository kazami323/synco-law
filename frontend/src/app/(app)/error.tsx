"use client";

import { RotateCcw, TriangleAlert } from "lucide-react";
import { useEffect } from "react";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-[55vh] items-center justify-center px-4">
      <div className="max-w-md text-center">
        <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-error-container text-error">
          <TriangleAlert size={23} />
        </span>
        <h1 className="mt-4 text-xl font-semibold">Не удалось открыть раздел</h1>
        <p className="mt-2 text-sm text-on-surface-variant">
          Данные не загрузились. Повторите запрос; введённая информация на других страницах не изменена.
        </p>
        <button
          type="button"
          onClick={reset}
          className="mx-auto mt-5 flex h-10 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-on-primary hover:bg-primary-hover"
        >
          <RotateCcw size={17} />
          Повторить
        </button>
      </div>
    </div>
  );
}
