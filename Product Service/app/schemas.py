from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, EmailStr, ConfigDict, Field, field_validator
from datetime import datetime

# --- Token ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    id: int

# --- Categories ---
class CategoryCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None

class CategoryOut(BaseModel):
    id: int
    name: str
    parent_id: Optional[int] = None
    
    model_config = ConfigDict(from_attributes=True)

# --- Product Images ---
class ProductImageOut(BaseModel):
    id: int
    product_id: int
    model_config = ConfigDict(from_attributes=True)

# --- Products ---
class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    specs: Optional[Dict[str, Any]] = None 
    price: float
    for_sale: bool = True
    stock: int = 0
    brand_name: Optional[str] = None

class ProductCreate(ProductBase):
    image: Optional[bytes] = None 

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    specs: Optional[Dict[str, Any]] = None
    price: Optional[float] = None
    for_sale: Optional[bool] = None
    stock: Optional[int] = None
    brand_name: Optional[str] = None
    image: Optional[bytes] = None 

# LITE Schema
class ProductOutLite(ProductBase):
    id: int
    created_at: datetime
    avg_rating: float
    num_reviews: int
    num_sold: int
    has_image: bool = False  # the photo itself is served by GET /product/{id}/image
    categories: List[CategoryOut] = []
    
    model_config = ConfigDict(from_attributes=True)

    # --- THE FIX IS HERE ---
    @field_validator('categories', mode='before')
    @classmethod
    def flatten_categories(cls, v: Any):
        """
        Extracts the actual Category object from the ProductCategory association object.
        """
        if not v:
            return []
        
        # If the item is the association object (has 'category' attribute), unpack it.
        # We check the first item to determine the type of list.
        first_item = v[0]
        if hasattr(first_item, 'category'):
            return [item.category for item in v]
        
        return v

# DETAIL Schema
class ProductOutDetail(ProductOutLite):
    pass 

class ProductSearchOut(ProductOutLite):
    relevance_score: float

# --- User ---
class UserBase(BaseModel):
    email: EmailStr
    name: str

class UserCreate(UserBase):
    password: str
    phone: Optional[str] = None
    address: Optional[str] = None
    is_admin: Optional[bool] = False

class UserOut(UserBase):
    id: int
    phone: Optional[str] = None
    address: Optional[str] = None
    is_admin: bool
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# --- Cart ---
class CartCreate(BaseModel):
    product_id: int
    quantity: int

class CartOut(BaseModel):
    user_id: int
    product_id: int
    quantity: int
    product: Optional[ProductOutLite] = None

    model_config = ConfigDict(from_attributes=True)

class QuantityUpdate(BaseModel):
    quantity: int

# --- Orders ---
class OrderItemOut(BaseModel):
    product_id: int
    quantity: int
    price: float
    product: Optional[ProductOutLite] = None

    model_config = ConfigDict(from_attributes=True)

class OrderCreate(BaseModel):
    address: str
    total_amount: float

class OrderUpdate(BaseModel):
    status: Optional[str]
    address: Optional[str] = None

class OrderOut(BaseModel):
    id: int
    user_id: int
    address: str
    total_amount: float
    status: str
    created_at: datetime
    items: List[OrderItemOut] = []

    model_config = ConfigDict(from_attributes=True)

# --- Reviews ---
class ReviewCreate(BaseModel):
    product_id: int
    rating: int
    comment: Optional[str] = None

class ReviewOut(BaseModel):
    id: int
    user_id: int
    product_id: int
    rating: int
    comment: Optional[str] = None
    created_at: datetime
    user: Optional[UserOut] = None
    product: Optional[ProductOutLite] = None 
    
    model_config = ConfigDict(from_attributes=True)

# --- Chat ---
class ChatInput(BaseModel):
    input_text: str
    conversation_id: Optional[str] = None

class ChatTurnIn(BaseModel):
    role: Literal["user", "assistant"]
    agent: Optional[str] = Field(default=None, max_length=40)  # which subagent replied
    content: str = Field(min_length=1, max_length=8000)

class ChatTurnsIn(BaseModel):
    messages: List[ChatTurnIn] = Field(min_length=1, max_length=50)

class ChatTurnOut(BaseModel):
    seq: int
    role: str
    agent: Optional[str] = None
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ChatSessionOut(BaseModel):
    id: str
    started_at: datetime
    last_activity_at: datetime
    ended_at: Optional[datetime] = None
    end_reason: Optional[str] = None
    turn_count: int

    model_config = ConfigDict(from_attributes=True)

class ChatSessionDetail(ChatSessionOut):
    turns: List[ChatTurnOut] = []

class ChatSessionOpened(BaseModel):
    id: str
    resumed: bool  # True when this continues a conversation that ended moments ago

class ChatSessionStatus(BaseModel):
    id: str
    ended: bool
    user_id: int  # the verified owner; the agent scopes long-term memory by this, not by what a URL says

class ChatSessionEnd(BaseModel):
    reason: Literal["disconnect", "idle"] = "disconnect"

# from typing import List, Optional, Dict
# from pydantic import BaseModel, EmailStr
# from datetime import datetime

# # --- Token Schemas ---
# class Token(BaseModel):
#     access_token: str
#     token_type: str

# class TokenData(BaseModel):
#     id: int

# # --- User Schemas ---
# class UserCreate(BaseModel):
#     name: str
#     email: EmailStr
#     password: str
#     phone: Optional[str] = None
#     address: Optional[str] = None
#     is_admin: Optional[bool] = False

# class UserOut(BaseModel):
#     id: int
#     name: str
#     email: str
#     phone: Optional[str] = None
#     address: Optional[str] = None
#     is_admin: bool
#     created_at: datetime

#     class Config:
#         orm_mode = True

# class User(UserOut):
#     orders: List["OrderOut"] = []
#     cart: List["CartOut"] = []
#     reviews: List["ReviewOut"] = []

# # --- Product Schemas ---
# class ProductCreate(BaseModel):
#     name: str
#     description: Optional[str] = None
#     specs: Optional[Dict[str, str]] = None  # JSON field
#     price: float
#     for_sale: Optional[bool] = True
#     stock: Optional[int] = 0
#     brand_name: Optional[str] = None
#     image: Optional[bytes] = None 

# class ProductUpdate(BaseModel):
#     name: Optional[str] = "None"
#     description: Optional[str] = None
#     specs: Optional[Dict[str, str]] = None  # JSON field
#     price: Optional[float] = 0.0
#     for_sale: Optional[bool] = True
#     stock: Optional[int] = 0
#     brand_name: Optional[str] = None
#     image: Optional[bytes] = None 

# class ProductOut(BaseModel):
#     id: int
#     name: str
#     description: Optional[str] = None
#     specs: Optional[Dict[str, str]] = None 
#     price: float
#     for_sale: bool
#     stock: int
#     brand_name: Optional[str] = None
#     created_at: datetime
#     categories: List["CategoryOut"] = []
#     avg_rating: float = 0.0
#     num_reviews: int = 0
#     num_sold: int = 0
#     image: Optional[bytes] = None  # Assuming image is stored as bytes

#     class Config:
#         orm_mode = True

# class ProductOutNoCategory(BaseModel):
#     id: int
#     name: str
#     description: Optional[str] = None
#     specs: Optional[Dict[str, str]] = None 
#     price: float
#     for_sale: bool
#     stock: int
#     brand_name: Optional[str] = None
#     created_at: datetime
#     avg_rating: float = 0.0
#     num_reviews: int = 0
#     num_sold: int = 0
#     image: Optional[bytes] = None  # Assuming image is stored as bytes

#     class Config:
#         orm_mode = True

# # --- Category Schemas ---
# class CategoryCreate(BaseModel):
#     name: str
#     parent_id: Optional[int] = None

# class CategoryOut(BaseModel):
#     id: int
#     name: str
#     parent_id: Optional[int] = None
#     children: List["CategoryOut"] = []

#     class Config:
#         orm_mode = True

# # --- ProductCategory Schemas (for many-to-many) ---
# class ProductCategoryCreate(BaseModel):
#     product_id: int
#     category_id: int

# class ProductCategoryOut(BaseModel):
#     product_id: int
#     category_id: int

#     class Config:
#         orm_mode = True

# # --- Cart Schemas ---
# class CartCreate(BaseModel):
#     product_id: int
#     quantity: int

# class CartOut(BaseModel):
#     user_id: int
#     product_id: int
#     quantity: int
#     product: Optional[ProductOutNoCategory] = None

#     class Config:
#         orm_mode = True

# # --- Order Item Schemas ---
# class OrderItemCreate(BaseModel):
#     product_id: int
#     quantity: int
#     price: float

# class OrderItemOut(BaseModel):
#     order_id: int
#     product_id: int
#     quantity: int
#     price: float
#     product: Optional[ProductOutNoCategory] = None

#     class Config:
#         orm_mode = True

# # --- Order Schemas ---
# class OrderCreate(BaseModel):
#     address: str
#     total_amount: float

# class OrderOut(BaseModel):
#     id: int
#     user_id: int
#     address: str
#     total_amount: float
#     status: str
#     created_at: datetime
#     items: List[OrderItemOut] = []

#     class Config:
#         orm_mode = True

# # --- Review Schemas ---
# class ReviewCreate(BaseModel):
#     product_id: int
#     rating: int
#     comment: Optional[str] = None

# class ReviewOut(BaseModel):
#     id: int
#     user_id: int
#     product_id: int
#     rating: int
#     comment: Optional[str] = None
#     created_at: datetime
#     user: Optional[UserOut] = None
#     product: Optional[ProductOut] = None

#     class Config:
#         orm_mode = True

# class ProductSearchOut(ProductOut):
#     relevance_score: float

# # Misc
# class QuantityUpdate(BaseModel):
#     quantity: int

# class OrderUpdate(BaseModel):
#     status: Optional[str]  # e.g., "Pending", "Shipped", "Delivered", "Cancelled"
#     address: Optional[str] = None  # Optional, can be updated later

# # # --- Chat Schemas ---
# # class ChatInput(BaseModel):
# #     input_text: str


# # For forward references (self-referencing models)
# User.update_forward_refs()
# CategoryOut.update_forward_refs()
# OrderOut.update_forward_refs()
# ReviewOut.update_forward_refs()
# ProductOut.update_forward_refs()


# --- Shopper profile ---
PROFILE_MAX_ITEMS = 30
PROFILE_MAX_ITEM_CHARS = 80


def _clean_list(values: List[str]) -> List[str]:
    """Trimmed, no blanks, no repeats (ignoring case), each short enough to be one phrase, and not too many."""
    cleaned, seen = [], set()
    for value in values:
        value = " ".join(str(value).split())
        if not value or value.lower() in seen:
            continue
        if len(value) > PROFILE_MAX_ITEM_CHARS:
            raise ValueError(f"Each entry must be at most {PROFILE_MAX_ITEM_CHARS} characters")
        seen.add(value.lower())
        cleaned.append(value)
    if len(cleaned) > PROFILE_MAX_ITEMS:
        raise ValueError(f"At most {PROFILE_MAX_ITEMS} entries")
    return cleaned


class ProfileIn(BaseModel):
    age: Optional[int] = Field(default=None, ge=0, le=120)
    preferences: List[str] = []
    medical_conditions: List[str] = []

    _clean_preferences = field_validator("preferences")(_clean_list)
    _clean_conditions = field_validator("medical_conditions")(_clean_list)


class ProfileOut(ProfileIn):
    model_config = ConfigDict(from_attributes=True)
