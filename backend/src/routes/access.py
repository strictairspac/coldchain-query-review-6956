from fastapi import APIRouter,Depends
from pydantic import BaseModel,Field
from ..config.database import get_db
from ..services.access import access_overview,set_access
from ..services.auth import admin
router=APIRouter(prefix='/access')
class Grant(BaseModel):
    customers:list[str]=Field(default_factory=list)
@router.get('')
def overview(db=Depends(get_db),user=Depends(admin)):return access_overview(db)
@router.put('/{user_id}')
def grant(user_id:int,data:Grant,db=Depends(get_db),user=Depends(admin)):
    return set_access(db,user_id,data.customers,user.email)
