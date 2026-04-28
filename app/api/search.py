from fastapi import APIRouter, Query
import httpx

router = APIRouter()

# 模拟你之前提供的书源配置中的搜索 URL 逻辑
SEARCH_URL = "https://novel.cooks.tw/api/novel/search"

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