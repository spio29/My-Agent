import os
from dataclasses import dataclass


@dataclass
class Settings:
    # Redis configuration
    REDIS_HOST: str = os.getenv("REDIS_HOST", "127.0.0.1")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB: int = int(os.getenv("REDIS_DB", 0))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")

    # API configuration
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", 8000))

    # Worker configuration
    WORKER_CONCURRENCY: int = int(os.getenv("WORKER_CONCURRENCY", 5))

    # Scheduler pressure-control configuration
    SCHEDULER_MAX_DISPATCH_PER_TICK: int = int(os.getenv("SCHEDULER_MAX_DISPATCH_PER_TICK", 80))
    SCHEDULER_PRESSURE_DEPTH_HIGH: int = int(os.getenv("SCHEDULER_PRESSURE_DEPTH_HIGH", 300))
    SCHEDULER_PRESSURE_DEPTH_LOW: int = int(os.getenv("SCHEDULER_PRESSURE_DEPTH_LOW", 180))

    # Private AI Factory (Phase 21)
    AI_NODE_URL: str = os.getenv("AI_NODE_URL", "") # IP VPS 2
    AI_NODE_SECRET: str = os.getenv("AI_NODE_SECRET", "factory-secret-123")

    # Local AI Brain (Phase 27)
    LOCAL_AI_URL: str = os.getenv("LOCAL_AI_URL", "http://localhost:11434/v1")
    PLANNER_AI_MODEL: str = os.getenv("PLANNER_AI_MODEL", "llama3")


settings = Settings()
