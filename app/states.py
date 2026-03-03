from dataclasses import dataclass
from typing import Optional

@dataclass
class LessonDraft:
    date: Optional[str] = None       # YYYY-MM-DD
    time: Optional[str] = None       # HH:MM
    duration: Optional[int] = None
    location_id: Optional[int] = None
    notes: Optional[str] = None

DRAFTS: dict[int, LessonDraft] = {}   # key: telegram_id
STEPS: dict[int, str] = {}           # key: telegram_id -> "DATE|TIME|DUR|LOC|NOTES|REVIEW"
ADMIN_PENDING_PRICE: dict[int, int] = {}  # admin_telegram_id -> req_id