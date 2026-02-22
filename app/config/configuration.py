from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    Excel_Path: str = Field(default="app/Services/data.xlsx", validation_alias="excel_location")
    Admin_Emails: str = Field(default="admin@nit.local", validation_alias="admin_emails")
    Access_Token_Expire: int = Field(default=60, validation_alias="access_token_expire")
    Refresh_Token_Expire: int = Field(default=30, validation_alias="refresh_token_expire")
    Secret_Key: str = Field(default="abcdefg123", validation_alias="secret_key")
    Algorithm: str = Field(default="HS256", validation_alias="algorithm")
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///data.db", validation_alias="database")

settings = Settings()
