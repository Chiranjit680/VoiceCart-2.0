from sqlalchemy import Boolean, Column, Integer, String, Text, ForeignKey, JSON, DECIMAL, LargeBinary, Index, UniqueConstraint, exists
from sqlalchemy.orm import relationship, column_property
from sqlalchemy.sql.expression import text
from sqlalchemy.sql.sqltypes import TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    phone = Column(String, unique=True, index=True, nullable=True)
    address = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'))

    orders = relationship("Orders", back_populates="user", cascade="all, delete-orphan")
    cart = relationship("Cart", back_populates="user", cascade="all, delete-orphan")
    reviews = relationship("Reviews", back_populates="user", cascade="all, delete-orphan")
    chat_messages = relationship("ChatMessage", back_populates="user", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)

    specs = Column(JSONB, nullable=True) # Using JSONB for better performance with PostgreSQL

    price = Column(DECIMAL(precision=10, scale=2), nullable=False)
    for_sale = Column(Boolean, default=True, nullable=False)
    stock = Column(Integer, default=0, nullable=False)
    brand_name = Column(String, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'))
    avg_rating = Column(DECIMAL(precision=2, scale=1), default=0.0, nullable=False)
    num_reviews = Column(Integer, default=0, nullable=False)
    num_sold = Column(Integer, default=0, nullable=False)

    # REMOVED: image = Column(LargeBinary...) 
    # REASON: Storing blobs in the main table slows down every query.
    
    # Relationships
    images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan")
    categories = relationship("ProductCategory", back_populates="product", cascade="all, delete-orphan")
    reviews = relationship("Reviews", back_populates="product", cascade="all, delete-orphan")
    cart = relationship("Cart", back_populates="product", cascade="all, delete-orphan")
    order_items = relationship("OrderItem", back_populates="product", cascade="all, delete-orphan")

    # Optimization: Indexes for fast searching/filtering
    __table_args__ = (
        Index('idx_product_name_brand', 'name', 'brand_name'),
        Index('idx_product_price', 'price'),
    )

# NEW TABLE: Store heavy images separately
class ProductImage(Base):
    __tablename__ = "product_images"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey('products.id', ondelete="CASCADE"), nullable=False)
    image_data = Column(LargeBinary, nullable=False)
    is_primary = Column(Boolean, default=False) # To know which one to show in search results
    
    product = relationship("Product", back_populates="images")

# Lets clients ask "does this product have a photo?" as part of any product query, without
# loading the image bytes (or the images relationship) just to find out.
Product.has_image = column_property(
    exists().where(ProductImage.product_id == Product.id).correlate_except(ProductImage)
)

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    name = Column(String, nullable=False, unique=True) # Added unique constraint
    parent_id = Column(Integer, ForeignKey('categories.id', ondelete='SET NULL'), nullable=True)

    parent = relationship("Category", remote_side=[id], backref="children")
    products = relationship("ProductCategory", back_populates="category", cascade="all, delete-orphan")

class ProductCategory(Base):
    __tablename__ = "product_categories"

    product_id = Column(Integer, ForeignKey('products.id', ondelete='CASCADE'), primary_key=True, nullable=False)
    category_id = Column(Integer, ForeignKey('categories.id', ondelete='CASCADE'), primary_key=True, nullable=False)

    product = relationship("Product", back_populates="categories")
    category = relationship("Category", back_populates="products")

class Cart(Base):
    __tablename__ = "cart"

    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey('products.id', ondelete="CASCADE"), primary_key=True)
    quantity = Column(Integer, nullable=False, default=1)

    user = relationship("User", back_populates="cart")
    product = relationship("Product", back_populates="cart")

class Orders(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    total_amount = Column(DECIMAL(precision=10, scale=2), nullable=False)
    status = Column(String, default="pending", nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'))
    address = Column(String, nullable=True)

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

class OrderItem(Base):
    __tablename__ = "order_items"

    order_id = Column(Integer, ForeignKey('orders.id'), nullable=False, index=True, primary_key=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False, primary_key=True)
    quantity = Column(Integer, default=1, nullable=False)
    price = Column(DECIMAL(precision=10, scale=2), nullable=False)

    order = relationship("Orders", back_populates="items")
    product = relationship("Product", back_populates="order_items")

class Reviews(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(String, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'))

    user = relationship("User", back_populates="reviews")
    product = relationship("Product", back_populates="reviews")
    
# ChatMessage Class (As referenced in User)
class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    message = Column(String)
    user = relationship("User", back_populates="chat_messages")


class ChatSession(Base):
    """One voice conversation: a single WebSocket connection (or a reconnect within the resume window)."""
    __tablename__ = "chat_sessions"

    id = Column(String(36), primary_key=True)  # UUID, also used as the agent's checkpoint thread id
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    started_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)
    last_activity_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)
    ended_at = Column(TIMESTAMP(timezone=True), nullable=True)
    end_reason = Column(String, nullable=True)  # "disconnect" | "idle"
    turn_count = Column(Integer, default=0, nullable=False)  # exchanges, i.e. user messages

    user = relationship("User", back_populates="chat_sessions")
    turns = relationship(
        "ChatTurn", back_populates="session", cascade="all, delete-orphan", order_by="ChatTurn.seq"
    )


class ChatTurn(Base):
    """One message in a session: what the user said, or what an agent replied."""
    __tablename__ = "chat_turns"
    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_chat_turns_session_seq"),
        # Lets the memory service find unchecked turns without scanning the whole table.
        # Keep in step with app/migrations.py, which adds the same index to databases that already have the table.
        Index("ix_chat_turns_unchecked", "id", postgresql_where=text("checked = false")),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    seq = Column(Integer, nullable=False)
    role = Column(String, nullable=False)  # "user" | "assistant"
    agent = Column(String, nullable=True)  # which subagent replied: product, cart, order, ...
    content = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)

    # Written by the long-term memory service (longterm_memory/), not by the API:
    checked = Column(Boolean, nullable=False, default=False, server_default=text("false"))  # the service has looked at this turn
    longterm = Column(Boolean, nullable=False, default=False, server_default=text("false"))  # and saved it to long-term memory

    session = relationship("ChatSession", back_populates="turns")

# from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, JSON, DECIMAL, LargeBinary
# from sqlalchemy.orm import relationship
# from sqlalchemy.sql.expression import text
# from sqlalchemy.sql.sqltypes import TIMESTAMP

# from .database import Base

# class User(Base):
#     __tablename__ = "users"

#     id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
#     name = Column(String, nullable=False)
#     email = Column(String, unique=True, index=True, nullable=False)
#     password = Column(String, nullable=False)
#     phone = Column(String, unique=True, index=True, nullable=True, server_default=None)
#     address = Column(String, nullable=True, server_default=None)
#     is_admin = Column(Boolean, default=False, nullable=False)
#     created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'))

#     orders = relationship("Orders", back_populates="user", cascade="all, delete-orphan")
#     cart = relationship("Cart", back_populates="user", cascade="all, delete-orphan")
#     reviews = relationship("Reviews", back_populates="user", cascade="all, delete-orphan")
#     chat_messages = relationship("ChatMessage", back_populates="user", cascade="all, delete-orphan")  # Add this line

# class Product(Base):
#     __tablename__ = "products"

#     id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
#     name = Column(String, nullable=False)
#     description = Column(String, nullable=True, server_default=None)
#     specs = Column(JSON, nullable=True, server_default=None)
#     price = Column(DECIMAL(precision=10, scale=2), nullable=False) # price is currently not nullable, # but it can be changed in the future
#     for_sale = Column(Boolean, default=True, nullable=False)
#     stock = Column(Integer, default=0, nullable=False)
#     # image_url = Column(String, nullable=True, server_default=None)
#     image = Column(LargeBinary, nullable=True, server_default=None)  # Storing image as BLOB
#     brand_name = Column(String, nullable=True, server_default=None)
#     created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'))
#     avg_rating = Column(DECIMAL(precision=2, scale=1), default=0.0, nullable=False)  # Average rating of the product
#     num_reviews = Column(Integer, default=0, nullable=False)  # Number of reviews for the product
#     num_sold = Column(Integer, default=0, nullable=False)  # Number of items sold

#     categories = relationship("ProductCategory", back_populates="product", cascade="all, delete-orphan")
#     reviews = relationship("Reviews", back_populates="product", cascade="all, delete-orphan")
#     cart = relationship("Cart", back_populates="product", cascade="all, delete-orphan")
#     order_items = relationship("OrderItem", back_populates="product", cascade="all, delete-orphan")

# class Category(Base):
#     __tablename__ = "categories"

#     id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
#     name = Column(String, nullable=False)
#     parent_id = Column(Integer, ForeignKey('categories.id', ondelete='SET NULL'), nullable=True, server_default=None)

#     parent = relationship("Category", remote_side=[id], backref="children")

#     products = relationship("ProductCategory", back_populates="category", cascade="all, delete-orphan")

# class ProductCategory(Base):
#     __tablename__ = "product_categories"

#     product_id = Column(Integer, ForeignKey('products.id', ondelete='CASCADE'), primary_key=True, nullable=False)
#     category_id = Column(Integer, ForeignKey('categories.id', ondelete='CASCADE'), primary_key=True, nullable=False)

#     product = relationship("Product", back_populates="categories")
#     category = relationship("Category", back_populates="products")

# class Cart(Base):
#     __tablename__ = "cart"

#     user_id = Column(Integer, ForeignKey('users.id'), primary_key=True, index=True)
#     product_id = Column(Integer, ForeignKey('products.id'), primary_key=True)
#     quantity = Column(Integer, nullable=False, default=1)

#     user = relationship("User", back_populates="cart")
#     product = relationship("Product", back_populates="cart")

# class Orders(Base):
#     __tablename__ = "orders"

#     id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
#     user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
#     total_amount = Column(DECIMAL(precision=10, scale=2), nullable=False)
#     status = Column(String, default="pending", nullable=False)  # e.g., pending, completed, cancelled
#     created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'))
#     address = Column(String, nullable=True, server_default=None)

#     user = relationship("User", back_populates="orders")
#     items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

# class OrderItem(Base):
#     __tablename__ = "order_items"

#     order_id = Column(Integer, ForeignKey('orders.id'), nullable=False, index=True, primary_key=True)
#     product_id = Column(Integer, ForeignKey('products.id'), nullable=False, primary_key=True)
#     quantity = Column(Integer, default=1, nullable=False)
#     price = Column(DECIMAL(precision=10, scale=2), nullable=False)  # Price at the time of order

#     order = relationship("Orders", back_populates="items")
#     product = relationship("Product", back_populates="order_items")

# class Reviews(Base):
#     __tablename__ = "reviews"

#     id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
#     user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
#     product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
#     rating = Column(Integer, nullable=False)  # e.g., 1 to 5 stars
#     comment = Column(String, nullable=True, server_default=None)
#     created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'))

#     user = relationship("User", back_populates="reviews")
#     product = relationship("Product", back_populates="reviews")


# # class ChatMessage(Base):
# #     __tablename__ = "chat_messages"

# #     id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
# #     user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
# #     content = Column(String, nullable=False)
# #     created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'))

# #     user = relationship("User", back_populates="chat_messages")



# # class AgentResponse(Base):
# #     __tablename__ = "agent_responses"

# #     id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
# #     type = Column(String, nullable=False)
# #     text_content = Column(String, nullable=False)
# #     structured_data = Column(JSON, nullable=True)
# #     timestamp = Column(TIMESTAMP(timezone=True), server_default=text('now()'))
# #     agent_type = Column(String, nullable=False)

# #     requires_feedback = Column(Boolean, default=False)
# #     conversation_id = Column(String, nullable=False)
# #     conversation_ended = Column(Boolean, default=False)