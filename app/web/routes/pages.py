"""GET pages — stubbed 501 until the UI agent implements them (phase0 §5)."""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/")
def index() -> None:
    raise HTTPException(status_code=501, detail="Not implemented")
