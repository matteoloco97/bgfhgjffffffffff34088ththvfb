# core/api_persona.py
from fastapi import APIRouter, Body, Query
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional
from .persona_store import (
    get_persona_struct, set_persona_struct,
    get_default_persona, set_default_persona,
)

router = APIRouter(prefix="/persona", tags=["persona"])

class PersonaPayload(BaseModel):
    persona_id: Optional[str] = Field(default=None)
    system: Optional[list[str] | str] = None
    behavior: Optional[Dict[str, Any]] = None
    tool_prefs: Optional[Dict[str, Any]] = None
    version: Optional[int] = 1

@router.get("/get")
async def persona_get(
    src: str = Query("global"),
    sid: str = Query("default"),
):
    if src == "global" and sid == "default":
        return await get_default_persona()
    return await get_persona_struct(src, sid)

@router.post("/set")
async def persona_set(
    payload: PersonaPayload,
    src: str = Query("global"),
    sid: str = Query("default"),
):
    data = payload.model_dump(exclude_none=True)
    if src == "global" and sid == "default":
        await set_default_persona(data)
    else:
        await set_persona_struct(src, sid, data)
    return {"status": "ok", "src": src, "sid": sid}
