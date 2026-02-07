# from .. import database, models, schemas
# from typing import List, Optional
# from sqlalchemy.orm import Session
# from sqlalchemy import or_, and_
# from fastapi import HTTPException, status
# import json

# # TODO fix it: none of the features work
# def filter_products(products: List[schemas.ProductSearchOut],
#                     categories: Optional[List[str]] = None,
#                     dict: Optional[dict] = None
#                     ) -> List[schemas.ProductSearchOut]:
#     """
#     All filtering logic for products.
#     """

#     results = []
#     for product in products:

#         flag: bool = True

#         for cat in categories or []:
#             if cat not in [category.name for category in product.categories]:
#                 flag = False
#                 break

#         description = product.specs or ""
#         # if isinstance(description, str):
#         #     try:
#         #         description = json.loads(description.lower())
#         #     except Exception:
#         #         description = {}
#         # elif not isinstance(description, dict):
#         #     description = {}

#         for key, value in (dict or {}).items():
#             print(f"Checking {key} with value {value} for product {product.name}")
#             if key.endswith("_low") and key[:-4] in product.model_dump():
#                 if product.model_dump()[key[:-4]] < value:
#                     flag = False
#                     break
#             elif key.endswith("_high") and key[:-5] in product.model_dump():
#                 if product.model_dump()[key[:-5]] > value:
#                     flag = False
#                     break
#             elif key.endswith("_exact") and key[:-7] in product.model_dump():
#                 if product.model_dump()[key[:-7]] != value:
#                     flag = False
#                     break
#             elif key.endswith("_contains") and key[:-9] in product.model_dump():
#                 if value not in product.model_dump()[key[:-9]]:
#                     flag = False
#                     break

#             elif key.endswith("_low") and key[:-4] in description.keys():
#                 if float(description[key[:-4]]) < value:
#                     flag = False
#                     break
#             elif key.endswith("_high") and key[:-5] in description.keys():
#                 if float(description[key[:-5]]) > value:
#                     flag = False
#                     break
#             elif key.endswith("_exact") and key[:-7] in description.keys():
#                 if description[key[:-7]] != value:
#                     flag = False
#                     break
#             elif key.endswith("_contains") and key[:-9] in description.keys():
#                 if value not in description[key[:-9]]:
#                     flag = False
#                     break

#         if flag:
#             results.append(product)
#     return results
                
from sqlalchemy.orm import Query
from sqlalchemy import and_, cast, Float, String, type_coerce
from .. import models

def filter_products(query: Query, 
                    categories: list[str] | None = None, 
                    filters: dict | None = None) -> Query:
    """
    Applies filters directly to the SQLAlchemy Query object.
    This prevents fetching unnecessary rows from the database.
    """
    
    # 1. Category Filter
    # Since Product <-> Category is Many-to-Many, we join the association tables
    if categories:
        query = query.join(models.Product.categories)\
                     .join(models.ProductCategory.category)\
                     .filter(models.Category.name.in_(categories))\
                     .distinct()

    if not filters:
        return query

    # 2. Dynamic Attribute Filtering
    conditions = []
    
    for key, value in filters.items():
        # A. Determine operation (low, high, exact, contains)
        field_name = key
        op = "exact"
        
        if key.endswith("_low"):
            field_name, op = key[:-4], "low"
        elif key.endswith("_high"):
            field_name, op = key[:-5], "high"
        elif key.endswith("_exact"):
            field_name, op = key[:-7], "exact"
        elif key.endswith("_contains"):
            field_name, op = key[:-9], "contains"

        # B. Filter against standard columns (price, stock, etc.)
        if hasattr(models.Product, field_name):
            column = getattr(models.Product, field_name)
            
            if op == "low":
                conditions.append(column < value)
            elif op == "high":
                conditions.append(column > value)
            elif op == "exact":
                conditions.append(column == value)
            elif op == "contains":
                # ilike provides case-insensitive search
                conditions.append(column.ilike(f"%{value}%"))

        # C. Filter against JSON 'specs' column
        # Note: 'specs' is defined as JSON in your models.py
        else:
            # We treat the JSON field lookup differently depending on the DB type.
            # This implementation assumes standard SQLAlchemy JSON access.
            
            # Access the JSON key
            json_val = models.Product.specs[field_name]

            if op == "exact":
                # Cast to string for safe comparison (handling numbers stored as strings)
                conditions.append(cast(json_val, String) == str(value))
            elif op == "contains":
                 conditions.append(cast(json_val, String).ilike(f"%{value}%"))
            elif op in ["low", "high"]:
                try:
                    # Cast to Float for numeric comparison inside JSON
                    # NOTE: This works best in PostgreSQL. SQLite JSON support varies.
                    num_val = cast(json_val, Float)
                    if op == "low": conditions.append(num_val < float(value))
                    if op == "high": conditions.append(num_val > float(value))
                except Exception:
                    # If casting fails, we ignore this filter to prevent crashes
                    pass

    if conditions:
        query = query.filter(and_(*conditions))

    return query