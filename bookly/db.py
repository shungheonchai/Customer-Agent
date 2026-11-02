"""Operational records. Customer/case state is independent of the model runtime."""

import os
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def now():
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)


class CustomerReadingHistory(Base):
    __tablename__ = "customer_reading_history"
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), primary_key=True)
    feedback: Mapped[dict] = mapped_column(JSON, default=dict)


class Book(Base):
    __tablename__ = "books"
    __table_args__ = (CheckConstraint("price_cents > 0"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    author: Mapped[str] = mapped_column(String)
    genre: Mapped[str] = mapped_column(String)
    mood: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    price_cents: Mapped[int] = mapped_column(Integer)
    color: Mapped[str] = mapped_column(String)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    status: Mapped[str] = mapped_column(String)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimated_arrival: Mapped[str | None] = mapped_column(String)


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("paid_cents > 0"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id"))
    paid_cents: Mapped[int] = mapped_column(Integer)


class WarehouseSnapshot(Base):
    __tablename__ = "warehouse_snapshots"
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), primary_key=True)
    source: Mapped[str] = mapped_column(String)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    signals: Mapped[dict] = mapped_column(JSON)


class DemoSession(Base):
    __tablename__ = "demo_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    channel: Mapped[str] = mapped_column(String, default="chat")
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    model_history: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("case_id", "request_id", "role"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    request_id: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ReturnProposal(Base):
    __tablename__ = "return_proposals"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("order_items.id"))
    reason: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending")
    policy_version: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ReturnReceipt(Base):
    __tablename__ = "return_receipts"
    __table_args__ = (CheckConstraint("refund_cents > 0"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("return_proposals.id"), unique=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("order_items.id"), unique=True)
    refund_cents: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


def make_engine(url=None):
    url = url or os.getenv(
        "DATABASE_URL", "postgresql+psycopg://bookly:bookly_local@127.0.0.1:5435/bookly"
    )
    options = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **options)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def foreign_keys(dbapi_connection, _):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


def sessions(engine):
    return sessionmaker(engine, expire_on_commit=False)
