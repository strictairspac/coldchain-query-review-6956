from pydantic import BaseModel,Field
class EvidenceOutput(BaseModel):
    id:int
    batch_id:int
    result:dict
    scope:list[str]=Field(default_factory=list)
    status_reason:str|None=None
    created_by:str|None=None
    created_at:str|None=None
