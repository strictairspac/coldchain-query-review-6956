"""幂等的轻量 schema 升级，兼容已存在的演示库（schema v1 → v2）。"""
from sqlalchemy import text

UPGRADES=(
    'ALTER TABLE batches ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)',
    'ALTER TABLE batches ADD COLUMN IF NOT EXISTS created_by VARCHAR(120)',
    "ALTER TABLE batches ADD COLUMN IF NOT EXISTS scope JSONB NOT NULL DEFAULT '[]'::jsonb",
    'ALTER TABLE batches ADD COLUMN IF NOT EXISTS status_reason TEXT',
    'ALTER TABLE evidence ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)',
    'ALTER TABLE evidence ADD COLUMN IF NOT EXISTS created_by VARCHAR(120)',
    "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS scope JSONB NOT NULL DEFAULT '[]'::jsonb",
    'ALTER TABLE evidence ADD COLUMN IF NOT EXISTS status_reason TEXT',
)

def ensure_schema(conn):
    """在 create_all 之后补齐旧库缺少的列；新库上为无害的 no-op。"""
    existing={row[0] for row in conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))}
    if 'batches' in existing and 'evidence' in existing:
        for statement in UPGRADES:
            conn.execute(text(statement))
