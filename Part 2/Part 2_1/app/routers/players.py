from fastapi import APIRouter, HTTPException, Query, Path, Depends
from typing import List, Dict, Any
import aiosqlite

from ..db.sqlite import get_db
from ..crud.player import fetch_by_name, fetch_by_club

router = APIRouter(prefix="/players", tags=["players"])


@router.get("", summary="Tìm cầu thủ theo tên")
async def by_name(
    name: str = Query(..., description="Tên cầu thủ, ví dụ: 'haaland'"),
    db: aiosqlite.Connection = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Tìm kiếm cầu thủ theo tên (trả về tất cả kết quả phù hợp)"""
    rows = await fetch_by_name(db, name=name)
    if not rows:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy cầu thủ phù hợp với tên '{name}'.")
    return rows


@router.get("/by-club/{club}", summary="Lấy toàn bộ cầu thủ thuộc CLB")
async def players_of_club(
    club: str = Path(..., description="Tên câu lạc bộ, ví dụ: 'Arsenal'"),
    exact: bool = Query(True, description="True = khớp chính xác; False = LIKE search"),
    db: aiosqlite.Connection = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Lấy toàn bộ chỉ số của tất cả cầu thủ thuộc CLB"""
    rows = await fetch_by_club(db, club=club, exact=exact)
    if not rows:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy cầu thủ thuộc CLB '{club}'.")
    return rows
