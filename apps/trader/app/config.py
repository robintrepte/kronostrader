from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"
_LOCAL_ENV = Path(__file__).resolve().parents[1] / ".env"
_ENV_FILES = tuple(
    str(p) for p in (_ROOT_ENV, _LOCAL_ENV) if p.is_file()
) or (".env",)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_paper: bool = True
    alpaca_live: bool = False

    trade_symbols: str = "AAPL,MSFT,NVDA"
    trade_interval_seconds: int = 60
    bar_timeframe: str = "5Min"
    lookback_bars: int = 512
    pred_len: int = 24
    dry_run: bool = True
    strategy: str = "forecast_momentum"
    signal_threshold_pct: float = 0.5

    max_position_size: float = 1000.0
    max_portfolio_exposure: float = 5000.0
    stop_loss_pct: float = 2.0

    database_url: str = "postgresql+asyncpg://kronos:kronos@localhost:5432/kronos"
    redis_url: str = "redis://localhost:6379/0"
    inference_url: str = "http://localhost:8000"

    trader_api_host: str = "0.0.0.0"
    trader_api_port: int = 8001
    redis_channel: str = "kronos.events"
    log_level: str = "INFO"

    mock_market_data: bool = False

    @property
    def symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.trade_symbols.split(",") if s.strip()]

    @property
    def live_trading_enabled(self) -> bool:
        """Live trading only when explicitly requested AND paper is disabled."""
        return self.alpaca_live is True and self.alpaca_paper is False

    @property
    def use_paper(self) -> bool:
        return not self.live_trading_enabled


@lru_cache
def get_settings() -> Settings:
    return Settings()
