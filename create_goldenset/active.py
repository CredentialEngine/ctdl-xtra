"""Slots for the pack currently being generated (slots.json)."""

from __future__ import annotations

from dynamic_slots import load_slots, unique_pages as _unique_pages


def active_slots():
    return load_slots()


def unique_pages():
    return _unique_pages()
