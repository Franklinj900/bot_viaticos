import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Python buscará la variable DATABASE_URL en la caja fuerte de Render
URL_BASE_DATOS = os.getenv("DATABASE_URL")

if not URL_BASE_DATOS:
    raise ValueError("⚠️ ERROR CRÍTICO: No se encontró la variable DATABASE_URL.")

engine = create_engine(URL_BASE_DATOS)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    from models import Base
    Base.metadata.create_all(bind=engine)
