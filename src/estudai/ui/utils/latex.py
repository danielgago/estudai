"""Lightweight inline LaTeX rendering helpers for Qt rich text."""

from __future__ import annotations

import html
import re

from pylatexenc.latex2text import LatexNodes2Text

_INLINE_MATH_PATTERN = re.compile(r"\$(.+?)\$")
_SCRIPT_EXTRA_CHARS = {"+", "-", "=", "/", "(", ")"}
_LATEX_TEXT_CONVERTER = LatexNodes2Text()


def render_inline_latex_html(text: str) -> str:
    """Render inline `$...$` LaTeX snippets into Qt-compatible HTML.

    Args:
        text: Input text that may contain inline LaTeX expressions.

    Returns:
        str: Rich text HTML string when LaTeX exists, otherwise original text.
    """
    normalized = text.replace(r"\(", "$").replace(r"\)", "$")
    if "$" not in normalized:
        return text
    rendered_chunks: list[str] = []
    cursor = 0
    for match in _INLINE_MATH_PATTERN.finditer(normalized):
        start, end = match.span()
        rendered_chunks.append(_escape_html_text(normalized[cursor:start]))
        rendered_chunks.append(_render_math_expression(match.group(1)))
        cursor = end
    rendered_chunks.append(_escape_html_text(normalized[cursor:]))
    return "".join(rendered_chunks)


def _render_math_expression(expression: str) -> str:
    """Render one math expression to HTML sup/sub markup.

    Args:
        expression: Expression content between math delimiters.

    Returns:
        str: HTML-rendered expression.
    """
    converted = _LATEX_TEXT_CONVERTER.latex_to_text(expression.strip())
    return _render_scripts_to_html(converted)


def _render_scripts_to_html(text: str) -> str:
    """Convert `^` and `_` script syntax to HTML tags.

    Args:
        text: Converted text that may include script markers.

    Returns:
        str: HTML with `<sup>` and `<sub>` tags.
    """
    index = 0
    rendered: list[str] = []
    while index < len(text):
        character = text[index]
        if character not in {"^", "_"}:
            rendered.append(html.escape(character))
            index += 1
            continue
        tag_name = "sup" if character == "^" else "sub"
        operand, consumed = _read_script_operand(text, index + 1)
        if consumed == 0:
            rendered.append(html.escape(character))
            index += 1
            continue
        rendered.append(f"<{tag_name}>{html.escape(operand)}</{tag_name}>")
        index += 1 + consumed
    return "".join(rendered)


def _read_script_operand(text: str, start_index: int) -> tuple[str, int]:
    """Read script operand content after `^` or `_`.

    Args:
        text: Full expression text.
        start_index: Index immediately after `^` or `_`.

    Returns:
        tuple[str, int]: Operand text and consumed character count.
    """
    if start_index >= len(text):
        return "", 0
    if text[start_index] == "{":
        depth = 1
        cursor = start_index + 1
        while cursor < len(text) and depth > 0:
            if text[cursor] == "{":
                depth += 1
            elif text[cursor] == "}":
                depth -= 1
            cursor += 1
        if depth == 0:
            raw_operand = text[start_index + 1 : cursor - 1]
            return raw_operand, cursor - start_index
        return text[start_index:], len(text) - start_index

    cursor = start_index
    while cursor < len(text):
        current = text[cursor]
        if current.isalnum() or current in _SCRIPT_EXTRA_CHARS:
            cursor += 1
            continue
        break
    if cursor == start_index:
        return text[start_index], 1
    return text[start_index:cursor], cursor - start_index


def _escape_html_text(text: str) -> str:
    """Escape plain text for HTML rendering while preserving line breaks."""
    return html.escape(text).replace("\n", "<br/>")
