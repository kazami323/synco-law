import { Fragment, type ReactNode } from "react";

/**
 * Лёгкий безопасный рендер markdown для ответов агентов.
 * Никакого dangerouslySetInnerHTML — весь текст идёт через React-узлы,
 * поэтому XSS невозможен. Поддержка: заголовки #/##/###, списки (-,*,•,1.),
 * **жирный**, *курсив*, `код`, --- разделитель, абзацы.
 */

// Инлайн-разметка внутри строки: **жирный**, *курсив*, `код`
function inline(text: string, keyBase: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const tok = m[0];
    const key = `${keyBase}-${i++}`;
    if (tok.startsWith("**")) {
      nodes.push(
        <strong key={key} className="font-semibold">
          {tok.slice(2, -2)}
        </strong>
      );
    } else if (tok.startsWith("`")) {
      nodes.push(
        <code
          key={key}
          className="rounded bg-surface-container px-1.5 py-0.5 text-[0.85em] font-mono"
        >
          {tok.slice(1, -1)}
        </code>
      );
    } else {
      nodes.push(
        <em key={key} className="italic">
          {tok.slice(1, -1)}
        </em>
      );
    }
    last = m.index + tok.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

type Block =
  | { type: "h"; level: number; text: string }
  | { type: "ul"; items: string[] }
  | { type: "ol"; items: string[] }
  | { type: "hr" }
  | { type: "p"; lines: string[] };

function parse(src: string): Block[] {
  const lines = src.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let para: string[] = [];

  const flush = () => {
    if (para.length) {
      blocks.push({ type: "p", lines: para });
      para = [];
    }
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      flush();
      continue;
    }
    const h = /^(#{1,3})\s+(.*)$/.exec(line);
    if (h) {
      flush();
      blocks.push({ type: "h", level: h[1].length, text: h[2] });
      continue;
    }
    if (/^(-{3,}|_{3,}|\*{3,})$/.test(line.trim())) {
      flush();
      blocks.push({ type: "hr" });
      continue;
    }
    const ol = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    if (ol) {
      const prev = blocks[blocks.length - 1];
      if (para.length) flush();
      if (prev && prev.type === "ol") prev.items.push(ol[1]);
      else blocks.push({ type: "ol", items: [ol[1]] });
      continue;
    }
    const ul = /^\s*[-*•]\s+(.*)$/.exec(line);
    if (ul) {
      const prev = blocks[blocks.length - 1];
      if (para.length) flush();
      if (prev && prev.type === "ul") prev.items.push(ul[1]);
      else blocks.push({ type: "ul", items: [ul[1]] });
      continue;
    }
    para.push(line);
  }
  flush();
  return blocks;
}

export function Markdown({ content }: { content: string }) {
  const blocks = parse(content);
  return (
    <div className="space-y-2.5 text-sm leading-relaxed">
      {blocks.map((b, i) => {
        if (b.type === "h") {
          const cls =
            b.level === 1
              ? "text-base font-semibold mt-1"
              : b.level === 2
                ? "text-sm font-semibold mt-1"
                : "text-sm font-semibold text-on-surface-variant";
          return (
            <p key={i} className={cls}>
              {inline(b.text, `h${i}`)}
            </p>
          );
        }
        if (b.type === "hr") {
          return <hr key={i} className="border-outline-variant" />;
        }
        if (b.type === "ul") {
          return (
            <ul key={i} className="space-y-1 pl-1">
              {b.items.map((it, j) => (
                <li key={j} className="flex gap-2">
                  <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-primary" />
                  <span>{inline(it, `ul${i}-${j}`)}</span>
                </li>
              ))}
            </ul>
          );
        }
        if (b.type === "ol") {
          return (
            <ol key={i} className="space-y-1 pl-1">
              {b.items.map((it, j) => (
                <li key={j} className="flex gap-2">
                  <span className="mt-0.5 min-w-[1.25rem] shrink-0 text-xs font-semibold text-primary">
                    {j + 1}.
                  </span>
                  <span>{inline(it, `ol${i}-${j}`)}</span>
                </li>
              ))}
            </ol>
          );
        }
        return (
          <p key={i} className="whitespace-pre-wrap">
            {b.lines.map((ln, j) => (
              <Fragment key={j}>
                {j > 0 && <br />}
                {inline(ln, `p${i}-${j}`)}
              </Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}
