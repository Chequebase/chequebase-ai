from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "Analytics Microservice"
    ACCESS_KEY: str = Field(..., env="ACCESS_KEY")
    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    JWT_SECRET_KEY: str = Field(..., env="JWT_SECRET_KEY")
    MONGO_DB_URI: str = Field(..., env="MONGO_DB_URI")
    MONGO_DB_USER: str = Field(..., env="MONGO_DB_USER")
    MONGO_DB_PASSWORD: str = Field(..., env="MONGO_DB_PASSWORD")
    MONGO_DB_NAME: str = Field(..., env="MONGO_DB_NAME")
    MONGO_DB: str = Field(..., env="MONGO_DB")
    MONGO_DB_COLLECTION_NAME: str = Field(..., env="MONGO_DB_COLLECTION_NAME")
    SEVER_PORT: str = Field(..., env="SEVER_PORT")
    PYTHONPATH: str = Field(..., env="PYTHONPATH")

    
    SERVER_PORT: int = 5001

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def print_settings(self):
        print(f"PROJECT_NAME: {self.PROJECT_NAME}")


settings = Settings()
