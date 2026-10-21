"""Template filters for safely rendering Steam's BBCode-like news content."""
from __future__ import annotations

import html
import re
from html import escape
from urllib.parse import urlsplit

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

_TOKEN_RE = re.compile(r"(\[/?[a-zA-Z*][^\]]*\])")
_ATTRIBUTE_RE = re.compile(r'([a-zA-Z_]+)\s*=\s*"([^"]*)"')
_TAG_RE = re.compile(r"^(/?)([a-zA-Z*]+)(?:(?:\s+|=).*)?$")
_YOUTUBE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")
_TAG_MAP = {
    "b": "strong",
    "i": "em",
    "u": "u",
    "strike": "s",
    "spoiler": "span",
    "code": "code",
    "quote": "blockquote",
    "p": "p",
    "h1": "h2",
    "h2": "h3",
    "h3": "h4",
    "list": "ul",
    "olist": "ol",
    "*": "li",
}


def _safe_url(value: str) -> str:
    value = html.unescape(value).strip()
    if value.startswith("{STEAM_CLAN_IMAGE}/"):
        value = (
            "https://clan.akamai.steamstatic.com/images/"
            + value.removeprefix("{STEAM_CLAN_IMAGE}/")
        )
    parts = urlsplit(value)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return ""
    return value


def _attributes(token: str) -> dict[str, str]:
    return {
        key.lower(): html.unescape(value)
        for key, value in _ATTRIBUTE_RE.findall(token)
    }


def _render_image(token: str, contents: str) -> str:
    src = _attributes(token).get("src", "")
    if not src:
        src = contents.strip()
    src = _safe_url(src)
    if not src:
        return ""
    return f'<img src="{escape(src, quote=True)}" alt="" loading="lazy">'


def _render_link_open(url: str) -> str:
    url = _safe_url(url)
    if not url:
        return ""
    return (
        f'<a href="{escape(url, quote=True)}" '
        'target="_blank" rel="noopener noreferrer">'
    )


def _next_content_token(tokens: list[str], index: int) -> tuple[int, str]:
    next_index = index + 1
    while next_index < len(tokens) and not tokens[next_index].strip():
        next_index += 1
    if next_index >= len(tokens):
        return next_index, ""
    return next_index, tokens[next_index]


@register.filter
def steam_news(value: object) -> str:
    """Convert Steam news markup to safe HTML using a small tag allowlist."""
    if not isinstance(value, str) or not value:
        return ""

    output: list[str] = []
    stack: list[tuple[str, str]] = []
    tokens = _TOKEN_RE.split(value)

    for index, token in enumerate(tokens):
        if not token:
            continue
        if not token.startswith("[") or not token.endswith("]"):
            output.append(escape(token))
            continue

        match = _TAG_RE.match(token[1:-1].strip())
        if not match:
            output.append(escape(token))
            continue
        closing, tag_name = match.groups()
        tag_name = tag_name.lower()

        if tag_name == "img":
            if not closing:
                attributes = _attributes(token)
                content_index, image_contents = _next_content_token(tokens, index)
                output.append(_render_image(token, image_contents))
                if (
                    not attributes.get("src")
                    and image_contents
                    and not image_contents.startswith("[")
                ):
                    tokens[content_index] = ""
            continue
        if tag_name == "hr":
            if not closing:
                output.append("<hr>")
            continue
        if tag_name == "br":
            if not closing:
                output.append("<br>")
            continue

        attributes = _attributes(token)
        if tag_name in {"url", "dynamiclink"}:
            if closing:
                for stack_index in range(len(stack) - 1, -1, -1):
                    if stack[stack_index][0] == tag_name:
                        while len(stack) > stack_index:
                            _, html_tag = stack.pop()
                            output.append(f"</{html_tag}>")
                        break
            else:
                url = attributes.get("href", "")
                if not url and "=" in token:
                    url = token[1:-1].split("=", 1)[1].strip().strip('"')
                content_index, next_content = _next_content_token(tokens, index)
                next_content = next_content.strip()
                if not url and tag_name == "url" and next_content:
                    url = next_content
                link_open = _render_link_open(url)
                if link_open:
                    output.append(link_open)
                    if (
                        tag_name in {"dynamiclink", "url"}
                        and next_content.lower() == f"[/{tag_name}]"
                    ):
                        output.append(escape(url))
                    elif tag_name == "url" and next_content == url:
                        tokens[content_index] = ""
                    stack.append((tag_name, "a"))
            continue

        if tag_name == "previewyoutube":
            if not closing:
                video_id = token[1:-1].split("=", 1)[-1].split(";", 1)[0].strip()
                if _YOUTUBE_ID_RE.fullmatch(video_id):
                    output.append(
                        '<div class="ratio ratio-16x9 my-3">'
                        f'<iframe src="https://www.youtube-nocookie.com/embed/{video_id}" '
                        'title="YouTube video" loading="lazy" allowfullscreen></iframe></div>'
                    )
            continue

        html_tag = _TAG_MAP.get(tag_name)
        if not html_tag:
            continue

        if closing:
            for stack_index in range(len(stack) - 1, -1, -1):
                if stack[stack_index][0] == tag_name:
                    while len(stack) > stack_index:
                        _, open_html_tag = stack.pop()
                        output.append(f"</{open_html_tag}>")
                    break
            continue

        if tag_name == "*" and stack and stack[-1] == ("*", "li"):
            stack.pop()
            output.append("</li>")
        output.append(f"<{html_tag}>")
        stack.append((tag_name, html_tag))

    while stack:
        _, html_tag = stack.pop()
        output.append(f"</{html_tag}>")
    return mark_safe("".join(output))
