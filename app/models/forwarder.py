from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.sql import func
from app.database import Base


class ForwarderTracking(Base):
    __tablename__ = "forwarder_trackings"

    tracking_no = Column(String(100), primary_key=True, index=True)
    
    # Status: pending_consolidation, consolidating, in_transit, delivered
    status = Column(String(50), default="pending_consolidation")
    
    # Notes and custom declaration info
    notes = Column(Text, nullable=True)
    
    # Timeline
    consolidation_date = Column(DateTime, nullable=True)
    ship_date = Column(DateTime, nullable=True)
    delivery_date = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "tracking_no": self.tracking_no,
            "status": self.status,
            "notes": self.notes,
            "consolidation_date": self.consolidation_date.isoformat() if self.consolidation_date else None,
            "ship_date": self.ship_date.isoformat() if self.ship_date else None,
            "delivery_date": self.delivery_date.isoformat() if self.delivery_date else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
