from sqlalchemy import select
from fastapi import HTTPException
from redis import Redis
from ..config.settings import REDIS_URL
from ..models.batch import Batch
from ..models.sample import Sample
from .access import allowed_customers,format_scope
from .query_engine import validate_sql,normalize_customers
queue=Redis.from_url(REDIS_URL)
def serialize(x):return {'id':x.id,'name':x.name,'sample_id':x.sample_id,'candidate_sql':x.candidate_sql,'status':x.status,'status_reason':x.status_reason,'scope':normalize_customers(x.scope),'created_by':x.created_by,'created_at':str(x.created_at)}
def visible(db,user,batch):
    """批次元数据（状态与原因）可见：管理员、创建者本人，或客户范围仍在当前授权内的同组专员。

    可见的只是状态与原因，不含账单数据；证据本身另按实际范围校验。
    """
    if user.role=='admin':return True
    if batch.user_id==user.id:return True
    scope=normalize_customers(batch.scope)
    return bool(scope) and set(scope).issubset(set(allowed_customers(db,user)))
def list_batches(db,user):
    statement=select(Batch).order_by(Batch.id.desc())
    if user is None or user.role=='admin':
        return [serialize(x) for x in db.scalars(statement)]
    granted=set(allowed_customers(db,user))
    items=[]
    for x in db.scalars(statement):
        if x.user_id==user.id or (normalize_customers(x.scope) and set(normalize_customers(x.scope)).issubset(granted)):
            items.append(serialize(x))
    return items
def create_batch(db,data,user):
    validate_sql(data.candidate_sql)
    if not db.get(Sample,data.sample_id):raise HTTPException(404,'样本不存在')
    if db.scalar(select(Batch).where(Batch.name==data.name)):raise HTTPException(409,'批次名称已存在')
    if len(list(db.scalars(select(Batch).where(Batch.status.in_(['queued','running'])))))>=20:raise HTTPException(429,'待执行任务达到20个，请稍后重试')
    scope=normalize_customers(allowed_customers(db,user))
    if not scope:raise HTTPException(403,'当前账号没有可查客户，请联系管理员授权后再提交')
    obj=Batch(**data.model_dump(),user_id=user.id,created_by=user.email,scope=scope,status_reason='待执行：客户范围 '+format_scope(scope))
    db.add(obj);db.commit();queue.rpush('query-review:jobs',obj.id);return serialize(obj)
