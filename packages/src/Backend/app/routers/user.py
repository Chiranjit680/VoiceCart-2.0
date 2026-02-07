from fastapi.security import OAuth2PasswordRequestForm
from .. import models, schemas, oauth2, database
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..utils import hashing

router = APIRouter(
    prefix="/user",
    tags=["user"],
)

@router.post("/register", status_code = status.HTTP_201_CREATED, response_model=schemas.UserOut)
def register_user(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    """
    Register a new user.
    This function checks if the user already exists by email or phone number.
    If the user exists, it raises a 400 error. If not, it hashes the password,
    creates a new user in the database, and returns the created user.
    Raises HTTPException if the user already exists.
    Raises HTTPException if the email or phone number is already registered.
    """

    # Check if the user already exists by email or phone number
    existing_user = db.query(models.User).filter(
        (models.User.email == user.email) | (models.User.phone == user.phone)
    ).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User with this email or phone number already exists")

    # Hash the password
    hashed_password = hashing.hash(user.password)
    user.password = hashed_password

    new_user = models.User(**user.model_dump())
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user

@router.get("/{id}", response_model=schemas.UserOut)
def get_user(id: int, db: Session = Depends(database.get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
    """
    Retrieve a user by their ID.
    This function fetches a user from the database by their ID.
    If the user exists, it returns the user details.
    If the user does not exist, it raises a 404 error.
    """
    user = db.query(models.User).filter(models.User.id == id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user

@router.post("/login", response_model=schemas.Token)
def login(user_credentials: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    """
    Login a user with email or phone number and password.
    This function checks if the user exists by email or phone number.
    If the user exists, it verifies the password. If the credentials are valid,
    it generates an access token and returns it.
    Raises HTTPException if the user does not exist or if the password is incorrect.
    """
    user = db.query(models.User).filter(models.User.email == user_credentials.username).first()
    if not user:
        user = db.query(models.User).filter(models.User.phone == user_credentials.username).first()
    
    if not user or not hashing.verify(user_credentials.password, user.password):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid credentials")
    
    access_token = oauth2.create_access_token(data={"user_id": user.id})
    return {"access_token": access_token, "token_type": "bearer"}