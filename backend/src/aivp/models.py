from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from aivp.db import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    export_version: Mapped[int] = mapped_column(Integer, default=0)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    current_step: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunks_total: Mapped[int] = mapped_column(Integer, default=0)
    chunks_done: Mapped[int] = mapped_column(Integer, default=0)
    volumes_total: Mapped[int] = mapped_column(Integer, default=0)
    volumes_done: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_from_step: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class JobStep(Base):
    __tablename__ = "job_steps"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    step: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
