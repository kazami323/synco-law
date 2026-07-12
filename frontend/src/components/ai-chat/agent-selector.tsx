"use client";

import { Check, ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { AGENTS, getAgent } from "@/lib/agents";

interface AgentSelectorProps {
  agentKey: string;
  onSelect: (key: string) => void;
}

export function AgentSelector({ agentKey, onSelect }: AgentSelectorProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const active = getAgent(agentKey);
  const ActiveIcon = active.icon;

  useEffect(() => {
    if (!open) return;
    function close(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative min-w-0">
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="Выбрать AI-агента"
        onClick={() => setOpen((value) => !value)}
        className="flex h-9 max-w-[13rem] items-center gap-2 rounded-lg px-2 text-sm font-medium text-on-surface outline-none transition-colors hover:bg-surface-container-high focus-visible:ring-2 focus-visible:ring-primary"
      >
        <ActiveIcon size={17} className="shrink-0 text-primary" />
        <span className="truncate">{active.name}</span>
        <ChevronDown
          size={14}
          className={`shrink-0 text-on-surface-variant transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div
          role="listbox"
          aria-label="AI-агенты"
          className="absolute bottom-full left-0 z-50 mb-2 max-h-[70vh] w-[22rem] max-w-[calc(100vw-2rem)] overflow-y-auto rounded-2xl border border-outline-variant bg-surface-container-lowest p-1.5 shadow-xl"
        >
          {AGENTS.map((candidate) => {
            const Icon = candidate.icon;
            const selected = candidate.key === agentKey;
            return (
              <button
                key={candidate.key}
                type="button"
                role="option"
                aria-selected={selected}
                onClick={() => {
                  onSelect(candidate.key);
                  setOpen(false);
                }}
                className={`flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-left outline-none transition-colors hover:bg-surface-container-low focus-visible:bg-surface-container ${selected ? "bg-primary-fixed" : ""}`}
              >
                <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-fixed text-primary">
                  <Icon size={17} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2 text-sm font-semibold text-on-surface">
                    {candidate.name}
                    <span className="inline-flex items-center gap-1 text-[10px] font-medium text-success">
                      <span className="h-1.5 w-1.5 rounded-full bg-success" />
                      Активен
                    </span>
                  </span>
                  <span className="mt-0.5 block text-xs font-medium text-primary">
                    {candidate.role}
                  </span>
                  <span className="mt-1 line-clamp-2 block text-xs leading-relaxed text-on-surface-variant">
                    {candidate.text}
                  </span>
                </span>
                {selected && <Check size={17} className="mt-1 shrink-0 text-primary" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
