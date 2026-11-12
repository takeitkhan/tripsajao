import os

from cryptography.fernet import Fernet

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
os.environ.setdefault("DATABASE_URL_SYSTEM", "postgresql+asyncpg://u:p@localhost/db")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret")
os.environ.setdefault("API_SECRET_PEPPER", "pepper")
os.environ.setdefault("COOKIE_ENCRYPTION_KEY", Fernet.generate_key().decode())
