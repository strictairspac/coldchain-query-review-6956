from sqlalchemy import delete, select, text
from fastapi import HTTPException

from ..models.access import CustomerAccess
from ..models.user import User


def known_customers(db):
    """账单表中真实存在的客户；未授权列表只能从这里取值。"""
    return [row[0] for row in db.execute(text('SELECT DISTINCT customer FROM invoices ORDER BY customer'))]


def allowed_customers(db, user):
    """管理员默认覆盖全部客户；专员只返回管理员显式授权的客户。"""
    if user.role == 'admin':
        return known_customers(db)
    return list(db.scalars(select(CustomerAccess.customer).where(CustomerAccess.user_id == user.id).order_by(CustomerAccess.customer)))


def _granted(db, user_id):
    return list(db.scalars(select(CustomerAccess.customer).where(CustomerAccess.user_id == user_id).order_by(CustomerAccess.customer)))


def format_scope(customers):
    return '、'.join(customers) if customers else '无'


def access_overview(db):
    customers = known_customers(db)
    users = list(db.scalars(select(User).where(User.role != 'admin').order_by(User.id)))
    return {
        'customers': customers,
        'users': [{'id': u.id, 'email': u.email, 'role': u.role, 'customers': _granted(db, u.id)} for u in users],
    }


def set_access(db, user_id, customers, actor):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, '账号不存在')
    if target.role == 'admin':
        raise HTTPException(400, '管理员默认可查全部客户，无需单独配置')
    known = set(known_customers(db))
    normalized = sorted({str(c).strip() for c in customers if str(c).strip()})
    unknown = [c for c in normalized if c not in known]
    if unknown:
        raise HTTPException(400, '未知客户：' + '、'.join(unknown))
    db.execute(delete(CustomerAccess).where(CustomerAccess.user_id == user_id))
    for customer in normalized:
        db.add(CustomerAccess(user_id=user_id, customer=customer, granted_by=actor))
    db.commit()
    return {'id': target.id, 'email': target.email, 'role': target.role, 'customers': normalized}
