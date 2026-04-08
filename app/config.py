from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    data_source: str = "postgres"
    database_url: str = "postgresql://user:password@localhost:5432/coupler_monitor"
    google_sheets_credentials_file: str = "credentials.json"
    google_sheets_spreadsheet_id: str = ""
    google_sheets_worksheet_name: str = "google_ads_data"
    alert_mode: str = "log"
    spend_threshold: float = 1.0

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
