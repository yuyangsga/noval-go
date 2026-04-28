from fastapi import APIRouter, HTTPException
from pathlib import Path
import httpx
import json

from app.api.bookshelf import mark_cached

router = APIRouter()

BASE_URL = "https://novel.cooks.tw"
CACHE_ROOT = Path("data/cache")

def book_cache_dir(aid: str):
    return CACHE_ROOT / str(aid)

def chapters_cache_path(aid: str):
    return book_cache_dir(aid) / "chapters.json"

def content_cache_path(aid: str, cid: str):
    return book_cache_dir(aid) / f"{cid}.json"

def read_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

async def fetch_chapters(aid: str):
    async with httpx.AsyncClient() as client:
        url = f"{BASE_URL}/api/chapter/list/{aid}?lang=zh-CN"
        resp = await client.get(url, timeout=10.0)
        resp.raise_for_status()
        return resp.json()

async def fetch_content(aid: str, cid: str):
    async with httpx.AsyncClient() as client:
        url = f"{BASE_URL}/api/chapter/content/{aid}/{cid}?lang=zh-CN"
        resp = await client.get(url, timeout=10.0)
        resp.raise_for_status()
        return resp.json()

@router.get("/chapters/{aid}")
async def get_chapters(aid: str):
    """获取书籍目录"""
    try:
        data = await fetch_chapters(aid)
        write_json(chapters_cache_path(aid), data)
        return data
    except Exception:
        cached = read_json(chapters_cache_path(aid))
        if cached:
            cached["cached"] = True
            return cached
        raise HTTPException(status_code=503, detail="目录加载失败，且没有本地缓存")

@router.get("/content/{aid}/{cid}")
async def get_content(aid: str, cid: str):
    """获取章节正文"""
    cached = read_json(content_cache_path(aid, cid))
    if cached:
        cached["cached"] = True
        return cached

    try:
        data = await fetch_content(aid, cid)
        write_json(content_cache_path(aid, cid), data)
        return data
    except Exception:
        raise HTTPException(status_code=503, detail="正文加载失败，且没有本地缓存")

@router.get("/cache/status/{aid}")
async def cache_status(aid: str):
    """查看本地缓存状态"""
    chapters = read_json(chapters_cache_path(aid))
    chapter_items = (chapters or {}).get("data") or []
    cached_count = len(list(book_cache_dir(aid).glob("*.json"))) - (1 if chapters else 0)
    cached_count = max(cached_count, 0)
    return {
        "cached": bool(chapter_items and cached_count >= len(chapter_items)),
        "cached_count": cached_count,
        "total": len(chapter_items),
    }

@router.post("/cache/{aid}")
async def cache_book(aid: str):
    """缓存整本书到本地 data/cache 目录"""
    chapters = await fetch_chapters(aid)
    chapter_items = chapters.get("data") or []
    write_json(chapters_cache_path(aid), chapters)

    cached_count = 0
    failed = []
    for chapter in chapter_items:
        cid = str(chapter.get("chapterid", ""))
        if not cid:
            continue

        target = content_cache_path(aid, cid)
        if target.exists():
            cached_count += 1
            continue

        try:
            content = await fetch_content(aid, cid)
            write_json(target, content)
            cached_count += 1
        except Exception:
            failed.append({
                "chapterid": cid,
                "chaptername": chapter.get("chaptername", ""),
            })

    if cached_count:
        mark_cached(aid)

    return {
        "msg": "缓存完成" if not failed else "部分章节缓存失败",
        "cached_count": cached_count,
        "total": len(chapter_items),
        "failed": failed[:20],
    }
