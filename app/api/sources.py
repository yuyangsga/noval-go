from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import uuid

from app.api.bookshelf import load_db, save_db

router = APIRouter()


class SourceItem(BaseModel):
    name: str
    base_url: str
    search_path: str = "/api/novel/search?q={query}&page={page}&limit=20&lang=zh-CN"
    chapter_list_path: str = "/api/chapter/list/{aid}?lang=zh-CN"
    chapter_content_path: str = "/api/chapter/content/{aid}/{cid}?lang=zh-CN"
    enabled: bool = True
    color: str = "#4F46E5"
    field_map: dict = Field(default_factory=lambda: {
        "name": "articlename",
        "author": "author",
        "aid": "articleid",
        "cover": "cover",
        "intro": "intro",
    })


class SourceUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    search_path: str | None = None
    chapter_list_path: str | None = None
    chapter_content_path: str | None = None
    enabled: bool | None = None
    color: str | None = None
    field_map: dict | None = None


def _get_sources(db: dict) -> list[dict]:
    return db.get("sources", [])


def _find_source(sources: list[dict], source_id: str) -> dict | None:
    for s in sources:
        if s.get("id") == source_id:
            return s
    return None


@router.get("/")
async def get_sources():
    db = load_db()
    return _get_sources(db)


@router.post("/")
async def add_source(item: SourceItem):
    db = load_db()
    sources = _get_sources(db)

    source = item.model_dump()
    source["id"] = uuid.uuid4().hex[:12]
    sources.append(source)
    db["sources"] = sources
    save_db(db)
    return source


@router.put("/{source_id}")
async def update_source(source_id: str, item: SourceUpdate):
    db = load_db()
    sources = _get_sources(db)
    source = _find_source(sources, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="书源不存在")

    updates = item.model_dump(exclude_none=True)
    source.update(updates)
    save_db(db)
    return source


@router.delete("/{source_id}")
async def delete_source(source_id: str):
    db = load_db()
    sources = _get_sources(db)
    before = len(sources)
    db["sources"] = [s for s in sources if s.get("id") != source_id]
    if len(db["sources"]) == before:
        raise HTTPException(status_code=404, detail="书源不存在")
    save_db(db)
    return {"msg": "已删除"}


@router.post("/{source_id}/toggle")
async def toggle_source(source_id: str):
    db = load_db()
    sources = _get_sources(db)
    source = _find_source(sources, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="书源不存在")
    source["enabled"] = not source.get("enabled", True)
    save_db(db)
    return source
