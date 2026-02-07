from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List
from .. import models, schemas, database, oauth2

router = APIRouter(prefix="/product", tags=["product"])

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.ProductOutDetail)
def create_product(
    product: schemas.ProductCreate, 
    categories: List[schemas.CategoryCreate], 
    db: Session = Depends(database.get_db), 
    current_user: schemas.UserOut = Depends(oauth2.get_current_user)
): 
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    
    # 1. Create Product (Without Image)
    # We exclude 'image' because it's no longer in the Product table
    product_data = product.model_dump(exclude={"image"}) 
    new_product = models.Product(**product_data)
    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    # 2. Handle Image (Save to new Table)
    if product.image:
        new_image = models.ProductImage(
            product_id=new_product.id,
            image_data=product.image,
            is_primary=True
        )
        db.add(new_image)

    # 3. Handle Categories
    for category in categories:
        existing_category = db.query(models.Category).filter(models.Category.name == category.name).first()
        if not existing_category:
            existing_category = models.Category(name=category.name)
            db.add(existing_category)
            db.commit()
            db.refresh(existing_category)
        
        # Link Product <-> Category
        product_category = models.ProductCategory(product_id=new_product.id, category_id=existing_category.id)
        db.add(product_category)

    db.commit()
    
    # 4. Return populated object
    # We must reload to get the relationships (categories/images) we just added
    return get_product(new_product.id, db)

@router.get("/{id}", response_model=schemas.ProductOutDetail)
def get_product(id: int, db: Session = Depends(database.get_db)):
    """
    Fetches FULL details including images.
    """
    product = db.query(models.Product)\
        .options(
            joinedload(models.Product.categories).joinedload(models.ProductCategory.category),
            joinedload(models.Product.images)
        )\
        .filter(models.Product.id == id)\
        .first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@router.get("/", response_model=List[schemas.ProductOutLite])
def get_all_products(
    limit: int = 50, 
    skip: int = 0, 
    db: Session = Depends(database.get_db)
):
    """
    Fetches LIGHT details (No massive image blobs) for fast listing.
    """
    products = db.query(models.Product)\
        .options(joinedload(models.Product.categories).joinedload(models.ProductCategory.category))\
        .limit(limit).offset(skip)\
        .all()
    return products

@router.get("/stock/{id}")
def get_product_stock(id: int, db: Session = Depends(database.get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
    product = db.query(models.Product.stock).filter(models.Product.id == id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"stock": product.stock}

@router.patch("/{id}", response_model=schemas.ProductOutDetail)
def update_product(
    id: int, 
    product_update: schemas.ProductUpdate, 
    db: Session = Depends(database.get_db), 
    current_user: schemas.UserOut = Depends(oauth2.get_current_user)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Fetch existing product
    existing_product = db.query(models.Product).filter(models.Product.id == id).first()
    if not existing_product:
        raise HTTPException(status_code=404, detail="Product not found")

    # 1. Update Basic Fields
    # exclude_unset=True is critical to avoid overwriting fields with None
    update_data = product_update.model_dump(exclude_unset=True, exclude={"image"})
    
    for key, value in update_data.items():
        setattr(existing_product, key, value)

    # 2. Update Image (Complex because it's in a different table)
    # Check if 'image' was actually passed in the update request
    # Note: ProductUpdate schema likely needs 'image' field added back if you want to support this
    if getattr(product_update, 'image', None):
        # Find existing primary image
        existing_image = db.query(models.ProductImage).filter(
            models.ProductImage.product_id == id,
            models.ProductImage.is_primary == True
        ).first()

        if existing_image:
            existing_image.image_data = product_update.image
        else:
            new_image = models.ProductImage(product_id=id, image_data=product_update.image, is_primary=True)
            db.add(new_image)

    db.commit()
    db.refresh(existing_product)
    
    # Reload with relationships
    return get_product(id, db)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(id: int, db: Session = Depends(database.get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    product = db.query(models.Product).filter(models.Product.id == id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Cascade delete in models.py (cascade="all, delete-orphan") will handle 
    # deleting the associated Images and Categories automatically.
    db.delete(product)
    db.commit()
    return




# from .. import models, schemas, database, oauth2
# from fastapi import APIRouter, Depends, HTTPException, status
# from sqlalchemy.orm import Session
# from typing import List
# from ..utils import products as product_utils


# router = APIRouter(
#     prefix="/product",
#     tags=["product"],
# )

# @router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.ProductOut)
# def create_product(product: schemas.ProductCreate, categories: List[schemas.CategoryCreate], db: Session = Depends(database.get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)): 
#     """
#     Create a new product with associated categories.
#     This function checks if the user is an admin before allowing product creation.
#     It creates a new product and associates it with the provided categories.
#     If a category does not exist, it creates a new category.
#     """
#     # Check if the user is an admin
#     if not current_user.is_admin:
#         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to create products")
    
#     new_product = models.Product(**product.model_dump())
#     db.add(new_product)
#     db.commit()
#     db.refresh(new_product)

#     for category in categories:
#         # check if the category exists
#         existing_category = db.query(models.Category).filter(models.Category.name == category.name).first()
#         if existing_category:
#             product_category = models.ProductCategory(product_id=new_product.id, category_id=existing_category.id)
#         else:
#             new_category = models.Category(**category.model_dump())
#             db.add(new_category)
#             db.commit()
#             db.refresh(new_category)
#             product_category = models.ProductCategory(product_id=new_product.id, category_id=new_category.id)
#         db.add(product_category)
#     db.commit()

#     db.refresh(new_product)
#     categories = [pc.category for pc in new_product.categories]
#     return product_utils.add_category(new_product, db)

# # I don't think this function associates parent categories with products, so it is not needed.
# @router.get("/{id}", response_model=schemas.ProductOut)
# def get_product(id: int, db: Session = Depends(database.get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
#     """
#     Retrieve a product by its ID.
#     This function fetches a product from the database by its ID and also retrieves its associated categories
#     if the product exists. If the product does not exist, it raises a 404 error.
#     """
#     product = db.query(models.Product).filter(models.Product.id == id).first()
#     if not product:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
#     # fetch categories
#     categories = db.query(models.Category).join(models.ProductCategory).filter(models.ProductCategory.product_id == id).all()
#     # product.categories = categories
#     return product_utils.add_category(product, db)

# @router.get("/stock/{id}")
# def get_product_stock(id: int, db: Session = Depends(database.get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
#     """
#     Retrieve the stock of a product by its ID.
#     This function fetches the stock of a product from the database by its ID.
#     If the product does not exist, it raises a 404 error.
#     It returns the stock quantity of the product.
#     """
#     product = db.query(models.Product).filter(models.Product.id == id).first()
#     if not product:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
#     return {"stock": product.stock}


# @router.get("/", response_model=List[schemas.ProductOut])
# def get_all_products(db: Session = Depends(database.get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)): # TODO: add query parameters for filtering, sorting, and pagination
#     """
#     Retrieve all products.
#     This function fetches all products from the database and retrieves their associated categories.
#     It returns a list of products, each with its categories populated.
#     If no products are found, it returns an empty list.
#     """
#     products = db.query(models.Product).all()
#     res = []
#     for product in products:
#         # fetch categories for each product
#         categories = db.query(models.Category).join(models.ProductCategory).filter(models.ProductCategory.product_id == product.id).all()
#         res.append(product_utils.add_category(product, db))
#     return res

# @router.patch("/{id}", response_model=schemas.ProductOut)
# def update_product(id: int, product: schemas.ProductUpdate, db: Session = Depends(database.get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
#     """
#     Update an existing product by its ID.
#     This function allows an admin user to update the details of a product.
#     It checks if the user is an admin before allowing the update.
#     If the product does not exist, it raises a 404 error.
#     """
#     # Check if the user is an admin
#     if not current_user.is_admin:
#         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to update products")

#     existing_product = db.query(models.Product).filter(models.Product.id == id).first()
#     if not existing_product:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    
#     for key, value in product.model_dump(exclude_unset=True).items():
#         setattr(existing_product, key, value)
    
#     db.commit()
#     db.refresh(existing_product)
    
#     return product_utils.add_category(existing_product, db)

# @router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
# def delete_product(id: int, db: Session = Depends(database.get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
#     """
#     Delete a product by its ID.
#     This function allows an admin user to delete a product from the database.
#     It checks if the user is an admin before allowing the deletion.
#     If the product does not exist, it raises a 404 error.
#     """
#     # Check if the user is an admin
#     if not current_user.is_admin:
#         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to delete products")
    
#     existing_product = db.query(models.Product).filter(models.Product.id == id).first()
#     if not existing_product:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    
#     db.delete(existing_product)
#     db.commit()
    
#     return {"detail": "Product deleted successfully"}