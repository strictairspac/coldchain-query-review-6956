import os,time,json,traceback
from pathlib import Path
from sqlalchemy import select
from .config.database import Session
from .models.batch import Batch
from .models.sample import Sample
from .models.evidence import Evidence
from .services.batch import queue
from .services.query_engine import compare,normalize_customers
ARTIFACTS=Path(os.getenv('ARTIFACTS_DIR','/artifacts'))
heartbeat=ARTIFACTS/'worker.heartbeat'

def _write_artifact(batch_id,result):
    """证据已入库；文件导出是附加产物，写失败不应让 worker 崩溃或丢证据。"""
    try:
        ARTIFACTS.mkdir(parents=True,exist_ok=True)
        (ARTIFACTS/f'review-{batch_id}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    except Exception:traceback.print_exc()

def _granted_for(db,batch):
    """执行时重新读取创建者当前授权；管理员始终全覆盖。"""
    from .models.user import User
    from .services.access import allowed_customers
    user=db.get(User,batch.user_id) if batch.user_id else None
    if not user and batch.created_by:
        # 旧批次可能只有邮箱快照，按邮箱找回账号后再校验授权。
        user=db.scalar(select(User).where(User.email==batch.created_by))
    if not user:return []
    return normalize_customers(allowed_customers(db,user))

def run_one(batch_id):
    with Session() as db:
        batch=db.get(Batch,batch_id)
        if not batch or db.scalar(select(Evidence).where(Evidence.batch_id==batch_id)):return
        sample=db.get(Sample,batch.sample_id)
        if not sample:
            reason='执行拒绝：基准样本已不存在'
            batch.status='failed';batch.status_reason=reason
            db.add(Evidence(batch_id=batch_id,result={'error':reason,'rejected':True},scope=[],status_reason=reason))
            db.commit();return
        snapshot=normalize_customers(batch.scope)
        current=_granted_for(db,batch)
        # 排队期间授权被撤销或收窄：按当前授权执行，已撤权客户绝不读取。
        effective=normalize_customers(set(snapshot)&set(current))
        revoked=[c for c in snapshot if c not in effective]
        batch.status='running';db.commit()
        if not effective:
            reason='执行拒绝：客户授权已撤销，客户范围 '+('、'.join(snapshot) or '无')
            result={'error':reason,'rejected':True,'scope':[]}
            batch.status='failed';batch.status_reason=reason
            db.add(Evidence(batch_id=batch_id,result=result,scope=[],user_id=None,created_by=None,status_reason=reason))
            db.commit()
            _write_artifact(batch_id,result)
            return
        try:
            result=compare(sample.original_sql,batch.candidate_sql,effective)
            if revoked:result['scope_note']=str(result.get('scope_note',''))+'；已剔除撤权客户：'+'、'.join(revoked)
            batch.status='passed' if result['equivalent'] else 'different'
            batch.status_reason=('执行完成：客户范围 '+'、'.join(effective))+('；已剔除撤权客户 '+'、'.join(revoked) if revoked else '')
        except Exception as exc:
            result={'error':str(exc)[:500],'scope':effective};batch.status='failed';batch.status_reason='执行失败：'+str(exc)[:200]
        db.add(Evidence(batch_id=batch_id,result=result,scope=effective,user_id=batch.user_id,created_by=batch.created_by,status_reason=batch.status_reason))
        db.commit()
        _write_artifact(batch_id,result)

def main():
    while True:
        try:
            heartbeat.write_text(str(time.time()))
            item=queue.blpop('query-review:jobs',timeout=2)
            if item:run_one(int(item[1]))
            else:
                with Session() as db:pending=list(db.scalars(select(Batch.id).where(Batch.status.in_(['queued','running']))))
                for ident in pending:run_one(ident)
        except Exception:traceback.print_exc();time.sleep(2)

if __name__=='__main__':main()
