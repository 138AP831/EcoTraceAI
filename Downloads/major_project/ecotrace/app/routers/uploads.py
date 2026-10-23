"""File upload endpoints for evidence media and invoices.

POST /collections/{id}/media  — upload one or more files (multipart/form-data).
Files are stored under uploads/<collection_id>/ on disk.
The collection must exist; no state-machine restriction (media can be attached at
any point). Returns a list of MediaFile records.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_operator
from app.db import get_db
from app.models import Collection, MediaFile, User
from app.services import write_audit

router = APIRouter(tags=["uploads"])

UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "uploads"))
_ALLOWED_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "application/pdf", "video/mp4", "video/quicktime",
}
MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB


class MediaFileOut(BaseModel):
    id: str
    collection_id: str
    filename: str
    content_type: str
    size_bytes: int
    file_purpose: str
    storage_path: str
    created_at: datetime

    model_config = {"from_attributes": True}


@router.post(
    "/collections/{collection_id}/media",
    response_model=list[MediaFileOut],
    status_code=status.HTTP_201_CREATED,
)
def upload_media(
    collection_id: str,
    files: list[UploadFile] = File(...),
    file_purpose: str = Form("evidence_media"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Upload one or more media files attached to a collection.

    `file_purpose` can be `evidence_media` (default) or `invoice`.
    """
    collection = db.get(Collection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="collection_not_found")

    if file_purpose not in ("evidence_media", "invoice"):
        raise HTTPException(status_code=422, detail="invalid_file_purpose")

    dest_dir = os.path.join(UPLOAD_DIR, collection_id)
    os.makedirs(dest_dir, exist_ok=True)

    created: list[MediaFile] = []
    for upload in files:
        content_type = upload.content_type or "application/octet-stream"
        if content_type not in _ALLOWED_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"unsupported_content_type:{content_type}",
            )

        data = upload.file.read()
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(status_code=422, detail="file_too_large")

        safe_name = f"{uuid.uuid4().hex}_{os.path.basename(upload.filename or 'file')}"
        dest_path = os.path.join(dest_dir, safe_name)
        with open(dest_path, "wb") as fh:
            fh.write(data)

        mf = MediaFile(
            collection_id=collection_id,
            filename=upload.filename or safe_name,
            content_type=content_type,
            size_bytes=len(data),
            storage_path=dest_path,
            file_purpose=file_purpose,
            uploaded_by=current_user.id,
        )
        db.add(mf)
        created.append(mf)

    db.flush()
    write_audit(
        db, "collection", collection_id, "media_uploaded",
        {"count": len(created), "purpose": file_purpose},
    )
    db.commit()
    for mf in created:
        db.refresh(mf)
    return created


@router.get("/collections/{collection_id}/media", response_model=list[MediaFileOut])
def list_media(
    collection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """List all media files attached to a collection."""
    collection = db.get(Collection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="collection_not_found")
    return (
        db.query(MediaFile)
        .filter(MediaFile.collection_id == collection_id)
        .order_by(MediaFile.created_at)
        .all()
    )
