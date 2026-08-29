"""
SQLAlchemy 2.0 ORM models.

Section enum values used throughout: reading, multilevel, listening, speaking, writing.
Gated (referral-locked) sections: listening, speaking, writing, multilevel.
Free section: reading.
"""
import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, String,
    Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Section(str, enum.Enum):
    reading = "reading"
    multilevel = "multilevel"
    listening = "listening"
    speaking = "speaking"
    writing = "writing"
    speaking_recent = "speaking_recent"
    writing_ai_check = "writing_ai_check"

    @property
    def is_gated(self) -> bool:
        return self != Section.reading

    @property
    def display_name(self) -> str:
        return {
            Section.reading: "IELTS Reading",
            Section.multilevel: "Multi-Level darslari",
            Section.listening: "IELTS Listening",
            Section.speaking: "IELTS Speaking",
            Section.writing: "IELTS Writing",
            Section.speaking_recent: "🔥 Speaking Recent Questions",
            Section.writing_ai_check: "🔥 Writing AI Check + Feedback",
        }[self]


# The 6 features a user can earn unlocks for, in the fixed prompt order.
# speaking_recent and writing_ai_check are NOT day-numbered lesson content
# like the other 4 -- they live under the "Ko'proq funksiyalar" menu instead
# of the main reply keyboard, and have their own dedicated handlers in
# bot/handlers/more_features.py rather than going through content_day_grid.
GATED_SECTIONS: List[Section] = [
    Section.listening,
    Section.speaking,
    Section.writing,
    Section.multilevel,
    Section.speaking_recent,
    Section.writing_ai_check,
]

DAYS_PER_SECTION = {
    Section.reading: 20,
    Section.multilevel: 20,
    Section.listening: 10,
    Section.speaking: 10,
    Section.writing: 10,
}


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    start_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    referred_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), nullable=True
    )

    is_verified_member: Mapped[bool] = mapped_column(Boolean, default=False)
    # One-way flag: True the first time this user ever passes full channel
    # verification, and NEVER reset back to False afterward (unlike
    # is_verified_member, which flips both ways as they join/leave). Used to
    # decide was_fresh_at_landing on a NEW referral link click -- prevents
    # someone who's already been a real member from leaving, clicking a
    # friend's link, and rejoining just to hand that friend undeserved credit.
    ever_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    last_membership_check: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Referral link click bookkeeping: the payload (referrer id) a user landed with,
    # captured on first /start before we know whether verification will complete.
    landed_via_referrer_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    referrals_sent: Mapped[List["Referral"]] = relationship(
        "Referral", foreign_keys="Referral.referrer_id", back_populates="referrer"
    )
    referral_received: Mapped[Optional["Referral"]] = relationship(
        "Referral", foreign_keys="Referral.referred_id", back_populates="referred", uselist=False
    )
    section_unlocks: Mapped[List["SectionUnlock"]] = relationship("SectionUnlock", back_populates="user")


class Referral(Base):
    """
    One row per referred user (a user can only ever be referred by one person --
    whoever's link they first landed with).
    """
    __tablename__ = "referrals"
    __table_args__ = (UniqueConstraint("referred_id", name="uq_referral_referred_once"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), index=True)
    referred_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Captured once, at landing time (before the referred user joins anything).
    # Immutable -- this is the "was genuinely fresh" eligibility flag and can
    # never be re-earned if False.
    was_fresh_at_landing: Mapped[bool] = mapped_column(Boolean, default=False)

    # Current validity = was_fresh_at_landing AND referred user is currently
    # verified (member of all 4 gate channels). Flips to False if they leave;
    # can flip back to True if they rejoin (was_fresh_at_landing never changes).
    is_valid: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Set when this referral is one of the 3 assigned to a completed batch that
    # unlocked a section. Cleared (back to NULL / unassigned pool) if that
    # section is re-locked due to a revocation in its batch.
    section_assigned: Mapped[Optional[Section]] = mapped_column(Enum(Section, name="section_enum"), nullable=True)
    batch_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    referrer: Mapped["User"] = relationship("User", foreign_keys=[referrer_id], back_populates="referrals_sent")
    referred: Mapped["User"] = relationship("User", foreign_keys=[referred_id], back_populates="referral_received")


class SectionUnlock(Base):
    __tablename__ = "section_unlocks"
    __table_args__ = (UniqueConstraint("user_id", "section", name="uq_user_section"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), index=True)
    section: Mapped[Section] = mapped_column(Enum(Section, name="section_enum"))
    unlocked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    relocked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship("User", back_populates="section_unlocks")


class Content(Base):
    __tablename__ = "content"
    __table_args__ = (UniqueConstraint("section", "day_number", name="uq_section_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    section: Mapped[Section] = mapped_column(Enum(Section, name="section_enum"))
    day_number: Mapped[int] = mapped_column(Integer)
    source_channel_id: Mapped[int] = mapped_column(BigInteger)
    # List of message ids in the source channel to copyMessage, in send order
    # (e.g. [video_msg_id, pdf_msg_id, html_msg_id]).
    message_ids: Mapped[list] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ContentDelivery(Base):
    """
    Log of every successful copyMessage delivery to a user, so we can answer
    "who hasn't received any content from section X yet" for broadcast
    segmentation -- this is separate from SectionUnlock, since a user can be
    unlocked for a section but never actually have tapped a day (and Reading/
    Multi-Level, being free, have no unlock event at all to check against).
    """
    __tablename__ = "content_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), index=True)
    section: Mapped[Section] = mapped_column(Enum(Section, name="section_enum"))
    day_number: Mapped[int] = mapped_column(Integer)
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdminAction(Base):
    __tablename__ = "admin_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_username: Mapped[str] = mapped_column(String(64))
    action_type: Mapped[str] = mapped_column(String(64))
    target_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BroadcastLog(Base):
    """Not in the original minimum schema, but needed to drive the
    rate-limited/resumable broadcast progress bar in the admin panel."""
    __tablename__ = "broadcast_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    segment: Mapped[str] = mapped_column(String(64))
    # message_text is now only a human-readable label for the history table
    # (e.g. the typed text, or a caption, or "[media]") -- it is NOT what
    # gets sent anymore. Actual sending copies source_chat_id/source_message_id
    # via bot.copy_message, which works for text, photo, video, voice, or any
    # other message type without type-specific handling.
    message_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    source_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    total_targets: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/running/done/failed
    created_by: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
