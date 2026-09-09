import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Python buscará la variable DATABASE_URL en la caja fuerte de Render
URL_BASE_DATOS = os.getenv("DATABASE_URL")

if not URL_BASE_DATOS:
    raise ValueError("⚠️ ERROR CRÍTICO: No se encontró la variable DATABASE_URL.")

# --- AQUÍ ESTÁ EL CAMBIO ---
# Agregamos los escudos preventivos directamente al motor de la base de datos
engine = create_engine(
    URL_BASE_DATOS,
    pool_pre_ping=True,  # Verifica que Neon no esté dormido antes de consultar
    pool_recycle=300     # Recicla la conexión cada 5 minutos de forma invisible
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    from models import Base
    Base.metadata.create_all(bind=engine)
