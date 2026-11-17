Schema version 2: SQLAlchemy metadata creates users/samples/batches/evidence/audit/customer_access. seed_demo initializes the separate invoices fixture table and NOLOGIN query_reader, enables row-level security on invoices with policy `invoices_customer_scope`, and grants SELECT to query_reader.

客户授权模型：

- `customer_access(user_id, customer)` 是管理员配置的逐客户授权；无行即无数据。
- `batches.scope` 与 `evidence.scope` 保存实际执行的客户范围快照，`created_by`/`user_id` 支持证据归属。
- `batches.status_reason` 与 `evidence.status_reason` 记录受理、完成、失败或拒绝原因。
- `ensure_schema` 为既有部署补齐上述列，可重复执行。

执行账号通过 `set_config('app.allowed_customers', '["客户A","客户B"]', true)` 声明范围，RLS 策略读取该设置；事务结束自动清空，连接池复用不会串用。`invoices` 的 `query_reader` 必须保留 `GRANT SELECT` 且不能 BYPASSRLS。Run `python -m scripts.seed_demo` for repeatable initialization; natural keys preserve user edits.
