from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

SQL_ALCHEMY_DATABASE_URL = settings.database_url

# Optimized Engine with Pooling
engine = create_engine(
    SQL_ALCHEMY_DATABASE_URL, 
    echo=False,  # Set to False for production performance
    pool_size=10,       # Baseline open connections
    max_overflow=20,    # Spikes allowed
    pool_timeout=30,    # Wait time before error
    pool_recycle=1800   # Recycle connections every 30 mins
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# from sqlalchemy import create_engine
# from sqlalchemy.ext.declarative import declarative_base
# from sqlalchemy.orm import sessionmaker
# from .config import settings
# from dotenv import load_dotenv
# load_dotenv()

# SQL_ALCHEMY_DATABASE_URL= settings.database_url

# engine = create_engine(SQL_ALCHEMY_DATABASE_URL, echo=True)

# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base = declarative_base()

# # dependency
# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()