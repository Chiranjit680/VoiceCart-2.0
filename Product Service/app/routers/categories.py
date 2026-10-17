from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List
from .. import models, schemas, database, oauth2

router = APIRouter(prefix="/categories", tags=["categories"])

@router.get("/", response_model=List[schemas.CategoryOut])
def get_all_categories(db: Session = Depends(database.get_db)):
    # Optimized: Eager load children to prevent recursion queries
    categories = db.query(models.Category)\
        .options(joinedload(models.Category.children))\
        .filter(models.Category.parent_id == None)\
        .all()
    # Note: This returns only ROOT categories, and Pydantic will nest the children.
    # If you want a flat list of ALL categories, remove the .filter() line.
    return categories

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.CategoryOut)
def create_category(
    category: schemas.CategoryCreate, 
    db: Session = Depends(database.get_db), 
    current_user: schemas.UserOut = Depends(oauth2.get_current_user)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if db.query(models.Category).filter(models.Category.name == category.name).first():
        raise HTTPException(status_code=400, detail="Category exists")
       
    new_category = models.Category(**category.model_dump())
    db.add(new_category)
    db.commit()
    db.refresh(new_category)
    return new_category

# from fastapi import APIRouter, Depends, HTTPException, status
# from sqlalchemy.orm import Session
# from typing import List, Optional
# from .. import models, schemas, database, oauth2

# router = APIRouter(
#     prefix="/categories",
#     tags=["categories"]
# )


# @router.get("/", response_model=List[schemas.CategoryOut])
# def get_all_categories(db: Session = Depends(database.get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
#     """
#     Retrieve all product categories.
#     This function fetches all categories from the database.
#     """
#     categories = db.query(models.Category).all()
#     return categories

# @router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.CategoryOut)
# def create_category(category: schemas.CategoryCreate, db: Session = Depends(database.get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
#     """
#     Create a new product category.
#     This function allows an admin user to create a new category.
#     It checks if the user is an admin before allowing category creation.
#     If the category already exists, it raises a 400 error.
#     """
#     # Check if the user is an admin
#     if not current_user.is_admin:
#         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to create categories")
    
#     if db.query(models.Category).filter(models.Category.name == category.name).first():
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category already exists")
       
#     new_category = models.Category(**category.model_dump())
#     db.add(new_category)
#     db.commit()
#     db.refresh(new_category)
#     return new_category