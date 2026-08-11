from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    ALERT_RECIPIENT_EMAIL: str = ""

    CHECK_INTERVAL_HOURS: float = 4
    DATABASE_URL: str = "sqlite:///data/app.db"
    TURSO_DATABASE_URL: str = ""
    TURSO_AUTH_TOKEN: str = ""
    CRON_SECRET: str = ""
    SCRAPER_USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    SCHEDULER_ENABLED: bool = True

    @property
    def use_turso(self) -> bool:
        url = (self.TURSO_DATABASE_URL or "").strip().strip('"').strip("'")
        token = (self.TURSO_AUTH_TOKEN or "").strip().strip('"').strip("'")
        return bool(url and token)


settings = Settings()


def update_env_file(updates: dict[str, str], env_path: str = ".env") -> None:
    """Persist settings changes to the .env file so they survive a restart.

    Replaces existing KEY=value lines in place; appends any keys not
    already present. Leaves comments and unrelated lines untouched.
    No-ops when the filesystem is not writable (e.g. Vercel).
    """
    path = Path(env_path)
    try:
        lines = path.read_text().splitlines() if path.exists() else []
        remaining = dict(updates)

        new_lines = []
        for line in lines:
            stripped = line.strip()
            key = (
                stripped.split("=", 1)[0].strip()
                if "=" in stripped and not stripped.startswith("#")
                else None
            )
            if key in remaining:
                new_lines.append(f"{key}={remaining.pop(key)}")
            else:
                new_lines.append(line)

        for key, value in remaining.items():
            new_lines.append(f"{key}={value}")

        path.write_text("\n".join(new_lines) + "\n")
    except OSError:
        # Read-only filesystem (Vercel) — in-memory settings still apply for this process.
        pass
