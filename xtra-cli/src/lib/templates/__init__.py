"""Course extractors, one module per catalog family.

Adding a family is a one-file change: write templates/<family>.py exposing
FAMILY, detect(text) -> template_id | None, and TEMPLATES = {id: fn}, then
append it to FAMILIES below. Nothing else in the pipeline changes.

Detection order across families is load bearing and preserves the order the
single-module version used, so a split cannot change what any page
classifies as. Clean Catalog's signature is the most specific (footer or
CODE: heading AND a bare Credits line), which is why it is tested first.
See CLASSIFICATION.md.
"""

from __future__ import annotations

from templates import acalog, clean_catalog, coursedog

FAMILIES = (clean_catalog, coursedog, acalog)

TEMPLATE: dict = {}
for _family in FAMILIES:
    TEMPLATE.update(_family.TEMPLATES)

FAMILY_OF = {
    tid: _family.FAMILY for _family in FAMILIES for tid in _family.TEMPLATES
}


def detect_template(text: str) -> str | None:
    """First family whose signature matches the freeze text. College name is not a signal."""
    for family in FAMILIES:
        tid = family.detect(text)
        if tid:
            return tid
    return None
