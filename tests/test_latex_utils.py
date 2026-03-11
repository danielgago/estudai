"""LaTeX rendering utility tests."""

from estudai.ui.utils.latex import render_inline_latex_html


def test_render_inline_latex_html_keeps_plain_text_without_math() -> None:
    """Verify plain text is returned unchanged when no math delimiters exist."""
    text = "Simple sentence without formulas."

    assert render_inline_latex_html(text) == text


def test_render_inline_latex_html_supports_subscripts_superscripts_and_symbols() -> (
    None
):
    """Verify utility renders common inline LaTeX structures to HTML."""
    rendered = render_inline_latex_html(
        r"Recetor $GABA_A$, canais $Ca^{2+}$ e subtipo $ER\alpha$."
    )

    assert "GABA<sub>A</sub>" in rendered
    assert "Ca<sup>2+</sup>" in rendered
    assert "ERα" in rendered


def test_render_inline_latex_html_decodes_html_entities_without_math() -> None:
    """Verify HTML entities are decoded for plain flashcard text."""
    rendered = render_inline_latex_html("A &gt; B and it&#x27;s correct.")

    assert rendered == "A > B and it's correct."
