from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..config.database import Base


class CustomerAccess(Base):
    """客户的查询授权：管理员为专员逐客户配置，未配置即无数据。"""

    __tablename__ = 'customer_access'
    __table_args__ = (
        UniqueConstraint('user_id', 'customer', name='uq_customer_access_user_customer'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    customer: Mapped[str] = mapped_column(String(120), index=True)
    granted_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
