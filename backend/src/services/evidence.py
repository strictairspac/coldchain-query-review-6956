from sqlalchemy import select
from fastapi import HTTPException
from ..models.batch import Batch
from ..models.evidence import Evidence
from .access import allowed_customers
from .query_engine import normalize_customers

def _accessible(db,user,record,granted=None):
    """证据访问按“实际客户范围”判定，而不是按创建人。

    - 管理员：全部可读（含旧证据与拒绝证据）。
    - 专员：证据记录的客户范围必须非空且完全落在当前授权内；跨客户读取或下载一律拒绝。
    - 旧证据/拒绝证据没有可证明的客户范围（scope 为空），归管理员。
    """
    if user.role=='admin':return True
    scope=normalize_customers(record.scope)
    if not scope:return False
    if granted is None:granted=set(allowed_customers(db,user))
    return set(scope).issubset(granted)

def _serialize(x):
    return {'id':x.id,'batch_id':x.batch_id,'result':x.result,'scope':normalize_customers(x.scope),'status_reason':x.status_reason,'created_by':x.created_by,'created_at':str(x.created_at) if x.created_at else None}

def list_evidence(db,user):
    granted=None if user.role=='admin' else set(allowed_customers(db,user))
    items=[x for x in db.scalars(select(Evidence).order_by(Evidence.id.desc())) if _accessible(db,user,x,granted)]
    return [_serialize(x) for x in items]

def get_evidence(db,batch_id,user):
    x=db.scalar(select(Evidence).where(Evidence.batch_id==batch_id))
    if not x:raise HTTPException(404,'证据尚未生成，请等待 worker 完成')
    if not _accessible(db,user,x):raise HTTPException(403,'该证据超出你的客户授权范围，无法读取或下载')
    return _serialize(x)

def batch_status(db,batch_id,user):
    """受理/执行/完成/拒绝原因；与证据同一客户范围校验。"""
    from .batch import visible
    batch=db.get(Batch,batch_id)
    if not batch:raise HTTPException(404,'批次不存在')
    if not visible(db,user,batch):
        raise HTTPException(403,'该批次超出你的客户授权范围')
    evidence=db.scalar(select(Evidence).where(Evidence.batch_id==batch_id))
    return {'id':batch.id,'status':batch.status,'status_reason':batch.status_reason,'scope':normalize_customers(batch.scope),'created_by':batch.created_by,'has_evidence':evidence is not None,'evidence_scope':normalize_customers(evidence.scope) if evidence else None}
