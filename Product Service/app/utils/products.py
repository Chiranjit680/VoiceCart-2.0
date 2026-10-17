# from sqlalchemy.orm import Session
# from .. import models, schemas


# def add_category(product: models.Product, db: Session) -> schemas.ProductOut:
#     """
#     Adds categories to a product and returns the updated product with its categories.
#     """
#     # categories = [pc.category for pc in product.categories]
#     # return {**product.__dict__, "categories": categories}

#     categories = [schemas.CategoryOut.model_validate(pc.category, from_attributes=True) for pc in product.categories]
#     product_data = {
#         **product.__dict__,
#         "categories": categories
#     }

#     return schemas.ProductOut.model_validate(product_data, from_attributes=True)