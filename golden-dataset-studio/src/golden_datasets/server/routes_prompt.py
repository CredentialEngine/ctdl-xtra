"""Prompt API (W6): the text of the Prompt tab's **Copy prompt** button (spec §7.5), the same as
`golden-datasets prompt`."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..errors import UserError
from ..loop import current_review
from ..prompt import build_prompt
from .state import not_found, studio

router = APIRouter(prefix="/api")


@router.get("/catalogs/{catalog}/prompt")
def prompt(request: Request, catalog: str, rule: str | None = None, needs_work: bool = False) -> dict:
    """One rule (`rule=`), or every rule whose status is `needs work` (`needs_work=true`, also the default). Always the
    version that points Claude at the Azure root (this Studio's, or `serve --azure-root`) after a minimal setup."""
    st = studio(request)
    ctx = st.ctx(catalog)
    try:
        out = build_prompt(ctx, rule, needs_work, rv=current_review(ctx), target="azure", azure_root=st.azure_root)
    except UserError as exc:
        raise not_found(str(exc)) from None
    return {**out, "studio_root": st.root.uri}
