from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship
from bot.config import DATABASE_URL
import enum
from datetime import datetime
import os

# Читаем настройки из переменных окружения
DB_USER = os.getenv("DB_USER", "bot_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "BotPass2024")
DB_NAME = os.getenv("DB_NAME", "telegram_bot")
DB_SOCKET = os.getenv("DB_SOCKET", "/var/run/mariadb10.sock")

# Формируем URL для подключения через сокет
DATABASE_URL = f"mysql+aiomysql://{DB_USER}:{DB_PASSWORD}@localhost/{DB_NAME}?unix_socket={DB_SOCKET}"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    pass

class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"

class User(Base):
    __tablename__ = 'users'
    telegram_id = Column(BigInteger, primary_key=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.USER)
    is_approved = Column(Boolean, default=False)
    is_blocked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    calendars = relationship("UserCalendar", back_populates="user")

class UserCalendar(Base):
    __tablename__ = 'user_calendars'
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'))
    caldav_url = Column(String(512))
    caldav_username = Column(String(255))
    caldav_password_encrypted = Column(String(512))
    notification_daily = Column(Boolean, default=False)
    notification_weekly = Column(Boolean, default=False)
    timezone = Column(String(50), default="Europe/Moscow")
    user = relationship("User", back_populates="calendars")

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)