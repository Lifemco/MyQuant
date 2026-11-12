from fastapi import APIRouter

from app.market import service

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/overview")
def overview():
    return service.overview()


@router.post("/refresh")
def refresh():
    return service.startCollection()


@router.post("/breadth")
def breadth():
    return service.startCollection("breadth")
