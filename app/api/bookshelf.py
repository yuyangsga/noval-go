from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import json
import os

router = APIRouter()
DB_PATH = "data/data.json"

# 定义数据模型
class BookItem(BaseModel):
    aid: str
    name: str
    author: str
    cover: str

def load_db():
    if not os.path.exists(DB_PATH):
        return {"bookshelf": [], "sources": []}
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(data):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

@router.get("/")
async def get_shelf():
    """获取书架所有书籍"""
    return load_db()["bookshelf"]

@router.post("/add")
async def add_to_shelf(book: BookItem):
    """添加书籍到书架"""
    db = load_db()
    # 检查是否已存在
    if any(item['aid'] == book.aid for item in db["bookshelf"]):
        return {"msg": "书籍已在书架中"}
    
    db["bookshelf"].append(book.dict())
    save_db(db)
    return {"msg": "添加成功"}

@router.delete("/remove/{aid}")
async def remove_from_shelf(aid: str):
    """从书架移除"""
    db = load_db()
    db["bookshelf"] = [item for item in db["bookshelf"] if item['aid'] != aid]
    save_db(db)
    return {"msg": "已从书架移除"}