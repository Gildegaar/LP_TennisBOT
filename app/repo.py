from sqlalchemy import select
from .models import User
from .db import get_session
from sqlalchemy import delete
from .models import Location
from datetime import datetime
from .models import LessonRequest, User, Location


def upsert_user(telegram_id: int, first_name: str, last_name: str | None, username: str | None) -> User:
    with get_session() as s:
        u = s.scalar(select(User).where(User.telegram_id == telegram_id))
        if u:
            # update fields (keep it simple)
            u.first_name = first_name
            u.last_name = last_name
            u.username = username
        else:
            u = User(
                telegram_id=telegram_id,
                first_name=first_name,
                last_name=last_name,
                username=username,
            )
            s.add(u)
        s.commit()
        s.refresh(u)
        return u
        
def add_location(name: str) -> Location:
    name = name.strip()
    with get_session() as s:
        loc = Location(name=name, active=True)
        s.add(loc)
        s.commit()
        s.refresh(loc)
        return loc

def list_locations(active_only: bool = True) -> list[Location]:
    with get_session() as s:
        q = select(Location)
        if active_only:
            q = q.where(Location.active == True)  # noqa: E712
        q = q.order_by(Location.name.asc())
        return list(s.scalars(q).all())

def deactivate_location(loc_id: int) -> bool:
    with get_session() as s:
        loc = s.get(Location, loc_id)
        if not loc:
            return False
        loc.active = False
        s.commit()
        return True
        
def get_user_by_telegram_id(telegram_id: int) -> User | None:
    with get_session() as s:
        return s.scalar(select(User).where(User.telegram_id == telegram_id))

def get_location(loc_id: int) -> Location | None:
    with get_session() as s:
        return s.get(Location, loc_id)

def create_lesson_request(user_id: int, start_dt: datetime, duration_min: int, location_id: int, notes: str | None) -> LessonRequest:
    with get_session() as s:
        lr = LessonRequest(
            user_id=user_id,
            start_dt=start_dt,
            duration_min=duration_min,
            location_id=location_id,
            notes=notes,
            status="PENDING",
        )
        s.add(lr)
        s.commit()
        s.refresh(lr)
        return lr

def set_request_status(req_id: int, status: str) -> bool:
    with get_session() as s:
        lr = s.get(LessonRequest, req_id)
        if not lr:
            return False
        lr.status = status
        s.commit()
        return True

def get_request(req_id: int) -> LessonRequest | None:
    with get_session() as s:
        return s.get(LessonRequest, req_id)