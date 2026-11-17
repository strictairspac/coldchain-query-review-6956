from sqlalchemy import select,text
from src.config.database import Base,engine,Session
from src.config.migrations import ensure_schema
from src.models.user import User
from src.models.sample import Sample
from src.models.batch import Batch
from src.models.evidence import Evidence
from src.models.audit import Audit
from src.models.access import CustomerAccess
from src.utils.password import hash_password
ORIGINAL="SELECT DISTINCT i.customer, (SELECT SUM(j.amount) FROM invoices j WHERE j.customer=i.customer AND j.temperature<=8) AS total FROM invoices i WHERE (SELECT SUM(k.amount) FROM invoices k WHERE k.customer=i.customer AND k.temperature<=8)>100 ORDER BY customer"
CUSTOMERS=('澄港海产','南港鲜食','北湾冷运')
def seed():
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        ensure_schema(conn)
        conn.execute(text("CREATE TABLE IF NOT EXISTS invoices (invoice_id INTEGER PRIMARY KEY, customer TEXT NOT NULL, route TEXT NOT NULL, amount NUMERIC(12,2) NOT NULL, temperature NUMERIC(4,1) NOT NULL, status TEXT NOT NULL)"))
        conn.execute(text("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='query_reader') THEN CREATE ROLE query_reader NOLOGIN; END IF; END $$"))
        conn.execute(text('GRANT SELECT ON invoices TO query_reader'))
        # 行级安全：执行账号只能看到事务内声明的客户范围；未声明即无数据。
        conn.execute(text('ALTER TABLE invoices ENABLE ROW LEVEL SECURITY'))
        conn.execute(text('DROP POLICY IF EXISTS invoices_customer_scope ON invoices'))
        conn.execute(text("""CREATE POLICY invoices_customer_scope ON invoices FOR SELECT TO query_reader
            USING (customer IN (SELECT jsonb_array_elements_text(COALESCE(current_setting('app.allowed_customers', true), '[]')::jsonb)))"""))
        conn.execute(text("INSERT INTO invoices SELECT i, (ARRAY['澄港海产','南港鲜食','北湾冷运'])[1+(i%3)], (ARRAY['东线','西线'])[1+(i%2)], 35+(i%17)*7, 2+(i%9), CASE WHEN i%7=0 THEN 'pending' ELSE 'settled' END FROM generate_series(1,600) i ON CONFLICT DO NOTHING"))
    with Session() as db:
        for role in ('admin','operator','viewer'):
            email=role+'@chenggang.test'
            if not db.scalar(select(User).where(User.email==email)):db.add(User(email=email,role=role,password_hash=hash_password('ColdChain!17')))
        samples=[('低温结算汇总','09:00 澄港海产、南港鲜食、北湾冷运的温控合格运费，600 行固定账单。',ORIGINAL),('路线平均费用','按路线观察已结算记录的均值；用 ROUND 保持两位小数。',"SELECT route, ROUND(AVG(amount),2) AS average FROM invoices WHERE status='settled' GROUP BY route ORDER BY route"),('异常温控账单','温度大于8度的账单，为差异复核提供反例。','SELECT customer, COUNT(*) AS count FROM invoices WHERE temperature > 8 GROUP BY customer ORDER BY customer')]
        for name,desc,sql in samples:
            if not db.scalar(select(Sample).where(Sample.name==name)):db.add(Sample(name=name,description=desc,original_sql=sql))
        db.commit()
        # 演示授权只在全新库（授权表为空）时写入，之后由管理员页面维护，重跑不覆盖。
        if db.execute(text('SELECT COUNT(*) FROM customer_access')).scalar()==0:
            demo={'operator@chenggang.test':CUSTOMERS[:2],'viewer@chenggang.test':CUSTOMERS[:1]}
            for email,customers in demo.items():
                user=db.scalar(select(User).where(User.email==email))
                if user:
                    for c in customers:db.add(CustomerAccess(user_id=user.id,customer=c,granted_by='admin@chenggang.test'))
            db.commit()
        return {t:db.execute(text('SELECT COUNT(*) FROM '+t)).scalar() for t in ('users','samples','batches','evidence','invoices','customer_access')}
if __name__=='__main__':print(seed())
