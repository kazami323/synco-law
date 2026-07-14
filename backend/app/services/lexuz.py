"""lex.uz HTML fetching and article parser.

lex.uz does not require an API key for public acts. This parser reads the
rendered document container (`divCont`) and splits acts into article-level
chunks that can be used by the Law Agent RAG pipeline.
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

LEX_UZ_BASE_URL = "https://lex.uz"
USER_AGENT = (
    "AI-Legal-Workspace/0.1 "
    "(legal RAG crawler; polite single-project indexing)"
)

ELEMENT_RE = re.compile(
    r'<div class="(?P<class>[^"]*?lx_elem[^"]*)"[^>]*>\s*'
    r'<div class="lx_elem2">.*?</div>\s*'
    r'<div name="(?P<id>\d+)" id="(?P=id)">(?P<body>.*?)</div>\s*</div>',
    re.DOTALL,
)
TITLE_RE = re.compile(r"<title>(?P<title>.*?)</title>", re.DOTALL | re.IGNORECASE)
REVISION_RE = re.compile(
    r'lx_date_selected[^>]*>\s*(?P<date>\d{2}\.\d{2}\.\d{4})',
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"№\s*(?P<number>[A-ZА-ЯЁЎҚҒҲ0-9/-]+)", re.IGNORECASE)
DATE_RE = re.compile(r"(?P<date>\d{2}\.\d{2}\.\d{4})")
ARTICLE_RE = re.compile(
    r"^(?:Статья|Ст\.)\s+"
    r"(?P<number>\d+[0-9A-Za-zА-Яа-яЁёЎўҚқҒғҲҳ/-]*)\.?\s*"
    r"(?P<title>.*)$",
    re.IGNORECASE,
)
UZ_ARTICLE_RE = re.compile(
    r"^(?P<number>\d+[0-9A-Za-z/-]*)\s*[-–]?\s*"
    r"(?P<label>модда|modda)\.?\s*(?P<title>.*)$",
    re.IGNORECASE,
)

BLOCK_TAG_RE = re.compile(r"</?(?:br|p|div|li|tr|td|h[1-6])[^>]*>", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"[ \t\r\f\v]+")
MULTI_NEWLINE_RE = re.compile(r"\n{3,}")

SKIP_CLASS_PARTS = (
    "FOOTNOTE",
    "ACT_SOURCE",
    "SOURCE",
    "LEX_COMMENT",
    "INDEXES",
)
NON_BODY_CLASSES = (
    "ACT_FORM",
    "ACT_TITLE",
    "TEXT_HEADER",
    "SIGNATURE",
    "ACT_ESSENTIAL_ELEMENTS",
)
SKIP_TEXT_PREFIXES = (
    "См. предыдущую редакцию",
    "См. предыдущую редакцию",
    "Комментарий LexUz",
    "Неофициальный перевод.",
)


@dataclass(frozen=True)
class LexUzElement:
    class_name: str
    element_id: str
    text: str


@dataclass(frozen=True)
class ParsedLegalArticle:
    source_article_id: str
    article_number: str | None
    title: str
    content: str
    url: str
    position: int


@dataclass(frozen=True)
class ParsedLegalDocument:
    source: str
    source_id: str
    language: str
    jurisdiction: str
    doc_type: str | None
    title: str
    number: str | None
    url: str
    adopted_at: date | None
    effective_at: date | None
    current_revision_date: date | None
    fetched_at: datetime
    articles: list[ParsedLegalArticle] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    match = DATE_RE.search(value)
    if not match:
        return None
    day, month, year = match.group("date").split(".")
    return date(int(year), int(month), int(day))


def extract_source_id(url: str) -> str:
    match = re.search(r"/docs/(\d+)", url)
    if match:
        return match.group(1)
    parsed = urlparse(url)
    fallback = parsed.path.strip("/") or parsed.netloc
    return hashlib.sha1(f"{fallback}?{parsed.query}".encode()).hexdigest()[:16]


def canonical_lexuz_url(url: str) -> str:
    if url.startswith("/"):
        return f"{LEX_UZ_BASE_URL}{url}"
    return url


async def fetch_lexuz_html(
    url: str,
    *,
    cache_dir: str | Path | None = None,
    refresh: bool = False,
    timeout: float = 30.0,
) -> str:
    url = canonical_lexuz_url(url)
    cache_path = _cache_path(url, cache_dir) if cache_dir else None
    if cache_path and cache_path.exists() and not refresh:
        return cache_path.read_text(encoding="utf-8")

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept-Language": "ru,uz;q=0.9"},
        follow_redirects=True,
        timeout=timeout,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        text = response.text

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(text, encoding="utf-8")
    return text


def parse_lexuz_html(
    html_text: str,
    *,
    url: str,
    title: str | None = None,
    doc_type: str | None = None,
    language: str = "ru",
    jurisdiction: str = "Uzbekistan",
    source_id: str | None = None,
    number: str | None = None,
    adopted_at: date | str | None = None,
    effective_at: date | str | None = None,
) -> ParsedLegalDocument:
    url = canonical_lexuz_url(url)
    elements = extract_doc_elements(html_text)
    title = title or _title_from_elements(elements) or _title_from_head(html_text) or url
    source_id = source_id or extract_source_id(url)
    number = number or _number_from_html(html_text)
    adopted_date = adopted_at if isinstance(adopted_at, date) else parse_date(adopted_at)
    effective_date = (
        effective_at if isinstance(effective_at, date) else parse_date(effective_at)
    )
    if adopted_date is None:
        adopted_date = parse_date(_title_from_head(html_text))

    articles = split_articles(elements, base_url=url)
    metadata = {
        "parser": "lexuz_divcont_v1",
        "elements_count": len(elements),
        "articles_count": len(articles),
    }
    return ParsedLegalDocument(
        source="lex.uz",
        source_id=source_id,
        language=language,
        jurisdiction=jurisdiction,
        doc_type=doc_type,
        title=_clean_title(title),
        number=number,
        url=url,
        adopted_at=adopted_date,
        effective_at=effective_date,
        current_revision_date=parse_date(_revision_from_html(html_text)),
        fetched_at=datetime.now(timezone.utc),
        articles=articles,
        metadata=metadata,
    )


def extract_doc_elements(html_text: str) -> list[LexUzElement]:
    start = html_text.find('id="divCont"')
    if start == -1:
        start = html_text.find("id='divCont'")
    document_html = html_text[start:] if start >= 0 else html_text

    elements: list[LexUzElement] = []
    for match in ELEMENT_RE.finditer(document_html):
        class_name = match.group("class")
        if _class_has(class_name, SKIP_CLASS_PARTS):
            continue
        text = html_fragment_to_text(match.group("body"))
        if not text or _should_skip_text(text):
            continue
        elements.append(
            LexUzElement(
                class_name=class_name,
                element_id=match.group("id"),
                text=text,
            )
        )
    return elements


def split_articles(
    elements: list[LexUzElement],
    *,
    base_url: str,
    min_content_chars: int = 40,
) -> list[ParsedLegalArticle]:
    articles: list[ParsedLegalArticle] = []
    current: dict | None = None

    def flush() -> None:
        nonlocal current
        if not current:
            return
        content_lines = [current["heading"], *current["body"]]
        content = "\n".join(line for line in content_lines if line).strip()
        if len(content) >= min_content_chars and current["body"]:
            articles.append(
                ParsedLegalArticle(
                    source_article_id=current["source_article_id"],
                    article_number=current["article_number"],
                    title=current["heading"],
                    content=content,
                    url=f"{base_url}#{current['source_article_id']}",
                    position=len(articles) + 1,
                )
            )
        current = None

    for element in elements:
        article_match = match_article_heading(element.text)
        if article_match:
            flush()
            number, heading = article_match
            current = {
                "source_article_id": element.element_id,
                "article_number": number,
                "heading": heading,
                "body": [],
            }
            continue

        if current is None:
            continue
        if _class_has(element.class_name, NON_BODY_CLASSES):
            continue
        if _looks_like_revision_note(element.text):
            continue
        current["body"].append(element.text)

    flush()
    if articles:
        return articles
    return fallback_chunks(elements, base_url=base_url)


def fallback_chunks(
    elements: list[LexUzElement],
    *,
    base_url: str,
    max_chars: int = 3000,
) -> list[ParsedLegalArticle]:
    body_elements = [
        element
        for element in elements
        if not _class_has(element.class_name, NON_BODY_CLASSES)
        and not _looks_like_revision_note(element.text)
    ]
    chunks: list[ParsedLegalArticle] = []
    current_lines: list[str] = []
    current_id = body_elements[0].element_id if body_elements else "document"

    def flush() -> None:
        nonlocal current_lines, current_id
        content = "\n".join(current_lines).strip()
        if not content:
            return
        chunks.append(
            ParsedLegalArticle(
                source_article_id=f"chunk-{len(chunks) + 1}-{current_id}",
                article_number=None,
                title=f"Фрагмент {len(chunks) + 1}",
                content=content,
                url=f"{base_url}#{current_id}" if current_id != "document" else base_url,
                position=len(chunks) + 1,
            )
        )
        current_lines = []

    for element in body_elements:
        pending = "\n".join([*current_lines, element.text]).strip()
        if current_lines and len(pending) > max_chars:
            flush()
            current_id = element.element_id
        current_lines.append(element.text)
    flush()
    return chunks


def match_article_heading(text: str) -> tuple[str | None, str] | None:
    text = " ".join(text.split())
    match = ARTICLE_RE.match(text) or UZ_ARTICLE_RE.match(text)
    if not match:
        return None
    number = match.group("number").strip()
    title = match.group("title").strip()
    heading = f"Статья {number}."
    if title:
        heading = f"{heading} {title}"
    return number, heading


def html_fragment_to_text(fragment: str) -> str:
    fragment = re.sub(r"<script.*?</script>", " ", fragment, flags=re.DOTALL)
    fragment = re.sub(r"<style.*?</style>", " ", fragment, flags=re.DOTALL)
    # Lex.uz marks inserted articles as 66<sup>1</sup>. Preserve that suffix
    # as 66-1 so exact article lookup does not confuse it with article 66.
    fragment = re.sub(
        r"<sup[^>]*>\s*([^<]+?)\s*</sup>",
        lambda match: f"-{match.group(1).strip()}",
        fragment,
        flags=re.IGNORECASE,
    )
    fragment = BLOCK_TAG_RE.sub("\n", fragment)
    text = TAG_RE.sub(" ", fragment)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = SPACE_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    text = MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def _cache_path(url: str, cache_dir: str | Path | None) -> Path:
    digest = hashlib.sha1(url.encode()).hexdigest()[:12]
    source_id = extract_source_id(url)
    return Path(cache_dir) / f"{source_id}-{digest}.html"


def _class_has(class_name: str, parts: tuple[str, ...]) -> bool:
    upper = class_name.upper()
    return any(part in upper for part in parts)


def _should_skip_text(text: str) -> bool:
    compact = " ".join(text.split())
    return any(compact.startswith(prefix) for prefix in SKIP_TEXT_PREFIXES)


def _looks_like_revision_note(text: str) -> bool:
    compact = " ".join(text.split())
    return (
        compact.startswith("(")
        and "редакци" in compact.lower()
        and "закон" in compact.lower()
    ) or _should_skip_text(compact)


def _title_from_elements(elements: list[LexUzElement]) -> str | None:
    for element in elements:
        if "ACT_TITLE" in element.class_name.upper() and element.text:
            return element.text
    return None


def _title_from_head(html_text: str) -> str | None:
    match = TITLE_RE.search(html_text)
    if not match:
        return None
    return html_fragment_to_text(match.group("title"))


def _clean_title(title: str) -> str:
    title = " ".join(title.split())
    title = re.sub(r"^\d{2}\.\d{2}\.\d{4}\.?\s*", "", title)
    title = re.sub(r"^[A-ZА-ЯЁЎҚҒҲ0-9/-]+-сон\s+\d{2}\.\d{2}\.\d{4}\.?\s*", "", title)
    return title.strip(" .")


def _number_from_html(html_text: str) -> str | None:
    title = _title_from_head(html_text) or ""
    match = NUMBER_RE.search(title)
    if match:
        return match.group("number")
    top = re.search(r'id="lx_lact_num_top"[^>]*>(?P<body>.*?)</div>', html_text, re.S)
    if not top:
        return None
    match = NUMBER_RE.search(html_fragment_to_text(top.group("body")))
    return match.group("number") if match else None


def _revision_from_html(html_text: str) -> str | None:
    match = REVISION_RE.search(html_text)
    return match.group("date") if match else None
