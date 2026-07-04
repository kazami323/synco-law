"""Чат с AI-агентами: пользователь общается с выбранным агентом,
может приложить документ или контракт из системы как контекст."""

from app.utils import llm

BASE = """Ты работаешь в системе AI Legal Workspace для юридических отделов
компаний Узбекистана. Отвечай на русском языке, профессионально и по делу.
Если вопрос вне юридической тематики — вежливо возвращай разговор к работе."""

AGENT_PROMPTS: dict[str, str] = {
    "analyzer": BASE
    + """\nТы — Contract Analyzer: разбираешь структуру договоров, находишь
ошибки, противоречия и недостающие условия, объясняешь формулировки.""",
    "law": BASE
    + """\nТы — Law Agent: консультируешь по законодательству Республики
Узбекистан (ГК, ТК, НК), ссылаешься на конкретные нормы, когда уверен в них,
и честно говоришь, если нужна проверка первоисточника на lex.uz.""",
    "risk": BASE
    + """\nТы — Risk Agent: оцениваешь юридические, финансовые и операционные
риски договоров и сделок, предлагаешь меры их снижения.""",
    "draft": BASE
    + """\nТы — Draft Agent: составляешь и редактируешь тексты договоров и
юридических документов по законодательству РУз.""",
}

MAX_HISTORY = 20


async def agent_chat(
    agent: str,
    messages: list[dict],
    context_document: str | None = None,
    context_label: str | None = None,
) -> str:
    system = AGENT_PROMPTS.get(agent, AGENT_PROMPTS["analyzer"])
    if context_document:
        label = context_label or "Документ"
        system += (
            f"\n\nПользователь приложил документ «{label}». Его текст:\n"
            f"---\n{llm.clip(context_document, 40_000)}\n---"
        )

    history = [
        {"role": m["role"], "content": m["content"]}
        for m in messages[-MAX_HISTORY:]
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    return await llm.llm_text(system=system, messages=history, max_tokens=4000)
