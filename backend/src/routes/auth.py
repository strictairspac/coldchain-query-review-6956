from fastapi import APIRouter,Depends
from pydantic import BaseModel,Field
from sqlalchemy import select
from ..config.database import get_db
from ..controllers.auth import login
from ..models.user import User
from ..services.access import allowed_customers
from ..services.auth import current_user
router=APIRouter(prefix='/auth')
class Login(BaseModel):
    email:str=Field(max_length=120)
    password:str=Field(max_length=100)
@router.post('/login')
def signin(data:Login,db=Depends(get_db)):
    result=login(db,data.email,data.password)
    user=db.scalar(select(User).where(User.email==data.email))
    result['customers']=allowed_customers(db,user) if user else []
    return result
@router.get('/me')
def me(db=Depends(get_db),user=Depends(current_user)):return {'email':user.email,'role':user.role,'customers':allowed_customers(db,user)}
