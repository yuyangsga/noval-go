from fastapi import APIRouter, Query
import httpx

from app.api.bookshelf import load_db

router = APIRouter()

# 模拟你之前提供的书源配置中的搜索 URL 逻辑
SEARCH_URL = "https://novel.cooks.tw/api/novel/search"

@router.get("/suggest")
async def suggest(q: str = Query("", description="联想关键词")):
    """搜索联想，优先返回书架命中，再补充远端搜索结果"""
    keyword = q.strip()
    suggestions = []

    for book in load_db()["bookshelf"]:
        name = book.get("name", "")
        if name and (not keyword or keyword in name):
            suggestions.append({
                "name": name,
                "author": book.get("author", ""),
                "aid": book.get("aid", ""),
                "source": "shelf",
            })

    if keyword:
        params = {
            "q": keyword,
            "page": 1,
            "limit": 8,
            "lang": "zh-CN"
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(SEARCH_URL, params=params, timeout=6.0)
                response.raise_for_status()
                items = response.json().get("data", {}).get("items", [])
                for item in items:
                    name = item.get("articlename", "")
                    if name and all(existing["name"] != name for existing in suggestions):
                        suggestions.append({
                            "name": name,
                            "author": item.get("author", ""),
                            "aid": str(item.get("articleid", "")),
                            "source": "remote",
                        })
            except Exception:
                pass

    return {"suggestions": suggestions[:8]}

@router.get("/")
async def search(q: str = Query(..., description="搜索关键词"), page: int = 1):
    """
    搜索书籍接口
    """
    params = {
        "q": q,
        "page": page,
        "limit": 20,
        "lang": "zh-CN"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            # 发起异步请求
            response = await client.get(SEARCH_URL, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            
            # 这里可以直接返回原始数据，或者根据你的模型进行清洗
            # 对应书源规则中的 $.data.items
            return data
            
        except Exception as e:
            return {"error": str(e), "msg": "搜索接口调用失败"}
