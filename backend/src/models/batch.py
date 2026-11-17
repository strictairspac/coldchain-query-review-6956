from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import String,Text,ForeignKey,DateTime,func,JSON
from datetime import datetime
from ..config.database import Base
class Batch(Base):
    __tablename__='batches'
    id:Mapped[int]=mapped_column(primary_key=True)
    name:Mapped[str]=mapped_column(String(120),unique=True)
    sample_id:Mapped[int]=mapped_column(ForeignKey('samples.id'))
    candidate_sql:Mapped[str]=mapped_column(Text)
    status:Mapped[str]=mapped_column(String(20),default='queued')
    created_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())
    user_id:Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    created_by:Mapped[str|None]=mapped_column(String(120),nullable=True)
    # 创建时快照的客户范围；执行时只允许收窄，绝不扩大到当前授权之外。
    scope:Mapped[list]=mapped_column(JSON,default=list)
    # 受理、拒绝或失败的可读原因（例如授权已撤销）。
    status_reason:Mapped[str|None]=mapped_column(Text,nullable=True)
