from fastapi import APIRouter, HTTPException
import httpx

router = APIRouter()

BASE_URL = "https://novel.cooks.tw"

@router.get("/chapters/{aid}")
async def get_chapters(aid: str):
    """获取书籍目录"""
    async with httpx.AsyncClient() as client:
        url = f"{BASE_URL}/api/chapter/list/{aid}?lang=zh-CN"
        resp = await client.get(url, timeout=10.0)
        return resp.json()

@router.get("/content/{aid}/{cid}")
async def get_content(aid: str, cid: str):
    """获取章节正文"""
    async with httpx.AsyncClient() as client:
        url = f"{BASE_URL}/api/chapter/content/{aid}/{cid}?lang=zh-CN"
        resp = await client.get(url, timeout=10.0)
        return resp.json()