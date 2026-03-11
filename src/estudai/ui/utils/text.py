"""Small text-formatting helpers for UI labels."""

from __future__ import annotations


def format_card_count(card_count: int) -> str:
    """Return a human-readable card count with correct pluralization."""
    card_word = "card" if card_count == 1 else "cards"
    return f"{card_count} {card_word}"
