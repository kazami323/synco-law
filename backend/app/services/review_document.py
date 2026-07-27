"""Сборка читаемого текста «Проверка контракта» из результатов AI-анализа.

Заказчик считает риск-карту и проверку контракта отдельными документами
проекта. Этот модуль превращает сохранённые результаты агентов (AgentResult)
в обычный текст, который кладётся в новый документ типа contract_review.
Формат — простой текст (не markdown): содержимое документа показывается как
есть, поэтому используем заглавные заголовки и дефисы-списки.
"""

from datetime import datetime, timezone


def _line(parts) -> str:
    return " ".join(str(p) for p in parts if p not in (None, "", []))


def render_review(source_title: str, analysis: dict[str, dict]) -> str:
    """analysis: {agent_name: result_data} из AgentResult (result_type=analysis)."""
    risk = analysis.get("risk_agent") or {}
    analyzer = analysis.get("contract_analyzer") or {}
    law = analysis.get("law_agent") or {}
    compliance = analysis.get("compliance_agent") or {}

    out: list[str] = []
    out.append("ПРОВЕРКА КОНТРАКТА (AI)")
    out.append(f"Документ: {source_title}")
    out.append(
        "Дата проверки: "
        + datetime.now(timezone.utc).strftime("%d.%m.%Y")
    )
    out.append("")

    # --- Итог ---
    score = risk.get("overall_score")
    out.append("ОБЩАЯ ОЦЕНКА")
    if score is not None:
        cat = risk.get("category")
        out.append(_line(["Оценка риска:", f"{score}/100", f"({cat})" if cat else ""]))
    if risk.get("recommendation"):
        out.append(f"Рекомендация: {risk['recommendation']}")
    out.append("")

    # --- Риски ---
    factors = risk.get("risk_factors") or []
    if factors:
        out.append("РИСКИ")
        for f in factors:
            out.append(
                _line([
                    "-", f.get("factor", "фактор риска"),
                    f"(важность {f['severity']}/10)" if f.get("severity") is not None else "",
                ])
            )
            if f.get("impact"):
                out.append(f"  Влияние: {f['impact']}")
        for step in risk.get("mitigation") or []:
            out.append(f"- Снижение риска: {step}")
        out.append("")

    # --- Структура ---
    errors = analyzer.get("errors") or []
    if analyzer.get("summary") or errors or analyzer.get("missing_terms"):
        out.append("СТРУКТУРА ДОГОВОРА")
        if analyzer.get("summary"):
            out.append(analyzer["summary"])
        for e in errors:
            out.append(
                _line([
                    "-",
                    f"[{e['severity']}]" if e.get("severity") else "",
                    f"{e['location']}:" if e.get("location") else "",
                    e.get("description", ""),
                ])
            )
            if e.get("recommendation"):
                out.append(f"  Рекомендация: {e['recommendation']}")
        missing = analyzer.get("missing_terms") or []
        if missing:
            out.append("Отсутствуют условия: " + ", ".join(missing))
        out.append("")

    # --- Закон ---
    issues = law.get("legal_issues") or []
    if law.get("compliance_status") or issues:
        out.append("СООТВЕТСТВИЕ ЗАКОНОДАТЕЛЬСТВУ РУз")
        if law.get("compliance_status"):
            out.append(f"Статус: {law['compliance_status']}")
        for issue in issues:
            ref = _line([
                issue.get("applicable_law", ""),
                f", {issue['article']}" if issue.get("article") else "",
            ])
            out.append(_line(["-", issue.get("issue", ""), f"({ref})" if ref else ""]))
            if issue.get("recommendation"):
                out.append(f"  Рекомендация: {issue['recommendation']}")
        out.append("")

    # --- Внутренние политики ---
    violations = compliance.get("violations") or []
    if compliance.get("status") or violations:
        out.append("ВНУТРЕННИЕ ПОЛИТИКИ")
        if compliance.get("status"):
            out.append(f"Статус: {compliance['status']}")
        for v in violations:
            out.append(
                _line([
                    "-",
                    f"[{v['severity']}]" if v.get("severity") else "",
                    f"{v['policy']}:" if v.get("policy") else "",
                    v.get("description", ""),
                ])
            )
            if v.get("recommendation"):
                out.append(f"  Рекомендация: {v['recommendation']}")
        out.append("")

    out.append("—")
    out.append(
        "Документ сформирован автоматически по результатам AI-анализа. "
        "Требует проверки юристом."
    )
    return "\n".join(out).strip()
