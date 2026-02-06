from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List
from .. import models, schemas, oauth2, database
from . import orders

router = APIRouter(prefix="/cart", tags=["cart"])

@router.get("/", response_model=List[schemas.CartOut])
def get_cart(db: Session = Depends(database.get_db), current_user: int = Depends(oauth2.get_current_user)):
    # Optimized: Load product details with the cart item
    cart_items = db.query(models.Cart)\
        .options(joinedload(models.Cart.product))\
        .filter(models.Cart.user_id == current_user.id)\
        .all()
    
    if not cart_items:
        raise HTTPException(status_code=404, detail="Cart is empty")
    return cart_items

@router.get("/cost", response_model=float)
def get_cart_cost(db: Session = Depends(database.get_db), current_user: int = Depends(oauth2.get_current_user)):
    # Optimized: Join Product table to get prices in one go
    results = db.query(models.Cart.quantity, models.Product.price)\
                .join(models.Product, models.Cart.product_id == models.Product.id)\
                .filter(models.Cart.user_id == current_user.id)\
                .all()
    
    if not results:
        return 0.0
        
    return sum(item.quantity * float(item.price) for item in results)

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.CartOut)
def add_to_cart(cart_item: schemas.CartCreate, db: Session = Depends(database.get_db), current_user: int = Depends(oauth2.get_current_user)):
    # 1. Check Product & Stock
    product = db.query(models.Product).filter(models.Product.id == cart_item.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.stock < cart_item.quantity:
        raise HTTPException(status_code=400, detail="Insufficient stock")

    # 2. Check Existing
    existing = db.query(models.Cart).filter(
        models.Cart.product_id == cart_item.product_id,
        models.Cart.user_id == current_user.id
    ).first()

    if existing:
        existing.quantity += cart_item.quantity
        db.commit()
        db.refresh(existing)
        return existing
    
    # 3. Create New
    new_item = models.Cart(**cart_item.model_dump(), user_id=current_user.id)
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    
    # Reload with relationships for schema
    return db.query(models.Cart).options(joinedload(models.Cart.product)).filter(models.Cart.product_id == cart_item.product_id, models.Cart.user_id == current_user.id).first()

# ... (Checkout and Clear Cart logic remains similar to your original, just ensure imports match)
@router.post("/checkout", status_code=status.HTTP_200_OK, response_model=schemas.OrderOut)
def checkout(address: str = None, db: Session = Depends(database.get_db), current_user: int = Depends(oauth2.get_current_user)):
    # Reuse the logic, but call the optimized get_cart_cost
    if not address:
        address = current_user.address
    if not address:
        raise HTTPException(status_code=400, detail="Address required")

    total = get_cart_cost(db, current_user)
    if total == 0:
        raise HTTPException(status_code=400, detail="Cart empty")
        
    # Call orders router logic (or duplicated here)
    return orders.create_order(address=address, total_amount=total, db=db, current_user=current_user)

@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_product_from_cart(
    product_id: int, 
    db: Session = Depends(database.get_db), 
    current_user: int = Depends(oauth2.get_current_user)
):
    cart_item = db.query(models.Cart).filter(
        models.Cart.product_id == product_id, 
        models.Cart.user_id == current_user.id
    ).first()
    
    if not cart_item:
        raise HTTPException(status_code=404, detail="Item not found in cart")
    
    db.delete(cart_item)
    db.commit()
    return

@router.patch("/{product_id}", response_model=schemas.CartOut)
def update_cart_item(
    product_id: int, 
    val: schemas.QuantityUpdate, 
    db: Session = Depends(database.get_db), 
    current_user: int = Depends(oauth2.get_current_user)
):
    cart_item = db.query(models.Cart).filter(
        models.Cart.product_id == product_id, 
        models.Cart.user_id == current_user.id
    ).first()
    
    if not cart_item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    if val.quantity <= 0:
        # Auto-remove if quantity is 0 or less
        db.delete(cart_item)
        db.commit()
        raise HTTPException(status_code=204, detail="Item removed")

    # Check Stock
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if product.stock < val.quantity:
        raise HTTPException(status_code=400, detail="Insufficient stock")

    cart_item.quantity = val.quantity
    db.commit()
    db.refresh(cart_item)
    
    # Reload for schema (ProductOutLite)
    return db.query(models.Cart).options(joinedload(models.Cart.product)).filter(models.Cart.product_id == product_id, models.Cart.user_id == current_user.id).first()

@router.delete("/clear", status_code=status.HTTP_204_NO_CONTENT)
def clear_cart(db: Session = Depends(database.get_db), current_user: int = Depends(oauth2.get_current_user)):
    # Standard SQL Delete is faster than looping
    db.query(models.Cart).filter(models.Cart.user_id == current_user.id).delete()
    db.commit()
    return

# from typing import List, Optional
# from fastapi import APIRouter, Depends, HTTPException, status
# from sqlalchemy.orm import Session
# from .. import models, schemas, oauth2, database
# from . import orders
# from ..utils import products as product_utils

# router = APIRouter(
#     prefix="/cart",
#     tags=["cart"],
# )

# @router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.CartOut)
# def add_to_cart(cart_item: schemas.CartCreate, db: Session = Depends(database.get_db), current_user: int = Depends(oauth2.get_current_user)):
#     """
#     Add a product to the user's cart. 
#     If the product already exists in the cart, update the quantity.
#     If the product does not exist in the cart, create a new cart item.
#     Raises HTTPException if the product is not found or if the quantity is invalid.
#     Raises HTTPException if the product is out of stock.
#     """

#     # Check if the product exists
#     product = db.query(models.Product).filter(models.Product.id == cart_item.product_id).first()
#     if not product:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    
#     # Check if the requested quantity is valid
#     if cart_item.quantity <= 0:
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quantity must be greater than zero")
#     if product.stock < cart_item.quantity:
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not enough stock for the requested quantity")
    
#     # Check if the product already exists in the user's cart
#     existing_item = db.query(models.Cart).filter(
#         models.Cart.product_id == cart_item.product_id,
#         models.Cart.user_id == current_user.id
#     ).first()

#     if existing_item:
#         # If the product already exists in the cart, update the quantity
#         existing_item.quantity += cart_item.quantity
#         db.commit()
#         db.refresh(existing_item)
#         return existing_item

#     # If the product does not exist in the cart, create a new cart item
#     new_cart_item = models.Cart(**cart_item.model_dump(), user_id=current_user.id)
#     db.add(new_cart_item)
#     db.commit()
#     db.refresh(new_cart_item)
#     return new_cart_item

# @router.get("/", response_model=List[schemas.CartOut])
# def get_cart(db: Session = Depends(database.get_db), current_user: int = Depends(oauth2.get_current_user)):
#     """
#     Retrieve all items in the user's cart.
#     Raises HTTPException if the cart is empty.
#     """
#     cart_items = db.query(models.Cart).filter(models.Cart.user_id == current_user.id).all()
#     if not cart_items:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart is empty")
#     return cart_items

# @router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
# def remove_product_from_cart(product_id: int, db: Session = Depends(database.get_db), current_user: int = Depends(oauth2.get_current_user)):
#     """
#     Remove a product from the user's cart by product_id.
#     Raises HTTPException if the cart item is not found.
#     """
#     cart_item = db.query(models.Cart).filter(models.Cart.product_id == product_id, models.Cart.user_id == current_user.id).first()
#     if not cart_item:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")
    
#     db.delete(cart_item)
#     db.commit()
#     return {"detail": "Product removed from cart"}

# @router.patch("/{product_id}", response_model=schemas.CartOut)
# def update_cart_item(product_id: int, val: schemas.QuantityUpdate, db: Session = Depends(database.get_db), current_user: int = Depends(oauth2.get_current_user)):
#     """
#     Update the quantity of a product in the user's cart.
#     If the product does not exist in the cart, raises HTTPException.
#     """
#     existing_item = db.query(models.Cart).filter(models.Cart.product_id == product_id, models.Cart.user_id == current_user.id).first()
    
#     if not existing_item:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")
    
#     # Update the quantity of the existing cart item
#     existing_item.quantity = val.quantity
#     db.commit()
#     db.refresh(existing_item)
#     return existing_item

# @router.get("/cost", response_model=float)
# def get_cart_cost(db: Session = Depends(database.get_db), current_user: int = Depends(oauth2.get_current_user)):
#     """
#     Calculate the total cost of items in the user's cart.
#     Returns zero HTTPException if the cart is empty.
#     """
#     cart_items = db.query(models.Cart).filter(models.Cart.user_id == current_user.id).all()
#     if not cart_items:
#         return 0.0      
#     total_cost = 0.0
#     for item in cart_items:
#         product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
#         if product:
#             total_cost += float(product.price) * item.quantity
#         else:
#             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product with id {item.product_id} not found")
    
#     return total_cost

# # dummy checkout endpoint
# @router.post("/checkout", status_code=status.HTTP_200_OK, response_model=schemas.OrderOut)
# def checkout(address: Optional[str] = None, db: Session = Depends(database.get_db), current_user: int = Depends(oauth2.get_current_user)):
#     """
#     Checkout the user's cart, process payment, and create an order.
#     Raises HTTPException if the cart is empty or if there is not enough stock for any product
#     Calculates the total amount of the cart and clears the cart after checkout.
#     Checks if the user has an address, if not, uses the user's default address.
#     Raises HTTPException if the address is not provided and no default address is set.
#     Creates an order with the specified details and returns the order details.
#     Raises HTTPException if the order creation fails.
#     Stock is reduced for each product in the cart in create_order function.
#     """
#     cart_items = db.query(models.Cart).filter(models.Cart.user_id == current_user.id).all()
#     if not cart_items:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart is empty")
    
#     for item in cart_items:
#         product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
#         if not product:
#             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product with id {item.product_id} not found")
        
#         if product.stock < item.quantity:
#             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Not enough stock for product {item.product_id}")
        
#     total_amount = get_cart_cost(db, current_user)

#     if address is None:
#         address = current_user.address
#     if not address:
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Address is required for checkout")
    
#     # Here you would typically process the payment and create an order
#     # TODO: Implement payment processing logic
#     # For now, we will just clear the cart

#     order = schemas.OrderCreate(address=address, total_amount = total_amount)
    
#     created_order = orders.create_order(address = address, total_amount=total_amount, db = db, current_user= current_user)
    
#     db.commit()
#     # return {"detail": "Checkout successful, cart cleared"}
#     return created_order

# @router.delete("/clear", status_code=status.HTTP_204_NO_CONTENT)
# def clear_cart(db: Session = Depends(database.get_db), current_user: int = Depends(oauth2.get_current_user)):
#     """
#     Delete all items in the user's cart.
#     Raises HTTPException if the cart is already empty.
#     """
#     cart_items = db.query(models.Cart).filter(models.Cart.user_id == current_user.id).all()
#     if not cart_items:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart is already empty")
    
#     for item in cart_items:
#         db.delete(item)
    
#     db.commit()
#     return {"detail": "Cart cleared successfully"} 