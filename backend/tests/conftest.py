import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 配置在导入任何 src 模块之前完成；没有测试库时整组跳过。
if os.getenv('TEST_DATABASE_URL'):
    os.environ.setdefault('DATABASE_URL', os.environ['TEST_DATABASE_URL'])
    os.environ.setdefault('JWT_SECRET', 'test-secret')
    os.environ.setdefault('SEED_DEMO', 'false')
    os.environ.setdefault('ARTIFACTS_DIR', os.getenv('TEST_ARTIFACTS', '/tmp/query-review-artifacts'))


@pytest.fixture(scope='session')
def database_url():
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('设置 TEST_DATABASE_URL 指向可写的 PostgreSQL 测试库后运行集成测试')
    return url
