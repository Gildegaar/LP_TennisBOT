from sqlalchemy import select
from .models import User
from .db import get_session

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