from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Date, Table
from sqlalchemy.orm import declarative_base, Mapped, mapped_column, relationship
from datetime import datetime, date

Base = declarative_base()

servicio_colaborador = Table(
    "servicio_colaborador",
    Base.metadata,
    Column("servicio_id", Integer, ForeignKey("servicios.id_servicio"), primary_key=True),
    Column("usuario_id", String, ForeignKey("usuarios.slack_user_id"), primary_key=True),
)

class Usuario(Base):
    __tablename__ = "usuarios"
    slack_user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    servicios_creados: Mapped[list["Servicio"]] = relationship(back_populates="creador")
    servicios_asignados: Mapped[list["Servicio"]] = relationship(secondary=servicio_colaborador, back_populates="colaboradores")
    viaticos_registrados: Mapped[list["Viatico"]] = relationship(back_populates="usuario")

class Cliente(Base):
    __tablename__ = "clientes"
    id_cliente: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True)

class Servicio(Base):
    __tablename__ = "servicios"
    id_servicio: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    creador_id: Mapped[str] = mapped_column(ForeignKey("usuarios.slack_user_id"))
    
    cliente: Mapped[str] = mapped_column(String(100)) 
    estado_ve: Mapped[str] = mapped_column(String(50)) 
    ciudad: Mapped[str] = mapped_column(String(50))    
    fecha_servicio: Mapped[date] = mapped_column(Date) # NUEVO: FECHA ELEGIDA POR EL USUARIO
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    creador: Mapped["Usuario"] = relationship(back_populates="servicios_creados")
    colaboradores: Mapped[list["Usuario"]] = relationship(secondary=servicio_colaborador, back_populates="servicios_asignados")
    viaticos: Mapped[list["Viatico"]] = relationship(back_populates="servicio")
    equipos: Mapped[list["EquipoAsignado"]] = relationship(back_populates="servicio", cascade="all, delete-orphan")

# NUEVA TABLA: 1 TICKET -> MUCHOS EQUIPOS
class EquipoAsignado(Base):
    __tablename__ = "equipos_asignados"
    id_equipo: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_servicio: Mapped[int] = mapped_column(ForeignKey("servicios.id_servicio"))
    
    tipo_equipo: Mapped[str] = mapped_column(String(100))
    marca: Mapped[str] = mapped_column(String(50), nullable=True)
    modelo: Mapped[str] = mapped_column(String(50), nullable=True)
    serial: Mapped[str] = mapped_column(String(50), nullable=True)
    
    servicio: Mapped["Servicio"] = relationship(back_populates="equipos")

class Viatico(Base):
    __tablename__ = "viaticos"
    id_viatico: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slack_user_id: Mapped[str] = mapped_column(ForeignKey("usuarios.slack_user_id"))
    id_servicio: Mapped[int] = mapped_column(ForeignKey("servicios.id_servicio"))
    
    categoria_gasto: Mapped[str] = mapped_column(String(50)) 
    moneda_ingreso: Mapped[str] = mapped_column(String(5))
    monto_ingresado: Mapped[float] = mapped_column(Float)
    tasa_bcv_dia: Mapped[float] = mapped_column(Float)
    
    monto_usd_calculado: Mapped[float] = mapped_column(Float)
    monto_bs_calculado: Mapped[float] = mapped_column(Float)
    fecha_gasto: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    usuario: Mapped["Usuario"] = relationship(back_populates="viaticos_registrados")
    servicio: Mapped["Servicio"] = relationship(back_populates="viaticos")