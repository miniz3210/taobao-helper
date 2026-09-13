"""
Main FastAPI Application
Taobao & Freight Forwarding Helper
"""
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import os
from pathlib import Path

from app.database import init_db, get_session
from app.models.order import Order
from app.models.forwarder import ForwarderTracking
from app.models.system_log import SystemLog
from app.modules.backup_export_engine import BackupExportEngine
from app.modules.image_archiver import ImageArchiver
from app.modules.taobao_scraper import TaobaoScraper
from app.modules.notes_generator import NotesGenerator
from app.modules.consolidation_manager import ConsolidationManager
from app.modules.ai_assistant import AIQueryAssistant
from app.modules.taobao_login import TaobaoLogin


# Initialize FastAPI app
app = FastAPI(
    title="Taobao & Freight Forwarding Helper",
    description="Track Taobao orders and manage freight forwarding consolidations",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files and snapshots
app.mount("/static", StaticFiles(directory="/app/app/static"), name="static")
app.mount("/snapshots", StaticFiles(directory="/app/data/snapshots"), name="snapshots")

# Initialize modules
backup_engine = BackupExportEngine()
image_archiver = ImageArchiver()
taobao_scraper = TaobaoScraper(image_archiver)
notes_generator = NotesGenerator()
consolidation_manager = ConsolidationManager()
ai_assistant = AIQueryAssistant()
taobao_login = TaobaoLogin()


# Pydantic models for request/response
class OrderCreate(BaseModel):
    order_id: str
    item_title: str
    price: float
    quantity: int = 1
    seller_name: Optional[str] = None
    seller_express_no: Optional[str] = None
    current_status: str = "pending_shipment"
    snapshot_url: Optional[str] = None


class ScrapeRequest(BaseModel):
    cookies: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AIQueryRequest(BaseModel):
    query: str


class ConsolidationRequest(BaseModel):
    order_ids: List[str]
    tracking_no: str


class ForwarderStatusUpdate(BaseModel):
    tracking_no: str
    status: str


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    await init_db()
    print("✅ Database initialized")


# Root endpoint - serve HTML interface
@app.get("/")
async def root():
    """Serve the main web interface"""
    html_path = Path("/app/app/templates/index.html")
    if html_path.exists():
        return FileResponse(html_path)
    return {"message": "Taobao Helper API is running. Web UI not yet available."}


# ==================== ORDER ENDPOINTS ====================

@app.get("/api/orders")
async def get_orders(
    status: Optional[str] = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_session)
):
    """Get all orders, optionally filtered by status"""
    query = select(Order).order_by(Order.order_date.desc()).limit(limit)
    
    if status:
        query = query.where(Order.current_status == status)
    
    result = await session.execute(query)
    orders = result.scalars().all()
    
    return {
        "orders": [order.to_dict() for order in orders],
        "count": len(orders)
    }


@app.get("/api/orders/{order_id}")
async def get_order(order_id: str, session: AsyncSession = Depends(get_session)):
    """Get a specific order by ID"""
    result = await session.execute(select(Order).where(Order.order_id == order_id))
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return order.to_dict()


@app.post("/api/orders")
async def create_order(
    order_data: OrderCreate,
    session: AsyncSession = Depends(get_session)
):
    """Manually create a new order"""
    order = await taobao_scraper.manual_add_order(
        session,
        order_data.dict()
    )
    
    # Download snapshot if URL provided
    if order_data.snapshot_url:
        local_path = await image_archiver.download_and_save(
            order_data.snapshot_url,
            order_data.order_id
        )
        if local_path:
            order.snapshot_local_path = local_path
            await session.commit()
    
    return order.to_dict()


@app.delete("/api/orders/{order_id}")
async def delete_order(order_id: str, session: AsyncSession = Depends(get_session)):
    """Delete an order"""
    result = await session.execute(select(Order).where(Order.order_id == order_id))
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Delete snapshot
    await image_archiver.delete_snapshot(order_id)
    
    await session.delete(order)
    await session.commit()
    
    return {"message": "Order deleted successfully"}


# ==================== SCRAPING ENDPOINTS ====================

@app.post("/api/login")
async def login_taobao(request: LoginRequest):
    """Login to Taobao with username and password"""
    result = await taobao_login.login_with_account(
        request.username,
        request.password
    )
    return result


@app.post("/api/scrape")
async def scrape_taobao(
    request: ScrapeRequest,
    session: AsyncSession = Depends(get_session)
):
    """Scrape orders from Taobao using cookies"""
    scraped_orders = await taobao_scraper.fetch_orders_from_taobao(request.cookies)
    
    new_count, updated_count, change_logs = await taobao_scraper.sync_orders(
        session,
        scraped_orders
    )
    
    return {
        "success": True,
        "new_orders": new_count,
        "updated_orders": updated_count,
        "changes": change_logs
    }


# ==================== AI QUERY ENDPOINTS ====================

@app.post("/api/ai-query")
async def ai_query(
    request: AIQueryRequest,
    session: AsyncSession = Depends(get_session)
):
    """Natural language query interface"""
    result = await ai_assistant.query(request.query, session)
    return result


# ==================== CONSOLIDATION ENDPOINTS ====================

@app.get("/api/forwarders")
async def get_forwarders(session: AsyncSession = Depends(get_session)):
    """Get all forwarder trackings"""
    forwarders = await consolidation_manager.get_all_forwarders(session)
    return {
        "forwarders": [f.to_dict() for f in forwarders],
        "count": len(forwarders)
    }


@app.get("/api/forwarders/{tracking_no}")
async def get_forwarder_orders(
    tracking_no: str,
    session: AsyncSession = Depends(get_session)
):
    """Get all orders for a specific forwarder tracking"""
    orders = await consolidation_manager.get_orders_by_forwarder(session, tracking_no)
    return {
        "tracking_no": tracking_no,
        "orders": [order.to_dict() for order in orders],
        "count": len(orders)
    }


@app.post("/api/consolidation/bind")
async def bind_to_forwarder(
    request: ConsolidationRequest,
    session: AsyncSession = Depends(get_session)
):
    """Bind orders to a forwarder tracking number"""
    result = await consolidation_manager.bind_orders_to_forwarder(
        session,
        request.order_ids,
        request.tracking_no
    )
    return result


@app.post("/api/consolidation/unbind/{order_id}")
async def unbind_from_forwarder(
    order_id: str,
    session: AsyncSession = Depends(get_session)
):
    """Remove forwarder binding from an order"""
    success = await consolidation_manager.unbind_order(session, order_id)
    
    if success:
        return {"message": "Order unbound successfully"}
    else:
        raise HTTPException(status_code=404, detail="Order not found")


@app.put("/api/forwarders/status")
async def update_forwarder_status(
    request: ForwarderStatusUpdate,
    session: AsyncSession = Depends(get_session)
):
    """Update forwarder tracking status"""
    forwarder = await consolidation_manager.update_forwarder_status(
        session,
        request.tracking_no,
        request.status
    )
    return forwarder.to_dict()


@app.get("/api/consolidation/export/{tracking_no}")
async def export_customs_declaration(
    tracking_no: str,
    session: AsyncSession = Depends(get_session)
):
    """Export customs declaration sheet"""
    file_path = await consolidation_manager.export_customs_declaration(
        session,
        tracking_no
    )
    
    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=os.path.basename(file_path)
    )


# ==================== BACKUP & EXPORT ENDPOINTS ====================

@app.get("/api/backup/create")
async def create_backup():
    """Create full system backup"""
    backup_path = await backup_engine.create_full_backup()
    
    return FileResponse(
        backup_path,
        media_type="application/zip",
        filename=os.path.basename(backup_path)
    )


@app.post("/api/backup/restore")
async def restore_backup(file: UploadFile = File(...)):
    """Restore system from backup"""
    temp_path = f"/tmp/{file.filename}"
    
    # Save uploaded file
    with open(temp_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    # Restore
    stats = await backup_engine.restore_backup(temp_path)
    
    # Clean up temp file
    os.remove(temp_path)
    
    return stats


@app.get("/api/export/excel")
async def export_excel(session: AsyncSession = Depends(get_session)):
    """Export all orders to Excel"""
    file_path = await backup_engine.export_to_excel(session)
    
    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=os.path.basename(file_path)
    )


@app.get("/api/export/csv")
async def export_csv(session: AsyncSession = Depends(get_session)):
    """Export all orders to CSV"""
    file_path = await backup_engine.export_to_csv(session)
    
    return FileResponse(
        file_path,
        media_type="text/csv",
        filename=os.path.basename(file_path)
    )


# ==================== NOTES ENDPOINTS ====================

@app.get("/api/notes")
async def get_notes(session: AsyncSession = Depends(get_session)):
    """Generate and return notes text"""
    # Get recent changes
    result = await session.execute(
        select(SystemLog)
        .where(SystemLog.log_type == 'state_change')
        .order_by(SystemLog.created_at.desc())
        .limit(20)
    )
    recent_logs = result.scalars().all()
    recent_changes = [log.message for log in recent_logs]
    
    notes_content = await notes_generator.generate_notes(session, recent_changes)
    
    return {
        "content": notes_content,
        "generated_at": datetime.now().isoformat()
    }


@app.get("/api/stats")
async def get_stats(session: AsyncSession = Depends(get_session)):
    """Get order statistics"""
    summary = await notes_generator.get_status_summary(session)
    
    # Total orders
    result = await session.execute(select(Order))
    total_orders = len(result.scalars().all())
    
    # Total value
    result = await session.execute(select(Order))
    orders = result.scalars().all()
    total_value = sum(order.price * order.quantity for order in orders)
    
    return {
        "total_orders": total_orders,
        "total_value": total_value,
        "by_status": summary
    }


# ==================== SYSTEM ENDPOINTS ====================

@app.get("/api/logs")
async def get_logs(
    log_type: Optional[str] = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_session)
):
    """Get system logs"""
    query = select(SystemLog).order_by(SystemLog.created_at.desc()).limit(limit)
    
    if log_type:
        query = query.where(SystemLog.log_type == log_type)
    
    result = await session.execute(query)
    logs = result.scalars().all()
    
    return {
        "logs": [log.to_dict() for log in logs],
        "count": len(logs)
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
