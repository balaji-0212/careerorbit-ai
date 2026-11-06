"""Settings and environment management for CareerOrbit AI."""
import os
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator, Any
from dotenv import load_dotenv

# Base paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

class Settings:
    PROJECT_NAME: str = "CareerOrbit AI"
    VERSION: str = "1.0.0"
    
    # Paths
    BASE_DIR: Path = PROJECT_ROOT
    DATA_DIR: Path = Path(os.getenv("CAREERORBIT_DATA_DIR", PROJECT_ROOT / "data"))
    DATABASE_PATH: Path = DATA_DIR / "careerorbit.db"
    RESUMES_DIR: Path = DATA_DIR / "resumes"
    EXPORTS_DIR: Path = DATA_DIR / "exports"
    LOGS_DIR: Path = Path(os.getenv("CAREERORBIT_LOGS_DIR", DATA_DIR / "logs"))

    # Server
    HOST: str = os.getenv("CAREERORBIT_HOST", "127.0.0.1")
    PORT: int = int(os.getenv("CAREERORBIT_PORT", "8000"))
    DEBUG: bool = os.getenv("CAREERORBIT_DEBUG", "False").lower() in ("true", "1", "yes")
    TESTING: bool = os.getenv("CAREERORBIT_TESTING", "False").lower() in ("true", "1", "yes")

    # Timezone & Scheduling
    TIMEZONE: str = os.getenv("CAREERORBIT_TIMEZONE", "Asia/Kolkata")
    JOB_DISCOVERY_CRON_TIME: str = os.getenv("JOB_DISCOVERY_TIME", "08:00")
    STUDY_PLAN_CRON_TIME: str = os.getenv("STUDY_PLAN_TIME", "20:00")
    WINDOWS_TASK_NAME: str = os.getenv("CAREERORBIT_TASK_NAME", "CareerOrbit_Daily_Job_Search")
    SCHEDULER_RECOVERY_WINDOW_HOURS: int = int(os.getenv("CAREERORBIT_RECOVERY_WINDOW_HOURS", "16"))
    MAX_RECOVERY_ATTEMPTS_PER_DAY: int = int(os.getenv("CAREERORBIT_MAX_RECOVERY_ATTEMPTS", "3"))

    # Optional public ATS job-board identifiers (Company=board-token, comma separated).
    GREENHOUSE_BOARDS: str = os.getenv("CAREERORBIT_GREENHOUSE_BOARDS", "")
    LEVER_SITES: str = os.getenv("CAREERORBIT_LEVER_SITES", "")

    # Primary account ownership for multi-account local installs (email or storage_key)
    PRIMARY_ACCOUNT: str = os.getenv("CAREERORBIT_PRIMARY_ACCOUNT", "").strip().lower()

    # Integrations
    GOOGLE_SHEETS_CREDENTIALS_FILE: str = os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE", "")
    GOOGLE_SHEET_ID: str = os.getenv("GOOGLE_SHEET_ID", "")

    # Telegram Bot Integration (@CareerOrbitJobAssistantBot)
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    TELEGRAM_BOT_USERNAME: str = os.getenv("TELEGRAM_BOT_USERNAME", "CareerOrbitJobAssistantBot").strip().lstrip("@")
    TELEGRAM_POLL_INTERVAL: int = int(os.getenv("TELEGRAM_POLL_INTERVAL", "5"))
    TELEGRAM_WEBHOOK_SECRET: str = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()

    @property
    def is_telegram_configured(self) -> bool:
        """Return True if a non-empty Telegram bot token is configured."""
        return bool(self.TELEGRAM_BOT_TOKEN)

    @property
    def masked_telegram_token(self) -> str:
        """Return a safely masked token string for display or logging."""
        if not self.TELEGRAM_BOT_TOKEN:
            return ""
        t = self.TELEGRAM_BOT_TOKEN
        if len(t) <= 10:
            return "***"
        return f"{t[:4]}...{t[-4:]}"

    # Security
    ALLOW_AUTO_SUBMISSION: bool = False  # NEVER True without explicit user action

    def __init__(self):
        # Ensure runtime directories exist
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.RESUMES_DIR.mkdir(parents=True, exist_ok=True)
        self.EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        self.LOGS_DIR.mkdir(parents=True, exist_ok=True)

SETTINGS = Settings()

# Request-scoped storage roots allow each authenticated account to use an
# isolated SQLite database, profile files, exports, and resumes. The default
# remains the existing local data directory for the legacy owner and workers.
_ACTIVE_STORAGE_ROOT: ContextVar[Path | None] = ContextVar("careerorbit_storage_root", default=None)


def current_data_dir() -> Path:
    return _ACTIVE_STORAGE_ROOT.get() or SETTINGS.DATA_DIR


def current_database_path() -> Path:
    root = _ACTIVE_STORAGE_ROOT.get()
    if root is None or root.resolve() == SETTINGS.DATA_DIR.resolve():
        return SETTINGS.DATABASE_PATH
    return root / "careerorbit.db"


def current_resumes_dir() -> Path:
    root = _ACTIVE_STORAGE_ROOT.get()
    if root is None or root.resolve() == SETTINGS.DATA_DIR.resolve():
        return SETTINGS.RESUMES_DIR
    return root / "resumes"


def current_exports_dir() -> Path:
    root = _ACTIVE_STORAGE_ROOT.get()
    if root is None or root.resolve() == SETTINGS.DATA_DIR.resolve():
        return SETTINGS.EXPORTS_DIR
    return root / "exports"


def current_logs_dir() -> Path:
    root = _ACTIVE_STORAGE_ROOT.get()
    if root is None or root.resolve() == SETTINGS.DATA_DIR.resolve():
        return SETTINGS.LOGS_DIR
    return root / "logs"


@contextmanager
def account_storage_context(data_dir: Path) -> Iterator[None]:
    """Route all context-aware storage access to one account's data directory."""
    root = Path(data_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    for subdirectory in ("resumes", "exports", "logs"):
        (root / subdirectory).mkdir(parents=True, exist_ok=True)
    token = _ACTIVE_STORAGE_ROOT.set(root)
    try:
        yield
    finally:
        _ACTIVE_STORAGE_ROOT.reset(token)


_ACTIVE_USER: ContextVar[Any] = ContextVar("careerorbit_active_user", default=None)


def current_active_user() -> Any:
    """Return the currently authenticated user in request context, if any."""
    return _ACTIVE_USER.get()


@contextmanager
def active_user_context(user: Any) -> Iterator[None]:
    """Attach the authenticated AuthUser to the current request context."""
    token = _ACTIVE_USER.set(user)
    try:
        yield
    finally:
        _ACTIVE_USER.reset(token)

