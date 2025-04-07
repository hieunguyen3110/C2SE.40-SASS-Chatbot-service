from pydantic import BaseModel

class CheckFileRequest(BaseModel):
    filePath: str