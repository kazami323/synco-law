"use client";

import { useMutation } from "@tanstack/react-query";
import { Mic, MicOff, Wand2 } from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { api } from "@/lib/api";
import type { DraftParams } from "@/lib/types";
import { Button, Card, ErrorNote, Input } from "@/components/ui";

/* Минимальные типы Web Speech API: в lib.dom.d.ts их нет. */
interface SpeechRecognitionAlternative {
  transcript: string;
}
interface SpeechRecognitionResult {
  0: SpeechRecognitionAlternative;
  isFinal: boolean;
  length: number;
}
interface SpeechRecognitionResultList {
  length: number;
  [index: number]: SpeechRecognitionResult;
}
interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: SpeechRecognitionResultList;
}
interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

function speechRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/**
 * Шаг 3 из ТЗ, раздел 3.1: голосовой или текстовый ввод условий, затем
 * карточка извлечённых параметров, которую юрист подтверждает ДО генерации.
 *
 * Расшифровка речи идёт средствами браузера (Chrome/Edge). Если браузер её не
 * поддерживает, остаётся текстовый ввод — сценарий не ломается.
 */
export function DraftTaskInput({
  value,
  onChange,
  params,
  onParamsChange,
}: {
  value: string;
  onChange: (text: string) => void;
  params: DraftParams | null;
  onParamsChange: (params: DraftParams | null) => void;
}) {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState("");
  // Текст постановки задачи, по которому разобрали текущую карточку.
  const [parsedFrom, setParsedFrom] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);

  // Возможность браузера, а не состояние: на сервере её нет, на клиенте
  // определяется один раз. useSyncExternalStore избавляет от рассинхрона
  // разметки при гидрации.
  const voiceSupported = useSyncExternalStore(
    () => () => {},
    () => speechRecognitionCtor() !== null,
    () => false,
  );

  useEffect(() => {
    return () => recognitionRef.current?.stop();
  }, []);

  const extract = useMutation({
    mutationFn: () =>
      api<DraftParams>("/api/agents/draft/extract-params", {
        method: "POST",
        body: { text: value },
      }),
    onSuccess: (data) => {
      setError("");
      setParsedFrom(value);
      onParamsChange({ ...data, parsed_from: value });
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "Не удалось разобрать условия"),
  });

  const toggleVoice = () => {
    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }
    const Ctor = speechRecognitionCtor();
    if (!Ctor) return;

    const recognition = new Ctor();
    recognition.lang = "ru-RU";
    recognition.continuous = true;
    recognition.interimResults = false;
    let captured = "";
    recognition.onresult = (event) => {
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        if (event.results[i].isFinal) {
          captured += event.results[i][0].transcript + " ";
        }
      }
      onChange((value ? `${value} ` : "") + captured.trim());
      captured = "";
    };
    recognition.onerror = () => {
      setError("Не удалось распознать речь. Продиктуйте ещё раз или наберите текст.");
      setListening(false);
    };
    recognition.onend = () => setListening(false);
    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
  };

  const patch = (changes: Partial<DraftParams>) =>
    params && onParamsChange({ ...params, ...changes });

  // Карточка разобрана по одному тексту, а юрист дописал условие в другой:
  // подтверждал он одно, а документ собрался бы по другому. Молча подставлять
  // устаревшую карточку нельзя.
  const paramsStale = Boolean(params) && parsedFrom !== null && parsedFrom !== value;

  return (
    <div className="space-y-3">
      <div className="relative">
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          rows={5}
          placeholder="Договор поставки, поставщик — ООО, покупатель — ИП, товар — оборудование, предоплата 30%, отсрочка 60 дней, штраф за просрочку 0,1% в день, подсудность — Ташкент."
          className="w-full px-3 py-2 pr-12 rounded-lg border border-outline-variant bg-surface-container-lowest text-sm outline-none focus:border-primary"
        />
        {voiceSupported && (
          <button
            type="button"
            onClick={toggleVoice}
            title={listening ? "Остановить запись" : "Продиктовать условия"}
            className={`absolute top-2 right-2 w-8 h-8 rounded-lg flex items-center justify-center cursor-pointer transition-colors ${
              listening
                ? "bg-error/10 text-error animate-pulse"
                : "bg-primary-fixed text-primary hover:bg-primary/20"
            }`}
          >
            {listening ? <MicOff size={16} /> : <Mic size={16} />}
          </button>
        )}
      </div>

      {!voiceSupported && (
        <p className="text-xs text-outline">
          Голосовой ввод доступен в Chrome и Edge. В этом браузере наберите
          условия текстом.
        </p>
      )}

      {error && <ErrorNote message={error} />}

      {paramsStale && (
        <div className="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2.5 text-sm">
          Постановка задачи изменилась после разбора. Разберите условия заново —
          иначе документ соберётся по прежней карточке параметров.
        </div>
      )}

      <Button
        variant="secondary"
        className="w-full"
        onClick={() => extract.mutate()}
        loading={extract.isPending}
        disabled={!value.trim()}
      >
        <span className="flex items-center justify-center gap-2">
          <Wand2 size={16} /> {params ? "Разобрать заново" : "Разобрать условия"}
        </span>
      </Button>

      {params && (
        <Card className="p-3 space-y-3">
          <p className="text-sm font-semibold">
            Проверьте параметры перед генерацией
          </p>
          <p className="text-xs text-on-surface-variant">
            Система разобрала вашу постановку задачи. Поправьте любое поле —
            договор соберётся по подтверждённым значениям.
          </p>

          <Input
            label="Предмет договора"
            value={params.subject ?? ""}
            onChange={(event) => patch({ subject: event.target.value })}
          />

          <div className="space-y-2">
            <span className="block text-[13px] font-semibold">Стороны</span>
            {(params.parties.length ? params.parties : [{ role: "", name: "", form: "" }]).map(
              (party, index) => (
                <div key={index} className="grid grid-cols-2 gap-2">
                  <Input
                    placeholder="Роль (Поставщик)"
                    value={party.role ?? ""}
                    onChange={(event) => {
                      const parties = [...params.parties];
                      parties[index] = { ...parties[index], role: event.target.value };
                      patch({ parties });
                    }}
                  />
                  <Input
                    placeholder="Наименование"
                    value={party.name ?? ""}
                    onChange={(event) => {
                      const parties = [...params.parties];
                      parties[index] = { ...parties[index], name: event.target.value };
                      patch({ parties });
                    }}
                  />
                </div>
              ),
            )}
          </div>

          <div className="grid grid-cols-2 gap-2">
            <Input
              label="Сумма"
              value={params.amount ?? ""}
              onChange={(event) => patch({ amount: event.target.value })}
            />
            <Input
              label="Валюта"
              value={params.currency ?? ""}
              onChange={(event) => patch({ currency: event.target.value })}
            />
          </div>

          <Input
            label="Порядок расчётов"
            value={params.payment_terms ?? ""}
            onChange={(event) => patch({ payment_terms: event.target.value })}
          />

          <ParamList
            title="Сроки"
            items={params.deadlines}
            onChange={(deadlines) => patch({ deadlines })}
          />
          <ParamList
            title="Санкции"
            items={params.penalties}
            onChange={(penalties) => patch({ penalties })}
          />

          <Input
            label="Подсудность"
            value={params.jurisdiction ?? ""}
            onChange={(event) => patch({ jurisdiction: event.target.value })}
          />

          {params.other_terms.length > 0 && (
            <div>
              <span className="block text-[13px] font-semibold mb-1.5">
                Прочие условия
              </span>
              <ul className="text-sm text-on-surface-variant list-disc pl-5 space-y-0.5">
                {params.other_terms.map((term, index) => (
                  <li key={index}>{term}</li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

function ParamList({
  title,
  items,
  onChange,
}: {
  title: string;
  items: Array<{ what: string | null; value: string | null }>;
  onChange: (items: Array<{ what: string | null; value: string | null }>) => void;
}) {
  if (!items.length) return null;
  return (
    <div className="space-y-2">
      <span className="block text-[13px] font-semibold">{title}</span>
      {items.map((item, index) => (
        <div key={index} className="grid grid-cols-2 gap-2">
          <Input
            placeholder="Что"
            value={item.what ?? ""}
            onChange={(event) => {
              const next = [...items];
              next[index] = { ...next[index], what: event.target.value };
              onChange(next);
            }}
          />
          <Input
            placeholder="Значение"
            value={item.value ?? ""}
            onChange={(event) => {
              const next = [...items];
              next[index] = { ...next[index], value: event.target.value };
              onChange(next);
            }}
          />
        </div>
      ))}
    </div>
  );
}
