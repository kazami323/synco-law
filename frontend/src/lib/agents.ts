import {
  FileText,
  PenLine,
  Scale,
  ShieldAlert,
  type LucideIcon,
} from "lucide-react";

export interface AgentInfo {
  key: string;
  name: string;
  text: string;
  hint: string;
  icon: LucideIcon;
}

export const AGENTS: AgentInfo[] = [
  {
    key: "analyzer",
    name: "Contract Analyzer",
    text: "Извлекает ключевые условия, находит ошибки и противоречия в договорах.",
    hint: "Например: «проверь сроки оплаты и ответственность сторон в приложенном договоре»",
    icon: FileText,
  },
  {
    key: "law",
    name: "Law Agent",
    text: "Консультирует по законодательству РУз: ГК, ТК, НК, нормативные акты.",
    hint: "Например: «какие обязательные условия у трудового договора по ТК РУз?»",
    icon: Scale,
  },
  {
    key: "risk",
    name: "Risk Agent",
    text: "Оценивает юридические, финансовые и операционные риски сделок.",
    hint: "Например: «какие риски у предоплаты 100% без банковской гарантии?»",
    icon: ShieldAlert,
  },
  {
    key: "draft",
    name: "Draft Agent",
    text: "Составляет и редактирует тексты договоров и юридических документов.",
    hint: "Например: «составь NDA для переговоров с подрядчиком из Ташкента»",
    icon: PenLine,
  },
];

export function getAgent(key: string): AgentInfo {
  return AGENTS.find((a) => a.key === key) ?? AGENTS[0];
}
