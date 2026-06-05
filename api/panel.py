import io
import json
import os
import aiosqlite
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from database import crud
from services import excel as excel_service
from config import STORAGE_PATH, DATABASE_URL

router = APIRouter(prefix="/api")


async def _require_accountant(token: str):
    accountant = await crud.get_panel_token(token)
    if not accountant:
        raise HTTPException(status_code=401, detail="Geçersiz veya süresi dolmuş token.")
    return accountant


# ─── ME ───────────────────────────────────────────────────────

@router.get("/me")
async def get_me(token: str = Query(...)):
    accountant = await _require_accountant(token)
    return {"id": accountant["id"], "full_name": accountant["full_name"]}


# ─── CLIENTS ──────────────────────────────────────────────────

@router.get("/clients")
async def get_clients(token: str = Query(...)):
    accountant = await _require_accountant(token)
    clients = await crud.get_panel_clients(accountant["id"])
    return clients


# ─── COMPANIES (CARİLER) ──────────────────────────────────────

@router.get("/companies")
async def get_companies(token: str = Query(...), client_id: int = Query(None)):
    accountant = await _require_accountant(token)
    companies = await crud.get_companies(accountant["id"], client_id)
    return companies


# ─── DOCUMENTS ────────────────────────────────────────────────

@router.get("/documents")
async def get_documents(
    token: str = Query(...),
    client_id: int = Query(...),
    month: str = Query(None),
    company: str = Query(None),
    doc_type: str = Query(None),
):
    accountant = await _require_accountant(token)
    docs = await crud.get_panel_documents(accountant["id"], client_id, month)

    result = []
    for doc in docs:
        ocr = doc.get("ocr_result")
        if isinstance(ocr, str):
            try:
                ocr = json.loads(ocr)
            except Exception:
                ocr = {}
        ocr = ocr or {}

        firma = ocr.get("firma_adi", "")
        if company and company.lower() not in (firma or "").lower():
            continue
        if doc_type and doc.get("doc_type") != doc_type:
            continue

        result.append({
            "id": doc["id"],
            "created_at": doc["created_at"],
            "doc_type": doc.get("doc_type", ""),
            "payment_type": doc.get("payment_type", ""),
            "review_status": doc.get("review_status", "pending"),
            "belge_tipi": ocr.get("belge_tipi", ""),
            "fatura_no": ocr.get("fatura_no", ""),
            "tarih": ocr.get("tarih", ""),
            "firma_adi": firma,
            "vergi_no": ocr.get("vergi_no", ""),
            "kdvsiz_toplam": ocr.get("kdvsiz_toplam"),
            "toplam_kdv": ocr.get("toplam_kdv"),
            "kdv_li_toplam": ocr.get("kdv_li_toplam") or ocr.get("genel_toplam"),
            "kalemler": ocr.get("kalemler", []),
            "notlar": ocr.get("notlar", ""),
            "has_image": bool(doc.get("file_path") and os.path.exists(doc["file_path"])),
            "image_url": f"/api/image/{doc['id']}?token={token}" if doc.get("file_path") else None,
        })
    return result


# ─── DOCUMENT ACTIONS ─────────────────────────────────────────

class DocUpdate(BaseModel):
    firma_adi: Optional[str] = None
    tarih: Optional[str] = None
    fatura_no: Optional[str] = None
    kdv_li_toplam: Optional[float] = None
    kdvsiz_toplam: Optional[float] = None
    toplam_kdv: Optional[float] = None
    payment_type: Optional[str] = None
    notlar: Optional[str] = None


@router.patch("/documents/{doc_id}/approve")
async def approve_document(doc_id: int, token: str = Query(...)):
    accountant = await _require_accountant(token)
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute(
            """UPDATE documents SET review_status='approved'
               WHERE id=? AND batch_id IN (
                   SELECT id FROM document_batches WHERE accountant_id=?
               )""",
            (doc_id, accountant["id"]),
        )
        await db.commit()
    return {"ok": True}


@router.patch("/documents/{doc_id}/update")
async def update_document(doc_id: int, token: str = Query(...), body: DocUpdate = Body(...)):
    accountant = await _require_accountant(token)
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT d.ocr_result, d.payment_type FROM documents d
               JOIN document_batches db ON db.id = d.batch_id
               WHERE d.id=? AND db.accountant_id=?""",
            (doc_id, accountant["id"]),
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Belge bulunamadı.")

        ocr = {}
        if row["ocr_result"]:
            try:
                ocr = json.loads(row["ocr_result"])
            except Exception:
                pass

        if body.firma_adi is not None:
            ocr["firma_adi"] = body.firma_adi
        if body.tarih is not None:
            ocr["tarih"] = body.tarih
        if body.fatura_no is not None:
            ocr["fatura_no"] = body.fatura_no
        if body.kdv_li_toplam is not None:
            ocr["kdv_li_toplam"] = body.kdv_li_toplam
        if body.kdvsiz_toplam is not None:
            ocr["kdvsiz_toplam"] = body.kdvsiz_toplam
        if body.toplam_kdv is not None:
            ocr["toplam_kdv"] = body.toplam_kdv
        if body.notlar is not None:
            ocr["notlar"] = body.notlar

        payment = body.payment_type if body.payment_type is not None else row["payment_type"]

        await db.execute(
            "UPDATE documents SET ocr_result=?, payment_type=?, review_status='approved' WHERE id=?",
            (json.dumps(ocr, ensure_ascii=False), payment, doc_id),
        )
        await db.commit()
    return {"ok": True}


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: int, token: str = Query(...)):
    accountant = await _require_accountant(token)
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT d.file_path FROM documents d
               JOIN document_batches db ON db.id = d.batch_id
               WHERE d.id=? AND db.accountant_id=?""",
            (doc_id, accountant["id"]),
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Bulunamadı.")

        if row["file_path"] and os.path.exists(row["file_path"]):
            os.remove(row["file_path"])

        await db.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        await db.commit()
    return {"ok": True}


# ─── IMAGE ────────────────────────────────────────────────────

@router.get("/image/{doc_id}")
async def get_image(doc_id: int, token: str = Query(...)):
    accountant = await _require_accountant(token)
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT d.file_path FROM documents d
               JOIN document_batches db ON db.id = d.batch_id
               WHERE d.id=? AND db.accountant_id=?""",
            (doc_id, accountant["id"]),
        ) as cursor:
            row = await cursor.fetchone()

    if not row or not row["file_path"] or not os.path.exists(row["file_path"]):
        raise HTTPException(status_code=404, detail="Görsel bulunamadı.")

    with open(row["file_path"], "rb") as f:
        data = f.read()
    return StreamingResponse(io.BytesIO(data), media_type="image/jpeg")


# ─── EXCEL EXPORT ─────────────────────────────────────────────

@router.get("/export/excel")
async def export_excel(
    token: str = Query(...),
    client_id: int = Query(...),
    month: str = Query(None),
):
    accountant = await _require_accountant(token)
    clients = await crud.get_panel_clients(accountant["id"])
    client = next((c for c in clients if c["id"] == client_id), None)
    if not client:
        raise HTTPException(status_code=404, detail="Mükellef bulunamadı.")

    client_name = client.get("full_name") or f"Mukellef_{client_id}"
    docs = await crud.get_panel_documents(accountant["id"], client_id, month)
    if not docs:
        raise HTTPException(status_code=404, detail="Belge bulunamadı.")

    for doc in docs:
        ocr = doc.get("ocr_result")
        if isinstance(ocr, str):
            try:
                doc["ocr_result"] = json.loads(ocr)
            except Exception:
                doc["ocr_result"] = {}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    month_str = f"_{month}" if month else ""
    filename = f"belgeler_{client_name}{month_str}_{timestamp}.xlsx"
    tmp_path = os.path.join(STORAGE_PATH, f"tmp_{filename}")

    excel_service.build_excel(docs, client_name, tmp_path)

    with open(tmp_path, "rb") as f:
        data = f.read()
    try:
        os.remove(tmp_path)
    except Exception:
        pass

    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── PDF EXPORT ───────────────────────────────────────────────

@router.get("/export/pdf")
async def export_pdf(
    token: str = Query(...),
    client_id: int = Query(...),
    month: str = Query(None),
):
    accountant = await _require_accountant(token)
    clients = await crud.get_panel_clients(accountant["id"])
    client = next((c for c in clients if c["id"] == client_id), None)
    if not client:
        raise HTTPException(status_code=404, detail="Mükellef bulunamadı.")

    docs = await crud.get_panel_documents(accountant["id"], client_id, month)
    images = [d["file_path"] for d in docs if d.get("file_path") and os.path.exists(d["file_path"])]

    if not images:
        raise HTTPException(status_code=404, detail="Görsel bulunamadı.")

    try:
        from PIL import Image as PILImage
    except ImportError:
        raise HTTPException(status_code=500, detail="PDF oluşturmak için Pillow gerekli.")

    pil_images = []
    for img_path in images:
        try:
            img = PILImage.open(img_path).convert("RGB")
            pil_images.append(img)
        except Exception:
            continue

    if not pil_images:
        raise HTTPException(status_code=404, detail="Görseller açılamadı.")

    client_name = client.get("full_name") or f"Mukellef_{client_id}"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    month_str = f"_{month}" if month else ""
    filename = f"belgeler_{client_name}{month_str}_{timestamp}.pdf"
    tmp_path = os.path.join(STORAGE_PATH, f"tmp_{filename}")

    pil_images[0].save(
        tmp_path, save_all=True, append_images=pil_images[1:], resolution=150
    )

    with open(tmp_path, "rb") as f:
        data = f.read()
    try:
        os.remove(tmp_path)
    except Exception:
        pass

    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
