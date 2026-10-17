from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List
from .. import models, schemas, database, oauth2

router = APIRouter(prefix="/reviews", tags=["review"])

@router.get("/product/{product_id}", response_model=List[schemas.ReviewOut])
def get_reviews_by_product(product_id: int, db: Session = Depends(database.get_db)):
    # Optimized: Loads Review + User + Product in 1 query
    reviews = db.query(models.Reviews)\
        .options(joinedload(models.Reviews.user), joinedload(models.Reviews.product))\
        .filter(models.Reviews.product_id == product_id)\
        .all()
    
    if not reviews:
        # Returning empty list is often better than 404 for lists, but 404 is fine too
        raise HTTPException(status_code=404, detail="No reviews found")
    return reviews

@router.get("/user/{user_id}", response_model=List[schemas.ReviewOut])
def get_reviews_by_user(user_id: int, db: Session = Depends(database.get_db)):
    reviews = db.query(models.Reviews)\
        .options(joinedload(models.Reviews.user), joinedload(models.Reviews.product))\
        .filter(models.Reviews.user_id == user_id)\
        .all()
        
    if not reviews:
        raise HTTPException(status_code=404, detail="No reviews found")
    return reviews

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.ReviewOut)
def create_review(
    review: schemas.ReviewCreate, 
    db: Session = Depends(database.get_db), 
    current_user: schemas.UserOut = Depends(oauth2.get_current_user)
):
    # 1. Check Product Existence
    product = db.query(models.Product).filter(models.Product.id == review.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # 2. Check for Duplicate Review
    existing_review = db.query(models.Reviews).filter(
        models.Reviews.product_id == review.product_id,
        models.Reviews.user_id == current_user.id
    ).first()
    if existing_review:
        raise HTTPException(status_code=400, detail="You have already reviewed this product")

    # 3. Verify Purchase (Must be 'completed')
    # Note: Ensure your 'status' string matches exactly what is in DB (case-sensitive)
    has_purchased = db.query(models.Orders).join(models.OrderItem).filter(
        models.Orders.user_id == current_user.id,
        models.Orders.status == "Delivered", # Changed from 'completed' to match your order update logic
        models.OrderItem.product_id == review.product_id
    ).first()

    if not has_purchased:
        raise HTTPException(status_code=403, detail="You can only review products you have purchased and received")

    # 4. Create Review
    new_review = models.Reviews(**review.model_dump(), user_id=current_user.id)
    db.add(new_review)
    db.commit()
    db.refresh(new_review)

    # Reload with relationships for the schema response
    return db.query(models.Reviews)\
        .options(joinedload(models.Reviews.user), joinedload(models.Reviews.product))\
        .filter(models.Reviews.id == new_review.id)\
        .first()

# ... (Delete and Update can remain as they were in your original code, they are simple single-item ops)

# from .. import models, schemas, database, oauth2
# from fastapi import APIRouter, Depends, HTTPException, status
# from sqlalchemy.orm import Session
# from typing import List

# router = APIRouter(
#     prefix="/reviews",
#     tags=["review"],
# )

# # TODO: update rating of product when a review is created or updated or deleted

# @router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.ReviewOut)
# def create_review(review: schemas.ReviewCreate, db: Session = Depends(database.get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
#     """
#     Create a new review for a product.
#     This function allows a user to create a review for a product. 
#     It checks if the product exists before creating the review.
#     It also checks if the user has already reviewed the product and if the user has purchased the product.
#     If the user has already reviewed the product, it raises a 400 error.
#     If the user has not purchased the product, it raises a 403 error.
#     The review is associated with the current user.
#     If the product does not exist, it raises a 404 error.
#     """
#     # Check if the product exists
#     product = db.query(models.Product).filter(models.Product.id == review.product_id).first()
#     if not product:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
#     # Check if the user has already reviewed this product
#     existing_review = db.query(models.Reviews).filter(
#         models.Reviews.product_id == review.product_id,
#         models.Reviews.user_id == current_user.id
#     ).first()
#     if existing_review:
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You have already reviewed this product")
#     # Validate the rating
#     if review.rating < 1 or review.rating > 5:  # Assuming rating is between 1 and 5
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rating must be between 1 and 5")
    
#     # check if user has ever purchased the product and if it was delivered
#     order_item = db.query(models.OrderItem).join(models.Orders).filter(
#         models.OrderItem.product_id == review.product_id,
#         models.OrderItem.order.has(user_id=current_user.id),
#         models.Orders.status == "completed"
#     ).first()

#     # Create the review
#     new_review = models.Reviews(**review.model_dump(), user_id=current_user.id)
#     db.add(new_review)
#     db.commit()
#     db.refresh(new_review)

#     return new_review

# @router.get("/{id}", response_model=schemas.ReviewOut)
# def get_review(id: int, db: Session = Depends(database.get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
#     """
#     Retrieve a review by its ID.
#     This function fetches a review from the database by its ID.
#     If the review exists, it returns the review details.
#     If the review does not exist, it raises a 404 error.
#     """
#     review = db.query(models.Reviews).filter(models.Reviews.id == id).first()
#     if not review:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    
#     return review

# @router.get("/product/{product_id}", response_model=List[schemas.ReviewOut])
# def get_reviews_by_product(product_id: int, db: Session = Depends(database.get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
#     """
#     Retrieve all reviews for a specific product.
#     This function fetches all reviews associated with a product by its ID.
#     If no reviews are found for the product, it raises a 404 error.
#     If reviews are found, it returns a list of reviews.
#     """
#     reviews = db.query(models.Reviews).filter(models.Reviews.product_id == product_id).all()
#     if not reviews:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No reviews found for this product")
    
#     return reviews

# @router.get("/user/{user_id}", response_model=List[schemas.ReviewOut])
# def get_reviews_by_user(user_id: int, db: Session = Depends(database.get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
#     """
#     Retrieve all reviews made by a specific user.
#     This function fetches all reviews associated with a user by their ID.
#     If no reviews are found for the user, it raises a 404 error.
#     If reviews are found, it returns a list of reviews.
#     """
#     reviews = db.query(models.Reviews).filter(models.Reviews.user_id == user_id).all()
#     if not reviews:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No reviews found for this user")
    
#     return reviews

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(id: int, db: Session = Depends(database.get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
    """
    Delete a review by its ID.
    This function allows a user to delete their own review. 
    It checks if the review exists and if the current user is the owner of the review.
    If the review does not exist, it raises a 404 error.
    If the user does not have permission to delete the review, it raises a 403 error.
    """
    review = db.query(models.Reviews).filter(models.Reviews.id == id).first()
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    if review.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to delete this review")
    
    db.delete(review)
    db.commit()
    return {"detail": "Review deleted successfully"}

@router.put("/{id}", response_model=schemas.ReviewOut)
def update_review(id: int, review: schemas.ReviewCreate, db: Session = Depends(database.get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
    """
    Update an existing review by its ID.
    This function allows a user to update their own review.
    It checks if the review exists and if the current user is the owner of the review.
    If the review does not exist, it raises a 404 error.
    If the user does not have permission to update the review, it raises a 403 error.
    """
    existing_review = db.query(models.Reviews).filter(models.Reviews.id == id).first()
    if not existing_review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    if existing_review.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to update this review")
    
    # Update the review fields
    for key, value in review.model_dump().items():
        setattr(existing_review, key, value)
    
    db.commit()
    db.refresh(existing_review)
    
    return existing_review