from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import ForeignKey,JSON,DateTime,String,Text,func
from datetime import datetime
from ..config.database import Base
class Evidence(Base):
    __tablename__='evidence'
    id:Mapped[int]=mapped_column(primary_key=True)
    batch_id:Mapped[int]=mapped_column(ForeignKey('batches.id'),unique=True)
    result:Mapped[dict]=mapped_column(JSON)
    created_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())
    user_id:Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    created_by:Mapped[str|None]=mapped_column(String(120),nullable=True)
    # 证据实际执行时使用的客户范围（两侧一致）；用于访问控制与展示。
    scope:Mapped[list]=mapped_column(JSON,default=list)
    # 拒绝原因：授权范围为空或被撤销时，记录为拒绝证据。
    status_reason:Mapped[str|None]=mapped_column(Text,nullable=True)
