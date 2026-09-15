"""Select the active sampling slot list from pack/slots.json."""

from __future__ import annotations


def active_slots():
    from dynamic_slots import load_slots

    return load_slots()


def unique_pages():
    from dynamic_slots import unique_pages as u

    return u()
