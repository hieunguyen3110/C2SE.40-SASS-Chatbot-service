from pydantic import BaseModel

class UploadFileRequest(BaseModel):
    fileName: str
    filePath: str
    docId: int