from sqlalchemy import Column, String, Integer, DateTime, Text
from sqlalchemy.sql import func
from app.database import Base


class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Log type: state_change, scrape, export, backup, restore
    log_type = Column(String(50), nullable=False, index=True)
    
    # Related order or tracking
    order_id = Column(String(100), nullable=True, index=True)
    
    # Log message
    message = Column(Text, nullable=False)
    
    # Additional metadata (JSON string)
    meta_data = Column(Text, nullable=True)
    
    # Timestamp
    created_at = Column(DateTime, server_default=func.now(), index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "log_type": self.log_type,
            "order_id": self.order_id,
            "message": self.message,
            "meta_data": self.meta_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
