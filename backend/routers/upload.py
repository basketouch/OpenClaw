import base64
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse

from auth import verify_token

UPLOADS_DIR = "/data/uploads"
MAX_SIZE = 20 * 1024 * 1024  # 20MB

ALLOWED = {
    "image/png", "image/jpeg", "image/gif", "image/webp",
    "application/pdf",
    "text/plain", "text/markdown", "text/csv",
}

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload")
async def upload(file: UploadFile = File(...), _: str = Depends(verify_token)):
    if file.content_type not in ALLOWED:
        raise HTTPException(400, f"Tipo no soportado: {file.content_type}")
    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(400, "Archivo demasiado grande (máximo 20MB)")
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    fid = str(uuid.uuid4())[:8]
    safe_name = "".join(c for c in (file.filename or "file") if c.isalnum() or c in "._-")
    path = os.path.join(UPLOADS_DIR, f"{fid}_{safe_name}")
    with open(path, "wb") as f:
        f.write(data)
    return {"file_id": fid, "filename": file.filename, "mime_type": file.content_type, "size": len(data)}
