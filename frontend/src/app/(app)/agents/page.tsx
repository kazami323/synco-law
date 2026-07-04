"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { AGENTS } from "@/lib/agents";
import { Chip } from "@/components/ui";

export default function AgentsPage() {
  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-semibold">AI-агенты системы</h1>
      <p className="text-on-surface-variant text-sm mt-1">
        Выберите агента — откроется чат с ним. Внутри чата агента можно
        переключить в любой момент.
      </p>

      <div className="grid md:grid-cols-2 gap-4 mt-6">
        {AGENTS.map(({ key, name, text, icon: Icon }) => (
          <Link
            key={key}
            href={`/agents/chat/${key}`}
            className="group border border-outline-variant rounded-xl p-5 bg-surface-container-lowest hover:border-primary transition-colors"
          >
            <div className="flex items-center justify-between">
              <div className="w-11 h-11 rounded-lg bg-primary-fixed text-primary flex items-center justify-center">
                <Icon size={22} />
              </div>
              <Chip tone="success">● Активен</Chip>
            </div>
            <div className="font-semibold mt-4">{name}</div>
            <div className="text-sm text-on-surface-variant mt-1">{text}</div>
            <div className="flex items-center gap-1.5 text-sm text-primary font-medium mt-4">
              Открыть чат
              <ArrowRight
                size={16}
                className="transition-transform group-hover:translate-x-1"
              />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
