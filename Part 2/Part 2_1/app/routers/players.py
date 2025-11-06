from fastapi import APIRouter, HTTPException, Query, Path
from typing import List, Dict, Any
from ..db.sqlite import get_conn, ensure_source_table, create_indexes
from ..crud.player import fetch_by_name, fetch_by_club
from ..core.config import DEFAULT_LIMIT, MAX_LIMIT

router = APIRouter(prefix="/players", tags=["players"])

@router.get("", summary="Tìm cầu thủ theo tên (LIKE)")
def by_name(
    name: str = Query(..., description="Tên cầu thủ, ví dụ: 'haaland'"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        ensure_source_table(conn)
        create_indexes(conn)
        rows = fetch_by_name(conn, name=name, limit=limit, offset=offset)
        if not rows:
            raise HTTPException(status_code=404, detail="Không tìm thấy cầu thủ phù hợp.")
        return rows

# ✅ endpoint club-centric: trả về TOÀN BỘ chỉ số của TẤT CẢ cầu thủ thuộc CLB
@router.get("/by-club/{club}", summary="Toàn bộ cầu thủ & chỉ số thuộc CLB")
def players_of_club(
    club: str = Path(..., description="Tên câu lạc bộ trùng cột 'squad', ví dụ: 'Arsenal'"),
    exact: bool = Query(True, description="True = khớp chính xác; False = LIKE gần đúng"),
) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        ensure_source_table(conn)
        create_indexes(conn)
        rows = fetch_by_club(conn, club=club, exact=exact)
        if not rows:
            raise HTTPException(status_code=404, detail="Không tìm thấy cầu thủ thuộc CLB này.")
        return rows
