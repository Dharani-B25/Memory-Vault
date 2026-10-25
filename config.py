import os
class Config:
    ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").lower()
    DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
    SECRET_KEY = os.environ.get("SECRET_KEY")

    if not SECRET_KEY:
        if ENVIRONMENT == "production":
            raise RuntimeError("Set SECRET_KEY to a unique, random value in production.")
        SECRET_KEY = "memoryvault-development-key-change-before-deployment"

    DATABASE_URL = os.environ.get("DATABASE_URL")
    if ENVIRONMENT == "production" and not DATABASE_URL:
        raise RuntimeError("Set DATABASE_URL to a persistent production database.")
    SQLALCHEMY_DATABASE_URI = DATABASE_URL or "sqlite:///memoryvault.db"
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            "postgres://", "postgresql+psycopg://", 1
        )
    elif SQLALCHEMY_DATABASE_URI.startswith("postgresql://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = ENVIRONMENT == "production"
