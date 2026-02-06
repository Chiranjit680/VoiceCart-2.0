from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, desc, case, cast, String
from typing import List
from .. import models, schemas, database
from ..utils import filter as filter_utils

router = APIRouter(prefix="/search", tags=["search"])

@router.get("/products", response_model=List[schemas.ProductSearchOut])
def search_products(
    query: str,
    filters: dict = None, 
    categories: List[str] = None, 
    db: Session = Depends(database.get_db)
):
    if not query:
        raise HTTPException(status_code=400, detail="Query required")

    # Clean query
    query_str = query.strip()
    words = query_str.split()
    
    # 1. Base Query
    sql_query = db.query(models.Product)

    # 2. Filter: Determine candidates (Must match at least ONE word from the query)
    # We construct a massive OR clause to filter out completely irrelevant items first.
    # This keeps the scoring logic faster.
    match_conditions = []
    for word in words:
        term = f"%{word}%"
        match_conditions.append(models.Product.name.ilike(term))
        match_conditions.append(models.Product.brand_name.ilike(term))
        match_conditions.append(models.Product.description.ilike(term))
        # Optional: Check specs too if you really need deep search (slower)
        # match_conditions.append(cast(models.Product.specs, String).ilike(term))

    sql_query = sql_query.filter(or_(*match_conditions))

    # 3. Apply Utility Filters (Price, Categories, etc.)
    sql_query = filter_utils.filter_products(sql_query, categories, filters)

    # 4. SCORING ALGORITHM (The "Red Shoe" Fix)
    # We sum up the score for EACH word in the query against ALL fields.
    total_score = 0
    
    for word in words:
        term = f"%{word}%"
        
        # Name match = 10 points
        total_score += case((models.Product.name.ilike(term), 10), else_=0)
        
        # Brand match = 6 points
        total_score += case((models.Product.brand_name.ilike(term), 6), else_=0)
        
        # Description match = 2 points
        total_score += case((models.Product.description.ilike(term), 2), else_=0)
        
        # Specs (JSON) match = 2 points
        # We cast JSON to string to search inside it
        total_score += case((cast(models.Product.specs, String).ilike(term), 2), else_=0)

    # 5. Sort by Score (Highest First), then by Popularity (Num Sold)
    sql_query = sql_query.order_by(desc(total_score), desc(models.Product.num_sold))

    # 6. Eager Load & Limit
    results = sql_query.options(
        joinedload(models.Product.categories).joinedload(models.ProductCategory.category)
    ).limit(50).all()

    if not results:
        raise HTTPException(status_code=404, detail="No products found")

    # 7. Map to Schema (Pass the calculated score to the frontend if needed)
    response = []
    
    # We can re-calculate the Python score for the UI 'relevance_score' field 
    # OR strictly trust the order. For display, let's mirror the logic simply.
    q_lower = query_str.lower()
    
    for p in results:
        # Simple python recalculation for the API response field
        # (The DB has already done the heavy lifting of sorting)
        ui_score = 0
        p_txt = (p.name + " " + (p.description or "") + " " + (p.brand_name or "") + " " + str(p.specs or "")).lower()
        
        # Simple frequency count for UI score
        for word in words:
            if word.lower() in p_txt:
                ui_score += 10
        
        p_out = schemas.ProductSearchOut.model_validate(p, from_attributes=True)
        p_out.relevance_score = ui_score
        response.append(p_out)

    return response

# from time import sleep
# from fastapi import APIRouter, Depends, HTTPException
# from sqlalchemy import or_, and_
# from sqlalchemy.orm import Session
# from .. import models, schemas, database, oauth2
# from typing import List
# from ..utils import filter as filter_utils, products as product_utils   

# router = APIRouter(
#     prefix="/search",
#     tags=["search"],
# )

# @router.get("/products", response_model=List[schemas.ProductSearchOut]) # TODO: add filtering and pagination
# def search_products(
#     query: str,
#     filters: dict = None,  # Placeholder for future filters
#     categories: List[str] = None,  # Placeholder for future categories
#     db: Session = Depends(database.get_db),
#     current_user: schemas.UserOut = Depends(oauth2.get_current_user)
# ):
#     if not query:
#         raise HTTPException(status_code=400, detail="Query parameter is required")
    
#     query = query.strip().lower()
#     if not query:
#         raise HTTPException(status_code=400, detail="Query cannot be empty")
    
#     matched_products = []
    
#     for word in query.split():
#         word = word.strip()
#         if not word:
#             continue
        
#         # Search for products matching the word in name, description, or brand_name
#         matched_products = db.query(models.Product).filter(
#             or_(
#                 models.Product.name.ilike(f"%{word}%"),
#                 models.Product.description.ilike(f"%{word}%"),
#                 models.Product.brand_name.ilike(f"%{word}%")
#                 )).all()
        
#         # Matches in categories
#         cat_list = db.query(models.Category).filter(
#             or_(
#                 models.Category.name.ilike(f"%{word}%"),
#                 models.Category.parent_id.in_(
#                     db.query(models.Category.id).filter(models.Category.name.ilike(f"%{word}%"))
#                 )
#             )
#         ).all()

#         # list of products in matched categories
#         cat_prod_list = db.query(models.ProductCategory).filter(
#             models.ProductCategory.category_id.in_([cat.id for cat in cat_list])
#         ).all()

#         # Extend matched products with those in matched categories
#         matched_products.extend(
#             db.query(models.Product).filter(
#                 models.Product.id.in_([pc.product_id for pc in cat_prod_list])
#             ).all()
#         )

#     # Remove duplicates while preserving order
#     matched_products = list({product.id: product for product in matched_products}.values()) # dict comprehension to remove duplicates
    
#     if not matched_products:
#         raise HTTPException(status_code=404, detail="No products found matching the query")
    
#     results: List[schemas.ProductSearchOut] = []

#     for word in query.split():
#         word = word.strip()
#         if not word:
#             continue

#         for product in matched_products:
#             relevance = 0
#             if word in product.name.lower():
#                 relevance += 10
#             if word in (product.brand_name or "").lower():
#                 relevance += 6
#             if word in str(product.description).lower():
#                 relevance += 2
#             if word in str(product.specs).lower():
#                 relevance += 1
            
#             # Check if the word matches any category name
#             # TODO check here
#             product_data = product_utils.add_category(product, db)


#             if any(word in cat.name.lower() for cat in product_data.categories):
#                 relevance += 4

#             # results.append(schemas.ProductSearchOut(**product_data, relevance_score=relevance))
#             results.append(schemas.ProductSearchOut(
#                 **product_data.model_dump(),
#                 relevance_score=relevance
#             ))

#     # Apply filters if provided
#     if filters or categories:
#         results = filter_utils.filter_products(results, categories=categories, dict=filters)

#     results.sort(key=lambda x: (x.relevance_score, x.num_sold), reverse=True)
#     return results