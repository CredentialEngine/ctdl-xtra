"""Select the active sampling slot list."""

from __future__ import annotations

from config import SLOTS_NAME


def active_slots():
    if SLOTS_NAME == "courses_30":
        from course_slots import SLOTS

        return SLOTS
    if SLOTS_NAME == "dynamic":
        from dynamic_slots import load_slots

        return load_slots()
    from slots import SLOTS

    return SLOTS


def unique_pages():
    if SLOTS_NAME == "courses_30":
        from course_slots import unique_pages as u

        return u()
    if SLOTS_NAME == "dynamic":
        from dynamic_slots import unique_pages as u

        return u()
    from slots import unique_pages as u

    return u()
