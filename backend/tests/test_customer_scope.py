"""客户授权隔离的集成测试。

运行方式：先启动一个可写的 PostgreSQL 测试库，然后
``TEST_DATABASE_URL=postgresql+psycopg2://... pytest backend/tests``。
测试使用独立 schema 清理后的数据，覆盖撤权、越权语句和连接复用。
"""
import os
import uuid

import pytest

CUSTOMERS = ('澄港海产', '南港鲜食', '北湾冷运')


def _qe():
    from src.services import query_engine
    return query_engine


@pytest.fixture(scope='module')
def app_client(database_url, monkeypatch_module):
    import fakeredis
    from fastapi.testclient import TestClient

    from src.services import batch as batch_service
    fake = fakeredis.FakeRedis()
    monkeypatch_module.setattr(batch_service, 'queue', fake)
    import src.worker as worker
    monkeypatch_module.setattr(worker, 'queue', fake)
    from src.config.database import Session, engine
    from src.models.batch import Batch
    from src.models.evidence import Evidence
    from src.main import app
    from sqlalchemy import delete

    from scripts.seed_demo import seed
    seed()
    with Session() as db:
        db.execute(delete(Evidence))
        db.execute(delete(Batch))
        db.commit()
    worker.ARTIFACTS = __import__('pathlib').Path(os.getenv('TEST_ARTIFACTS', '/tmp/query-review-artifacts'))
    return TestClient(app), worker, Session, engine


@pytest.fixture(scope='module')
def monkeypatch_module():
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


def _login(client, email):
    response = client.post('/auth/login', json={'email': email, 'password': 'ColdChain!17'})
    assert response.status_code == 200, response.text
    return {'Authorization': 'Bearer ' + response.json()['token']}


def _grant(client, admin, user_id, customers):
    response = client.put(f'/access/{user_id}', json={'customers': list(customers)}, headers=admin)
    assert response.status_code == 200, response.text
    return response.json()


def _user_id(client, admin, email):
    return next(u['id'] for u in client.get('/access', headers=admin).json()['users'] if u['email'] == email)


CANDIDATE = ('SELECT customer, SUM(amount) AS total FROM invoices WHERE temperature <= 8 '
             'GROUP BY customer HAVING SUM(amount) > 100 ORDER BY customer')


def test_unscoped_and_null_scope_read_nothing(database_url):
    execute_query = _qe().execute_query
    assert execute_query('SELECT COUNT(*) FROM invoices', [])['rows'] == [['0']]
    assert execute_query('SELECT COUNT(*) FROM invoices', None)['rows'] == [['0']]


def test_scope_cannot_be_widened_by_subqueries_or_rewrites(database_url):
    execute_query = _qe().execute_query
    scope = ['南港鲜食']
    bypasses = [
        'SELECT DISTINCT j.customer FROM invoices i JOIN invoices j ON true ORDER BY 1',
        "SELECT DISTINCT customer FROM invoices WHERE customer NOT IN ('南港鲜食')",
        'SELECT customer FROM invoices WHERE customer IN (SELECT customer FROM invoices WHERE temperature > 8)',
        'SELECT (SELECT SUM(amount) FROM invoices)',
        'SELECT COUNT(*) FROM invoices',
    ]
    for sql in bypasses:
        rows = execute_query(sql, scope)['rows']
        if len(sql.split()) and sql.startswith('SELECT (SELECT'):
            # 标量子查询只能看到本客户的数据
            assert rows == [['18130.00']], sql
        else:
            flat = [cell for row in rows for cell in row]
            assert all(value in ('南港鲜食', '200', '0') for value in flat), (sql, rows)
    # 无范围时所有绕过语句都返回空/空聚合
    assert execute_query('SELECT DISTINCT j.customer FROM invoices i JOIN invoices j ON true', [])['rows'] == []


def test_compare_records_actual_scope_and_matches_rows(database_url):
    compare = _qe().compare
    normalize_customers = _qe().normalize_customers
    scope = ['澄港海产', '南港鲜食']
    expected = sorted(scope)
    result = compare(CANDIDATE, CANDIDATE, scope)
    assert result['equivalent'] is True
    assert normalize_customers(result['scope']) == expected
    assert {row[0] for row in result['original']['rows']} <= set(scope)
    assert result['original']['scope'] == result['candidate']['scope'] == expected


def test_pooled_connections_do_not_leak_scope(database_url):
    execute_query = _qe().execute_query
    execute_query('SELECT COUNT(*) FROM invoices', ['北湾冷运'])
    assert execute_query('SELECT COUNT(*) FROM invoices', [])['rows'] == [['0']]
    execute_query('SELECT COUNT(*) FROM invoices', ['北湾冷运', '南港鲜食'])
    assert execute_query('SELECT COUNT(*) FROM invoices', ['澄港海产'])['rows'] == [['200']]


def test_api_authorization_lifecycle(app_client):
    client, worker, Session, engine = app_client
    admin = _login(client, 'admin@chenggang.test')
    operator = _login(client, 'operator@chenggang.test')
    viewer = _login(client, 'viewer@chenggang.test')
    operator_id = _user_id(client, admin, 'operator@chenggang.test')

    # 未授权默认无数据，且不能提交
    _grant(client, admin, operator_id, [])
    denied = client.post('/batches', headers=operator,
                         json={'name': 'no-grant-' + uuid.uuid4().hex[:6], 'sample_id': 1, 'candidate_sql': CANDIDATE})
    assert denied.status_code == 403

    _grant(client, admin, operator_id, ['澄港海产', '南港鲜食'])
    created = client.post('/batches', headers=operator,
                          json={'name': 'ok-' + uuid.uuid4().hex[:6], 'sample_id': 1, 'candidate_sql': CANDIDATE})
    assert created.status_code == 202, created.text
    batch_id = created.json()['id']
    assert created.json()['status_reason'].startswith('待执行')
    worker.run_one(batch_id)
    status = client.get(f'/batches/{batch_id}/status', headers=operator).json()
    assert status['status'] in ('passed', 'different') and status['has_evidence']
    assert status['status_reason'].startswith('执行完成')

    evidence = client.get(f'/evidence/{batch_id}', headers=operator)
    assert evidence.status_code == 200
    assert _qe().normalize_customers(evidence.json()['scope']) == ['南港鲜食', '澄港海产']

    # 跨客户读取与下载被拒绝；旧证据收窄后归管理员
    assert client.get(f'/evidence/{batch_id}', headers=viewer).status_code == 403
    assert client.get(f'/evidence/{batch_id}/export', headers=viewer).status_code == 403
    assert client.get(f'/evidence/{batch_id}/export', headers=operator).status_code == 200
    _grant(client, admin, operator_id, ['南港鲜食'])
    assert client.get(f'/evidence/{batch_id}', headers=operator).status_code == 403
    assert client.get(f'/evidence/{batch_id}', headers=admin).status_code == 200

    # 排队期间撤权：执行拒绝，留拒绝证据且仅管理员可读
    _grant(client, admin, operator_id, ['澄港海产', '南港鲜食'])
    queued = client.post('/batches', headers=operator,
                         json={'name': 'revoke-' + uuid.uuid4().hex[:6], 'sample_id': 1, 'candidate_sql': CANDIDATE}).json()
    _grant(client, admin, operator_id, [])
    worker.run_one(queued['id'])
    rejected = client.get(f'/batches/{queued["id"]}/status', headers=operator).json()
    assert rejected['status'] == 'failed'
    assert '撤销' in rejected['status_reason']
    assert client.get(f'/evidence/{queued["id"]}', headers=operator).status_code == 403
    assert client.get(f'/evidence/{queued["id"]}', headers=admin).status_code == 200

    # 部分撤权：只执行仍授权的客户
    _grant(client, admin, operator_id, ['澄港海产', '南港鲜食'])
    partial = client.post('/batches', headers=operator,
                          json={'name': 'partial-' + uuid.uuid4().hex[:6], 'sample_id': 1, 'candidate_sql': CANDIDATE}).json()
    _grant(client, admin, operator_id, ['南港鲜食'])
    worker.run_one(partial['id'])
    partial_status = client.get(f'/batches/{partial["id"]}/status', headers=operator).json()
    assert partial_status['evidence_scope'] == ['南港鲜食']
    assert '澄港海产' in partial_status['status_reason']


def test_only_admin_configures_access(app_client):
    client, *_ = app_client
    operator = _login(client, 'operator@chenggang.test')
    assert client.get('/access', headers=operator).status_code == 403
    assert client.put('/access/2', json={'customers': []}, headers=operator).status_code == 403
    admin = _login(client, 'admin@chenggang.test')
    assert client.put('/access/2', json={'customers': ['不存在的客户']}, headers=admin).status_code == 400
