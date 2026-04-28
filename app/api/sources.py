from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def get_sources():
    return {"msg": "书源管理模块开发中"}