from cryptography.fernet import Fernet
from bot.config import ENCRYPTION_KEY

fernet = Fernet(ENCRYPTION_KEY.encode())

def encrypt_caldav_password(password: str) -> str:
    return fernet.encrypt(password.encode()).decode()

def decrypt_caldav_password(encrypted_password: str) -> str:
    return fernet.decrypt(encrypted_password.encode()).decode()