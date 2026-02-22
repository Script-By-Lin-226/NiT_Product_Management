from sqlalchemy import Integer, Column, String, DateTime, ForeignKey, func, CheckConstraint
from sqlalchemy.orm import relationship
from app.config.database_utils import Base


class User(Base):  # Renamed for cleaner Python code
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hash_password = Column(String(255), nullable=False)  # Removed unique=True
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Product(Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True)
    product_name = Column(String(255), unique=True, nullable=False, index=True)
    # Relationships
    inventory = relationship("Inventory", back_populates="product", uselist=False, cascade="all, delete-orphan")
    logs = relationship("InventoryLog", back_populates="product", cascade="all, delete-orphan")


class Inventory(Base):
    __tablename__ = 'inventories'
    id = Column(Integer, primary_key=True)
    # unique=True ensures 1 product = 1 inventory row
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False, unique=True, index=True)
    quantity = Column(Integer, nullable=False, default=0)

    # SQL level constraint to prevent negative stock
    __table_args__ = (CheckConstraint('quantity >= 0', name='check_quantity_positive'),)

    product = relationship("Product", back_populates="inventory")


class InventoryLog(Base):
    __tablename__ = 'inventory_logs'
    id = Column(Integer, primary_key=True)
    # Added index=True for fast history lookups
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False, index=True)
    change_amount = Column(Integer, nullable=False)  # Rename 'quantity' to 'change' for clarity
    actor_name = Column(String(255), nullable=True)
    actor_class = Column(String(255), nullable=True)
    given_to = Column(String(255), nullable=True)
    department = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product", back_populates="logs")
