from sqlalchemy import Column, String, Float, Integer, DateTime, Text
from sqlalchemy.sql import func
from app.database import Base


class Order(Base):
    __tablename__ = "orders"

    order_id = Column(String(100), primary_key=True, index=True)
    item_title = Column(Text, nullable=False)
    ai_clean_title = Column(Text, nullable=True)
    price = Column(Float, nullable=False)
    quantity = Column(Integer, default=1)
    seller_name = Column(String(200), nullable=True)
    seller_express_no = Column(String(100), nullable=True)
    carrier = Column(String(100), nullable=True)
    
    # Timeline dates
    order_date = Column(DateTime, nullable=True)
    pay_date = Column(DateTime, nullable=True)
    ship_date = Column(DateTime, nullable=True)
    receive_date = Column(DateTime, nullable=True)
    
    # Status: pending_shipment, in_transit, received, cancelled
    current_status = Column(String(50), default="pending_shipment")
    
    # Forwarder tracking (nullable until consolidated)
    forwarder_tracking_no = Column(String(100), nullable=True, index=True)
    
    # Local snapshot path
    snapshot_local_path = Column(String(500), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "order_id": self.order_id,
            "item_title": self.item_title,
            "ai_clean_title": self.ai_clean_title,
            "price": self.price,
            "quantity": self.quantity,
            "seller_name": self.seller_name,
            "seller_express_no": self.seller_express_no,
            "carrier": self.carrier,
            "order_date": self.order_date.isoformat() if self.order_date else None,
            "pay_date": self.pay_date.isoformat() if self.pay_date else None,
            "ship_date": self.ship_date.isoformat() if self.ship_date else None,
            "receive_date": self.receive_date.isoformat() if self.receive_date else None,
            "current_status": self.current_status,
            "forwarder_tracking_no": self.forwarder_tracking_no,
            "snapshot_local_path": self.snapshot_local_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
