from sqlalchemy import select
from .models import User
from .db import get_session
from sqlalchemy import update, delete
from .models import Location
from datetime import datetime
from .models import LessonRequest, User, Location
from sqlalchemy import select, func
from datetime import datetime
from .models import Payment, LessonRequest, User
from datetime import datetime, timedelta
import zoneinfo
from sqlalchemy import desc
from sqlalchemy import func
from .models import LessonRequest


from .config import TZ
from .models import LessonRequest, User, Location
rome = zoneinfo.ZoneInfo(TZ)

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
        

def count_lesson_requests() -> int:
    with get_session() as s:
        return int(s.scalar(select(func.count()).select_from(LessonRequest)) or 0)
        
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
        q = q.order_by(Location.id.asc())
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
        
def get_user_by_username(username: str) -> User | None:
    username = username.lstrip("@")
    with get_session() as s:
        return s.scalar(select(User).where(User.username == username))

def get_user_by_telegram_id(telegram_id: int) -> User | None:
    with get_session() as s:
        return s.scalar(select(User).where(User.telegram_id == telegram_id))

def get_request_with_user(req_id: int) -> tuple[LessonRequest, User] | None:
    with get_session() as s:
        stmt = (
            select(LessonRequest, User)
            .join(User, LessonRequest.user_id == User.id)
            .where(LessonRequest.id == req_id)
        )
        row = s.execute(stmt).first()
        if not row:
            return None
        return row[0], row[1]

def set_request_status(req_id: int, status: str) -> bool:
    with get_session() as s:
        lr = s.get(LessonRequest, req_id)
        if not lr:
            return False
        lr.status = status
        s.commit()
        return True

def set_request_price_and_confirm(req_id: int, price_cents: int) -> bool:
    with get_session() as s:
        lr = s.get(LessonRequest, req_id)
        if not lr:
            return False
        lr.price_cents = price_cents
        lr.currency = "EUR"
        lr.status = "CONFIRMED"
        s.commit()
        return True

def create_payment(user_id: int, amount_cents: int, note: str | None = None, method: str | None = None) -> Payment:
    with get_session() as s:
        p = Payment(user_id=user_id, amount_cents=amount_cents, currency="EUR", note=note, method=method)
        s.add(p)
        s.commit()
        s.refresh(p)
        return p

def student_totals(user_id: int) -> tuple[int, int, int]:
    """
    returns: (lessons_total_cents, payments_total_cents, balance_cents)
    balance > 0 => ti devono soldi
    """
    with get_session() as s:
        lessons_total = s.scalar(
            select(func.coalesce(func.sum(LessonRequest.price_cents), 0))
            .where(LessonRequest.user_id == user_id)
            .where(LessonRequest.status == "CONFIRMED")
        ) or 0

        payments_total = s.scalar(
            select(func.coalesce(func.sum(Payment.amount_cents), 0))
            .where(Payment.user_id == user_id)
        ) or 0

        balance = int(lessons_total) - int(payments_total)
        return int(lessons_total), int(payments_total), balance

def list_debtors() -> list[tuple[User, int]]:
    """
    returns list of (User, balance_cents) where balance > 0
    """
    with get_session() as s:
        # aggregate lessons
        lessons = (
            select(LessonRequest.user_id, func.coalesce(func.sum(LessonRequest.price_cents), 0).label("lt"))
            .where(LessonRequest.status == "CONFIRMED")
            .group_by(LessonRequest.user_id)
            .subquery()
        )
        # aggregate payments
        pays = (
            select(Payment.user_id, func.coalesce(func.sum(Payment.amount_cents), 0).label("pt"))
            .group_by(Payment.user_id)
            .subquery()
        )

        stmt = (
            select(User, (lessons.c.lt - func.coalesce(pays.c.pt, 0)).label("bal"))
            .join(lessons, lessons.c.user_id == User.id)
            .outerjoin(pays, pays.c.user_id == User.id)
            .where((lessons.c.lt - func.coalesce(pays.c.pt, 0)) > 0)
            .order_by((lessons.c.lt - func.coalesce(pays.c.pt, 0)).desc())
        )
        rows = s.execute(stmt).all()
        return [(r[0], int(r[1])) for r in rows]

def payments_sum_between(dt_from: datetime, dt_to: datetime) -> int:
    with get_session() as s:
        total = s.scalar(
            select(func.coalesce(func.sum(Payment.amount_cents), 0))
            .where(Payment.paid_at >= dt_from)
            .where(Payment.paid_at < dt_to)
        ) or 0
        return int(total)
        
def get_location_name(location_id: int) -> str:
    with get_session() as s:
        loc = s.get(Location, location_id)
        return loc.name if loc else f"Location {location_id}"

def list_students() -> list[User]:
    with get_session() as s:
        stmt = select(User).order_by(User.first_name.asc())
        return list(s.scalars(stmt).all())
        
def list_user_requests(telegram_id: int, limit: int = 10) -> list[LessonRequest]:
    u = get_user_by_telegram_id(telegram_id)
    if not u:
        return []
    with get_session() as s:
        stmt = (
            select(LessonRequest)
            .where(LessonRequest.user_id == u.id)
            .order_by(desc(LessonRequest.created_at))
            .limit(limit)
        )
        return list(s.scalars(stmt).all())

def list_pending_requests(limit: int = 20) -> list[tuple[LessonRequest, User]]:
    with get_session() as s:
        stmt = (
            select(LessonRequest, User)
            .join(User, LessonRequest.user_id == User.id)
            .where(LessonRequest.status.in_(["PENDING", "AWAITING_PRICE"]))
            .order_by(LessonRequest.created_at.asc())
            .limit(limit)
        )
        rows = s.execute(stmt).all()
        return [(r[0], r[1]) for r in rows]

def list_confirmed_on_day(day: datetime) -> list[tuple[LessonRequest, User]]:
    # day: any dt within the day, tz-aware
    start = day.astimezone(rome).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    with get_session() as s:
        stmt = (
            select(LessonRequest, User)
            .join(User, LessonRequest.user_id == User.id)
            .where(LessonRequest.status == "CONFIRMED")
            .where(LessonRequest.start_dt >= start)
            .where(LessonRequest.start_dt < end)
            .order_by(LessonRequest.start_dt.asc())
        )
        rows = s.execute(stmt).all()
        return [(r[0], r[1]) for r in rows]
        
from sqlalchemy import update, delete

def activate_location(loc_id: int) -> bool:
    with get_session() as s:
        loc = s.get(Location, loc_id)
        if not loc:
            return False
        loc.active = True
        s.commit()
        return True

def purge_location(loc_id: int) -> bool:
    with get_session() as s:
        loc = s.get(Location, loc_id)
        if not loc:
            return False
        s.delete(loc)
        s.commit()
        return True

def deactivate_all_locations() -> int:
    with get_session() as s:
        res = s.execute(update(Location).values(active=False))
        s.commit()
        return res.rowcount or 0