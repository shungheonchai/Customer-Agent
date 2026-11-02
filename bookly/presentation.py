"""Render assistant Markdown without allowing executable HTML or remote images."""

import re
from datetime import UTC, datetime, timedelta
from html import escape
from html.parser import HTMLParser

from markdown_it import MarkdownIt

_markdown = MarkdownIt("js-default", {"breaks": True}).disable("image")
SOURCE_MARKER = re.compile(r"\[\[source:([a-zA-Z0-9_-]+)\]\]")


def source_date(value, *, at=None):
    recorded = datetime.fromisoformat(value)
    if recorded.tzinfo is None:
        recorded = recorded.replace(tzinfo=UTC)
    at = at or datetime.now(UTC)
    if at - timedelta(days=30) <= recorded <= at:
        return f"{recorded:%B} {recorded.day}, {recorded.year}"
    return f"{recorded:%B %Y}"


def source_reference(state, silent):
    match = SOURCE_MARKER.match(state.src, state.pos)
    if not match:
        return False
    if not silent:
        source = state.env.get("sources", {}).get(match[1])
        token = state.push("html_inline" if source else "text", "", 0)
        if source:
            label = {
                "review": "review",
                "conversation": "earlier conversation",
                "wishlist": "wishlist activity",
                "browsing": "browsing activity",
                "dismissal": "dismissal activity",
                "help_article": "help article",
            }[source["kind"]]
            date = source_date(source["recorded_at"])
            body_tag = "q" if source["kind"] in {"review", "conversation"} else "span"
            token.content = (
                '<span class="source-reference"><button type="button" class="source-trigger" '
                f'aria-label="Read {label} from {escape(date)}">{label} · {escape(date)}</button>'
                '<span class="source-popover" role="tooltip" popover="manual">'
                f"<strong>{escape(source['title'])}</strong>"
                f"<span>{escape(source['author'])} · {escape(date)}</span>"
                f"<{body_tag}>{escape(source['quote'])}</{body_tag}></span></span>"
            )
        else:
            token.content = "[source unavailable]"
    state.pos = match.end()
    return True


_markdown.inline.ruler.before("text", "source_reference", source_reference)


def render_markdown(content, sources=None):
    return _markdown.render(content, {"sources": sources or {}})


def plain_excerpt(content, limit=220):
    class TextOnly(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []

        def handle_data(self, data):
            self.parts.append(data)

    parser = TextOnly()
    parser.feed(render_markdown(SOURCE_MARKER.sub("", content)))
    text = " ".join("".join(parser.parts).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
