from fastapi import APIRouter,Depends
from ..config.database import get_db
from ..schemas.batch import BatchInput
from ..services.auth import current_user,writer
from ..services.batch import list_batches,create_batch
from ..services.evidence import batch_status
router=APIRouter(prefix='/batches')
@router.get('')
def listing(db=Depends(get_db),user=Depends(current_user)):return list_batches(db,user)
@router.post('',status_code=202)
def create(data:BatchInput,db=Depends(get_db),user=Depends(writer)):return create_batch(db,data,user)
@router.get('/{batch_id}/status')
def status(batch_id:int,db=Depends(get_db),user=Depends(current_user)):return batch_status(db,batch_id,user)
