"""Unauthenticated, read-only endpoints for the sign-up and app shell (``/v1/public/*``).

They expose only values the control panel marks as public (brand) and the list of countries open for sign-up.
Nothing tenant-specific is ever served here.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from control_api.deps import StateDep
from control_api.regions import available_countries
from control_api.schemas import PublicBrandOut, PublicCountryOut

router = APIRouter(prefix="/v1/public", tags=["public"])

_CACHE = "public, max-age=30"


@router.get("/brand", response_model=PublicBrandOut, summary="Product name, support contact and legal links")
async def brand(state: StateDep, response: Response) -> PublicBrandOut:
    v = await state.config.public_values()
    response.headers["Cache-Control"] = _CACHE
    return PublicBrandOut(
        product_name=v["body.product_name"],
        support_email=v["body.support_email"],
        terms_url=v["body.terms_url"],
        privacy_url=v["body.privacy_url"],
    )


@router.get("/countries", response_model=list[PublicCountryOut], summary="Countries open for sign-up")
async def countries(state: StateDep, response: Response) -> list[PublicCountryOut]:
    async with state.db.unscoped_tx() as s:
        rows = await available_countries(s)
    response.headers["Cache-Control"] = _CACHE
    return [PublicCountryOut(code=c, name=n, region=r) for c, n, r in rows]
