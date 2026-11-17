"""Strict read-only bounded SQL execution against a single seeded business table.

客户范围在两层同时生效：
1. AST 层：把每个 ``invoices`` 表引用改写成只含授权客户行的子查询，相关子查询、
   自连接、任意改写条件都无法绕过。
2. 数据库层：``query_reader`` 角色受行级安全策略约束，事务内通过
   ``set_config(..., is_local=true)`` 设置范围；未设置或范围为空时默认无数据，
   事务结束后自动失效，连接池复用不会串用上一个范围。
"""
import json,hashlib,time
from collections import Counter
import sqlglot
from sqlglot import exp
from sqlalchemy import text
from ..config.database import engine
ALLOWED_FUNCTIONS={'SUM','COUNT','AVG','MIN','MAX','ROUND','COALESCE','CAST'}
ALLOWED_COLUMNS={'customer','route','amount','temperature','invoice_id','status'}

def normalize_customers(customers):
    """去空、去重并排序，保证两侧比较使用完全相同的范围。"""
    return sorted({str(c).strip() for c in (customers or []) if str(c).strip()})

def parse_sql(sql):
    try: trees=sqlglot.parse(sql,read='postgres')
    except Exception as exc: raise ValueError('SQL 无法解析：'+str(exc)[:180])
    if len(trees)!=1 or not isinstance(trees[0],exp.Select): raise ValueError('只允许单条 SELECT')
    tree=trees[0]
    if tree.args.get('into') or tree.args.get('locks') or tree.find(exp.With): raise ValueError('不允许 INTO、锁或 CTE')
    tables=list(tree.find_all(exp.Table))
    if not tables or any(t.name!='invoices' or t.db or t.catalog for t in tables): raise ValueError('只允许访问 invoices 表')
    for col in tree.find_all(exp.Column):
        if col.name not in ALLOWED_COLUMNS and col.name!='*': raise ValueError('未知业务字段：'+col.name)
    for f in tree.find_all(exp.Func):
        if f.sql_name() not in ALLOWED_FUNCTIONS: raise ValueError('不允许函数：'+f.sql_name())
    if len(list(tree.walk()))>250: raise ValueError('SQL 结构过大')
    return tree

def validate_sql(sql):
    return parse_sql(sql).sql(dialect='postgres')

def _scope_condition(customers):
    customers=normalize_customers(customers)
    if not customers: return exp.false()
    return exp.In(this=exp.column('customer'),expressions=[exp.Literal.string(c) for c in customers])

def scoped_sql(sql,customers):
    """将每个 invoices 表引用收窄到授权客户，返回可执行 SQL。"""
    tree=parse_sql(sql)
    condition=_scope_condition(customers)
    def rewrite(node):
        if isinstance(node,exp.Table) and node.name=='invoices' and not node.db and not node.catalog:
            alias=node.alias_or_name
            inner=exp.select('*').from_(exp.Table(this=exp.to_identifier('invoices'))).where(condition.copy())
            return exp.Subquery(this=inner,alias=exp.TableAlias(this=exp.to_identifier(alias)))
        return node
    return tree.transform(rewrite).sql(dialect='postgres')

def execute_query(sql,customers=None):
    """只读执行；customers 为空时默认无数据（不是无限制）。"""
    scope=normalize_customers(customers)
    scoped=scoped_sql(sql,scope)
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text('SET TRANSACTION READ ONLY'))
            conn.execute(text("SET LOCAL statement_timeout='2500ms'"))
            # is_local=true：事务结束即失效，连接被池复用时不会带入下一个客户范围。
            conn.execute(text("SELECT set_config('app.allowed_customers', :scope, true)"),{'scope':json.dumps(scope)})
            conn.execute(text('SET LOCAL ROLE query_reader'))
            plan=conn.execute(text('EXPLAIN (ANALYZE, FORMAT JSON, BUFFERS) '+scoped)).scalar()
            started=time.perf_counter()
            cursor=conn.execute(text(scoped)); columns=list(cursor.keys()); rows=cursor.fetchmany(1001)
            if len(rows)>1000: raise ValueError('结果超过 1000 行，请聚合或 LIMIT')
            rows=[[str(v) if v is not None else None for v in row] for row in rows]
            return {'columns':columns,'rows':rows,'row_count':len(rows),'elapsed_ms':round((time.perf_counter()-started)*1000,3),'plan':plan,'scope':scope}

def compare(original,candidate,customers=None):
    scope=normalize_customers(customers)
    left=execute_query(original,scope);right=execute_query(candidate,scope)
    canon=lambda data:Counter(json.dumps(row,ensure_ascii=False) for row in data['rows'])
    a,b=canon(left),canon(right)
    equivalent=len(left['columns'])==len(right['columns']) and a==b
    digest=lambda x:hashlib.sha256(json.dumps(sorted(canon(x).items()),ensure_ascii=False).encode()).hexdigest()
    return {'equivalent':equivalent,'comparison':'忽略行顺序、保留重复行；按输出列位置比较，数字按数据库文本表示','scope':scope,'scope_note':'原始与候选 SQL 使用同一客户范围；范围外账单不可见','original':left,'candidate':right,'original_checksum':digest(left),'candidate_checksum':digest(right),'missing_rows':list((a-b).elements())[:10],'extra_rows':list((b-a).elements())[:10],'note':'执行时间受缓存与机器负载影响；不据一次耗时断言优化收益'}
