"""htmx search endpoints — stubbed 501 until the UI agent implements them (phase0 §5)."""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/games/{game}/search")
def start_search(game: str) -> None:
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/search/{search_id}/more")
def load_more(search_id: str) -> None:
    raise HTTPException(status_code=501, detail="Not implemented")
