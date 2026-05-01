from fastapi import APIRouter, Query
import asyncio
import httpx

from app.api.bookshelf import load_db

router = APIRouter()


def _extract_field(item: dict, field_map: dict, key: str) -> str:
    src_key = field_map.get(key, key)
    return str(item.get(src_key, "") or "")


async def _search_source(source: dict, keyword: str, page: int) -> list[dict]:
    if not source.get("enabled", True):
        return []

    base_url = (source.get("base_url") or "").rstrip("/")
    search_path = source.get("search_path") or ""
    if not base_url or not search_path:
        return []

    url = base_url + search_path.replace("{query}", keyword).replace("{page}", str(page))
    field_map = source.get("field_map") or {}
    source_id = source.get("id", "")
    source_name = source.get("name", "未知")
    source_color = source.get("color", "#888")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    items_raw = data.get("data", {}).get("items", []) if isinstance(data.get("data"), dict) else []

    results = []
    for item in items_raw:
        if not isinstance(item, dict):
            continue
        results.append({
            "articleid": _extract_field(item, field_map, "aid"),
            "articlename": _extract_field(item, field_map, "name"),
            "author": _extract_field(item, field_map, "author"),
            "cover": _extract_field(item, field_map, "cover"),
            "intro": _extract_field(item, field_map, "intro"),
            "source_id": source_id,
            "source_name": source_name,
            "source_color": source_color,
        })
    return results


async def _search_all(keyword: str, page: int) -> list[dict]:
    db = load_db()
    sources = db.get("sources", [])
    enabled = [s for s in sources if s.get("enabled", True)]
    if not enabled:
        return []

    tasks = [_search_source(s, keyword, page) for s in enabled]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    merged = []
    seen = set()
    for r in results:
        if isinstance(r, list):
            for item in r:
                key = (
                    str(item.get("articleid", "")),
                    item.get("articlename", ""),
                    item.get("author", ""),
                )
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)
    return merged


async def _search_source_by_id(source_id: str, keyword: str, page: int) -> list[dict]:
    db = load_db()
    sources = db.get("sources", [])
    source = None
    for s in sources:
        if s.get("id") == source_id:
            source = s
            break
    if not source:
        return []
    return await _search_source(source, keyword, page)


@router.get("/suggest")
async def suggest(q: str = Query("", description="联想关键词")):
    keyword = q.strip()
    suggestions = []

    for book in load_db()["bookshelf"]:
        name = book.get("name", "")
        if name and (not keyword or keyword in name):
            suggestions.append({
                "name": name,
                "author": book.get("author", ""),
                "aid": book.get("aid", ""),
                "source_id": book.get("source_id", ""),
                "source_name": "书架",
                "source_color": "#0d9488",
            })

    if keyword:
        remote = await _search_all(keyword, 1)
        seen = {s["name"] for s in suggestions}
        for item in remote:
            if item["articlename"] and item["articlename"] not in seen:
                seen.add(item["articlename"])
                suggestions.append({
                    "name": item["articlename"],
                    "author": item["author"],
                    "aid": item["articleid"],
                    "source_id": item["source_id"],
                    "source_name": item["source_name"],
                    "source_color": item["source_color"],
                })

    return {"suggestions": suggestions[:12]}


@router.get("/")
async def search(
    q: str = Query(..., description="搜索关键词"),
    page: int = 1,
    source: str = Query("", description="指定书源ID，留空则搜索全部"),
):
    keyword = q.strip()
    if not keyword:
        return {"data": {"items": []}}

    if source:
        items = await _search_source_by_id(source, keyword, page)
    else:
        items = await _search_all(keyword, page)

    return {"data": {"items": items}}
