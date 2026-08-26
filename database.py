import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Intenta leer la variable desde Render. Si estás probando en tu PC, usa el enlace que copiaste como respaldo (pon tu enlace real aquí abajo)
URL_BASE_DATOS = os.getenv(
    "DATABASE_URL", 
    "postgresql://neondb_owner:npg_NmVnle7z0gGq@ep-snowy-grass-ax8u269h-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
)

# Postgres no necesita el 'check_same_thread' que usaba SQLite
engine = create_engine(URL_BASE_DATOS)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    from models import Base
    # Esto creará las tablas automáticamente en Neon cuando el bot encienda
    Base.metadata.create_all(bind=engine)