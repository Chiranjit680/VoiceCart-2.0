# agent/tools.py

import sys
import os
import json
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from langchain_core.tools import tool
from sqlalchemy.orm import joinedload

try:
    from backend.app import database
    from backend.app.models import Product, Cart, Orders, OrderItem, User
except ImportError:
    logging.warning("Backend not available - tools will use mock data")
    database = None

logger = logging.getLogger(__name__)


@tool
def search_products(query: str) -> str:
    """Search for products by name or description"""
    if database is None:
        # Mock data
        return json.dumps([
            {"id": 1, "name": "Gaming Laptop", "price": 1299.99, "stock": 50},
            {"id": 2, "name": "Wireless Mouse", "price": 79.99, "stock": 200}
        ])
    
    db = database.SessionLocal()
    try:
        from sqlalchemy import or_
        results = db.query(Product).filter(
            or_(
                Product.name.ilike(f"%{query}%"),
                Product.description.ilike(f"%{query}%")
            )
        ).limit(10).all()
        
        if not results:
            return f"No products found for '{query}'."
        
        products = [
            {
                "id": p.id,
                "name": p.name,
                "price": float(p.price),
                "stock": p.stock
            }
            for p in results
        ]
        return json.dumps(products)
    except Exception as e:
        logger.error(f"search_products failed: {e}")
        return f"Error: {str(e)}"
    finally:
        db.close()


@tool
def add_to_cart(user_id: int, product_id: int, quantity: int = 1) -> str:
    """Add product to cart"""
    if database is None:
        return f"✅ Mock: Added product {product_id} (x{quantity})"
    
    db = database.SessionLocal()
    try:
        # Check product exists
        prod = db.query(Product).filter(Product.id == product_id).first()
        if not prod:
            return f"❌ Product {product_id} not found."
        
        if prod.stock < quantity:
            return f"❌ Insufficient stock. Available: {prod.stock}"
        
        # Check existing cart item
        existing = db.query(Cart).filter(
            Cart.product_id == product_id,
            Cart.user_id == user_id
        ).first()
        
        if existing:
            existing.quantity += quantity
            db.commit()
            return f"✅ Added {quantity}x '{prod.name}'. Total: {existing.quantity}"
        
        new_item = Cart(user_id=user_id, product_id=product_id, quantity=quantity)
        db.add(new_item)
        db.commit()
        return f"✅ Added {quantity}x '{prod.name}' to cart."
    except Exception as e:
        db.rollback()
        logger.error(f"add_to_cart failed: {e}")
        return f"❌ Error: {str(e)}"
    finally:
        db.close()


@tool
def remove_from_cart(user_id: int, product_id: int, quantity: int = 1) -> str:
    """Remove product from cart"""
    if database is None:
        return f"✅ Mock: Removed product {product_id}"
    
    db = database.SessionLocal()
    try:
        cart_item = db.query(Cart).filter(
            Cart.product_id == product_id,
            Cart.user_id == user_id
        ).first()
        
        if not cart_item:
            return f"❌ Product {product_id} not in cart."
        
        if quantity >= cart_item.quantity:
            db.delete(cart_item)
            db.commit()
            return f"✅ Removed product {product_id} from cart."
        
        cart_item.quantity -= quantity
        db.commit()
        return f"✅ Reduced quantity by {quantity}. Remaining: {cart_item.quantity}"
    except Exception as e:
        db.rollback()
        logger.error(f"remove_from_cart failed: {e}")
        return f"❌ Error: {str(e)}"
    finally:
        db.close()


@tool
def get_user_cart(user_id: int) -> str:
    """Get cart contents"""
    if database is None:
        return json.dumps({"items": [], "total": 0.0})
    
    db = database.SessionLocal()
    try:
        cart_items = db.query(Cart).options(
            joinedload(Cart.product)
        ).filter(Cart.user_id == user_id).all()
        
        if not cart_items:
            return json.dumps({"items": [], "total": 0.0})
        
        items = []
        total = 0.0
        
        for item in cart_items:
            prod = item.product
            if prod:
                subtotal = float(prod.price) * item.quantity
                total += subtotal
                items.append({
                    "product_id": prod.id,
                    "name": prod.name,
                    "quantity": item.quantity,
                    "price": float(prod.price),
                    "subtotal": subtotal
                })
        
        return json.dumps({"items": items, "total": total})
    except Exception as e:
        logger.error(f"get_user_cart failed: {e}")
        return f"❌ Error: {str(e)}"
    finally:
        db.close()


@tool
def checkout_cart(user_id: int) -> str:
    """Checkout cart"""
    if database is None:
        return "✅ Mock: Checkout successful!"
    
    db = database.SessionLocal()
    try:
        cart_items = db.query(Cart).options(
            joinedload(Cart.product)
        ).filter(Cart.user_id == user_id).all()
        
        if not cart_items:
            return "❌ Cart is empty."
        
        total = sum(float(item.product.price) * item.quantity for item in cart_items)
        
        return f"✅ Checkout successful! Total: ${total:.2f}"
    except Exception as e:
        logger.error(f"checkout_cart failed: {e}")
        return f"❌ Error: {str(e)}"
    finally:
        db.close()


@tool
def create_order(user_id: int) -> str:
    """Create order from cart"""
    if database is None:
        return "✅ Mock: Order created #12345"
    
    db = database.SessionLocal()
    try:
        cart_items = db.query(Cart).filter(Cart.user_id == user_id).all()
        if not cart_items:
            return "❌ Cart is empty."
        
        # Calculate total
        total = 0.0
        for item in cart_items:
            prod = db.query(Product).filter(Product.id == item.product_id).first()
            if prod:
                total += float(prod.price) * item.quantity
        
        # Create order
        user = db.query(User).filter(User.id == user_id).first()
        address = user.address if user else "No address"
        
        order = Orders(
            user_id=user_id,
            address=address,
            total_amount=total,
            status="Pending"
        )
        db.add(order)
        db.flush()
        
        # Add order items
        for item in cart_items:
            prod = db.query(Product).filter(Product.id == item.product_id).first()
            order_item = OrderItem(
                order_id=order.id,
                product_id=item.product_id,
                quantity=item.quantity,
                price=prod.price
            )
            db.add(order_item)
        
        # Clear cart
        db.query(Cart).filter(Cart.user_id == user_id).delete()
        
        db.commit()
        return f"✅ Order #{order.id} created! Total: ${total:.2f}"
    except Exception as e:
        db.rollback()
        logger.error(f"create_order failed: {e}")
        return f"❌ Error: {str(e)}"
    finally:
        db.close()


@tool
def view_orders(user_id: int) -> str:
    """View past orders"""
    if database is None:
        return json.dumps([])
    
    db = database.SessionLocal()
    try:
        orders = db.query(Orders).options(
            joinedload(Orders.items).joinedload(OrderItem.product)
        ).filter(Orders.user_id == user_id).all()
        
        if not orders:
            return json.dumps([])
        
        order_list = []
        for order in orders:
            items = []
            for item in order.items:
                if item.product:
                    items.append({
                        "name": item.product.name,
                        "quantity": item.quantity,
                        "price": float(item.price)
                    })
            
            order_list.append({
                "order_id": order.id,
                "items": items,
                "total": float(order.total_amount),
                "status": order.status
            })
        
        return json.dumps(order_list)
    except Exception as e:
        logger.error(f"view_orders failed: {e}")
        return f"❌ Error: {str(e)}"
    finally:
        db.close()