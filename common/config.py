"""
Centralized configuration shared by the bot and admin services.
All values are loaded from environment variables (see .env.example).
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Telegram bot ---
    bot_token: str
    bot_username: str = "ielts_level_bot"

    # --- Webhook ---
    use_webhook: bool = True
    webhook_base_url: str = ""  # e.g. https://admin.ielts-8-plus-bot.uz
    webhook_path: str = "/webhook/tg"
    webhook_secret: str = ""  # random string, also used as the URL suffix for obscurity
    webapp_host: str = "0.0.0.0"
    webapp_port: int = 8081

    # --- Source content channel (private, admin-controlled, bot must be admin) ---
    # One private channel per section. Content messages (video/pdf/html) for a given
    # (section, day) live here; the admin panel stores which message_ids to copy.
    channel_reading_id: int
    channel_multilevel_id: int
    channel_listening_id: int
    channel_speaking_id: int
    channel_writing_id: int

    # --- Required subscription-gate channels (public, 4 of them) ---
    # These are public channels with usernames, so getChatMember is called with
    # "@username" directly -- no numeric chat_id needed/collected for these.
    req_channel_1_username: str = "MultiLevelRecord"
    req_channel_1_name: str = "Multi-Level Record"

    req_channel_2_username: str = "RS_IELTS"
    req_channel_2_name: str = "Sirojiddin's blog"

    req_channel_3_username: str = "alisher_abduvohobov"
    req_channel_3_name: str = "Alisher's IELTS | 9.0"

    req_channel_4_username: str = "xojaevs"
    req_channel_4_name: str = "Muxriddin Xujaev | IELTS"

    # Results channel post linked from "🏆 Natijalar"
    results_link: str = "https://t.me/level_results/2"

    # --- Database ---
    database_url: str  # postgresql+asyncpg://user:pass@postgres:5432/dbname
    db_pool_size: int = 20
    db_max_overflow: int = 40
    db_pool_timeout: int = 30

    # --- Postgres connection pieces, for pg_dump (the daily backup job) ---
    # These mirror POSTGRES_* used by the postgres container itself in
    # docker-compose.yml -- kept separate from database_url because pg_dump
    # needs plain libpq-style args, not a SQLAlchemy+asyncpg URL.
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str
    postgres_user: str
    postgres_password: str

    # --- Daily DB backup, sent via Telegram to the admin ---
    backup_admin_chat_id: int = 8233724149
    backup_hour: int = 8
    backup_minute: int = 0

    # --- Bot-side admin commands (e.g. /broadcast) ---
    # Comma-separated Telegram user ids allowed to use admin-only bot
    # commands. Defaults to the same account as backup_admin_chat_id.
    admin_ids: str = "8233724149"

    @property
    def admin_id_list(self) -> list[int]:
        return [int(x.strip()) for x in self.admin_ids.split(",") if x.strip()]

    # --- Admin panel ---
    admin_username: str
    admin_password: str
    admin_secret_key: str  # session/cookie signing secret

    # --- Referral / unlock economics ---
    referrals_per_slot: int = 3

    # --- Broadcast pacing ---
    broadcast_rate_per_sec: int = 28  # just under Telegram's ~30 msg/sec ceiling


    # --- Misc ---
    log_level: str = "INFO"
    tz: str = "Asia/Tashkent"

    @property
    def webhook_url(self) -> str:
        return f"{self.webhook_base_url.rstrip('/')}{self.webhook_path}/{self.webhook_secret}"

    @property
    def required_channels(self) -> List[dict]:
        """
        chat_id is "@username" (works fine with Bot.get_chat_member for public
        channels) rather than a numeric id, since only usernames were provided
        for these 4 gate channels.
        """
        return [
            {"username": self.req_channel_1_username, "name": self.req_channel_1_name, "chat_id": f"@{self.req_channel_1_username}"},
            {"username": self.req_channel_2_username, "name": self.req_channel_2_name, "chat_id": f"@{self.req_channel_2_username}"},
            {"username": self.req_channel_3_username, "name": self.req_channel_3_name, "chat_id": f"@{self.req_channel_3_username}"},
            {"username": self.req_channel_4_username, "name": self.req_channel_4_name, "chat_id": f"@{self.req_channel_4_username}"},
        ]

    @property
    def content_channel_map(self) -> dict:
        """section value -> source channel id"""
        return {
            "reading": self.channel_reading_id,
            "multilevel": self.channel_multilevel_id,
            "listening": self.channel_listening_id,
            "speaking": self.channel_speaking_id,
            "writing": self.channel_writing_id,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
