from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime, timezone
import asyncio
import httpx
import json
import os

router = APIRouter()
DB_PATH = "data/data.json"
BASE_URL = "https://novel.cooks.tw"
UPDATE_INTERVAL_SECONDS = 30 * 60

def empty_db():
    return {"bookshelf": [], "sources": []}

# 定义数据模型
class BookItem(BaseModel):
    aid: str
    name: str
    author: str = ""
    cover: str = ""
    tags: list[str] = Field(default_factory=list)
    source_id: str = ""

class ProgressItem(BaseModel):
    chapterid: str
    chaptername: str = ""
    index: int = 0

class TagsItem(BaseModel):
    tags: list[str] = Field(default_factory=list)

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def normalize_book(book: dict[str, Any]):
    book["aid"] = str(book.get("aid", ""))
    book.setdefault("name", "")
    book.setdefault("author", "")
    book.setdefault("cover", "")
    book.setdefault("tags", [])
    book.setdefault("source_id", "")
    book.setdefault("progress", None)
    book.setdefault("has_update", False)
    book.setdefault("latest_chapter_id", "")
    book.setdefault("latest_chapter_name", "")
    book.setdefault("latest_chapter_count", 0)
    book.setdefault("latest_checked_at", "")
    book.setdefault("cached", False)
    book.setdefault("cached_at", "")
    return book

def find_book(db, aid: str):
    aid = str(aid)
    for book in db["bookshelf"]:
        if str(book.get("aid")) == aid:
            return book
    return None

def load_db():
    if not os.path.exists(DB_PATH):
        return empty_db()
    with open(DB_PATH, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return empty_db()

    if not isinstance(data, dict):
        return empty_db()

    data.setdefault("bookshelf", [])
    data.setdefault("sources", [])
    data["bookshelf"] = [
        normalize_book(item)
        for item in data["bookshelf"]
        if isinstance(item, dict) and item.get("aid")
    ]
    return data

def save_db(data):
    data.setdefault("bookshelf", [])
    data.setdefault("sources", [])
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def mark_cached(aid: str):
    db = load_db()
    book = find_book(db, aid)
    if book:
        book["cached"] = True
        book["cached_at"] = now_iso()
        save_db(db)

def unmark_cached(aid: str):
    db = load_db()
    book = find_book(db, aid)
    if book:
        book["cached"] = False
        book["cached_at"] = ""
        save_db(db)

async def fetch_latest_chapter(aid: str, source_id: str = ""):
    url = f"{BASE_URL}/api/chapter/list/{aid}?lang=zh-CN"
    if source_id:
        from app.api.sources import _find_source, _get_sources
        db = load_db()
        source = _find_source(_get_sources(db), source_id)
        if source and source.get("base_url") and source.get("chapter_list_path"):
            base = source["base_url"].rstrip("/")
            tpl = source["chapter_list_path"]
            url = base + tpl.replace("{aid}", aid)

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10.0)
        resp.raise_for_status()
        chapters = resp.json().get("data") or []

    if not chapters:
        return None

    latest = chapters[-1]
    return {
        "chapterid": str(latest.get("chapterid", "")),
        "chaptername": latest.get("chaptername", ""),
        "count": len(chapters),
    }

async def check_bookshelf_updates():
    db = load_db()
    changed = False

    for book in db["bookshelf"]:
        try:
            latest = await fetch_latest_chapter(book["aid"], book.get("source_id", ""))
        except Exception:
            book["latest_checked_at"] = now_iso()
            changed = True
            continue

        if not latest:
            continue

        old_latest = str(book.get("latest_chapter_id") or "")
        if old_latest and old_latest != latest["chapterid"]:
            progress = book.get("progress") or {}
            book["has_update"] = str(progress.get("chapterid", "")) != latest["chapterid"]

        book["latest_chapter_id"] = latest["chapterid"]
        book["latest_chapter_name"] = latest["chaptername"]
        book["latest_chapter_count"] = latest["count"]
        book["latest_checked_at"] = now_iso()
        changed = True

    if changed:
        save_db(db)
    return db["bookshelf"]

async def update_watcher():
    while True:
        try:
            await check_bookshelf_updates()
        except Exception:
            pass
        await asyncio.sleep(UPDATE_INTERVAL_SECONDS)

@router.get("/")
@router.get("")
async def get_shelf():
    """获取书架所有书籍"""
    return load_db()["bookshelf"]

@router.post("/add")
async def add_to_shelf(book: BookItem):
    """添加书籍到书架"""
    db = load_db()
    # 检查是否已存在
    existing = find_book(db, book.aid)
    if existing:
        existing.update({
            "name": book.name or existing.get("name", ""),
            "author": book.author or existing.get("author", ""),
            "cover": book.cover or existing.get("cover", ""),
        })
        if book.source_id:
            existing["source_id"] = book.source_id
        save_db(db)
        return {"msg": "书籍已在书架中"}
    
    book_data = book.model_dump() if hasattr(book, "model_dump") else book.dict()
    normalize_book(book_data)
    db["bookshelf"].append(book_data)
    save_db(db)
    return {"msg": "添加成功"}

@router.put("/progress/{aid}")
async def update_progress(aid: str, progress: ProgressItem):
    """保存阅读进度"""
    db = load_db()
    book = find_book(db, aid)
    if not book:
        return {"msg": "书籍不在书架中"}

    book["progress"] = progress.model_dump() if hasattr(progress, "model_dump") else progress.dict()
    if str(book.get("latest_chapter_id", "")) == progress.chapterid:
        book["has_update"] = False
    save_db(db)
    return {"msg": "进度已保存", "progress": book["progress"]}

@router.put("/tags/{aid}")
async def update_tags(aid: str, payload: TagsItem):
    """更新书籍标签"""
    db = load_db()
    book = find_book(db, aid)
    if not book:
        return {"msg": "书籍不在书架中"}

    tags = []
    for tag in payload.tags:
        text = str(tag).strip()
        if text and text not in tags:
            tags.append(text[:12])

    book["tags"] = tags
    save_db(db)
    return {"msg": "标签已更新", "tags": tags}

@router.post("/mark-read/{aid}")
async def mark_read(aid: str):
    """清除更新提醒红点"""
    db = load_db()
    book = find_book(db, aid)
    if book:
        book["has_update"] = False
        save_db(db)
    return {"msg": "已标记为已读"}

@router.post("/check-updates")
async def check_updates():
    """检查书架书籍是否有新章节"""
    return await check_bookshelf_updates()

@router.delete("/remove/{aid}")
async def remove_from_shelf(aid: str):
    """从书架移除并清除缓存"""
    from app.api.reader import _clear_book_cache
    _clear_book_cache(aid)
    db = load_db()
    db["bookshelf"] = [item for item in db["bookshelf"] if str(item.get("aid")) != aid]
    save_db(db)
    return {"msg": "已从书架移除"}
