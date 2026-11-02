"""Local FastAPI app. Demo identity is explicit, not production authentication."""

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from bookly import service
from bookly.agents import run_turn
from bookly.channel_prompts import prompt_profiles
from bookly.db import (
    Base,
    Case,
    Customer,
    DemoSession,
    Message,
    ReturnProposal,
    make_engine,
    sessions,
)
from bookly.fixtures import reset_demo, seed
from bookly.models import configured_model, model_details
from bookly.warehouse import MockDataWarehouse

load_dotenv()
logger = logging.getLogger(__name__)
STATIC = Path(__file__).with_name("static")


class Login(BaseModel):
    customer_id: Literal["maya", "theo"]


class Channel(BaseModel):
    channel: Literal["chat", "async"] = "chat"


class Turn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    request_id: str = Field(min_length=8, max_length=100)


class ResetDemo(BaseModel):
    confirm: Literal["RESET"]
    channel: Literal["chat", "async"] = "chat"


def create_app(database_url=None, model=None, engine=None):
    engine = engine if engine is not None else make_engine(database_url)
    factory = sessions(engine)
    selected_model = model if model is not None else configured_model()

    @contextmanager
    def transaction(*, resetting=False):
        with factory.begin() as db:
            if engine.dialect.name == "postgresql":
                # Normal writes share a lock; resetting waits for all active writes.
                lock = "pg_advisory_xact_lock" if resetting else "pg_advisory_xact_lock_shared"
                db.execute(text(f"SELECT {lock}(:key)"), {"key": 0x424F4F4B4C59})
            yield db

    @asynccontextmanager
    async def lifespan(app):
        Base.metadata.create_all(engine)
        with transaction() as db:
            seed(db)
        yield
        engine.dispose()

    app = FastAPI(title="Bookly Concierge", lifespan=lifespan)
    app.state.engine = engine
    app.state.factory = factory
    app.state.model = selected_model
    app.state.warehouse = MockDataWarehouse()
    # Also serializes same-process duplicate requests; PostgreSQL row locks protect across workers.
    app.state.case_locks = {}
    app.state.mutation_lock = asyncio.Lock()

    @app.middleware("http")
    async def local_mutations(request: Request, call_next):
        if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return Response("Cross-origin writes are not allowed.", status_code=403)
        if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
            # Do not block this worker's event loop on a DB reset lock while its
            # own model request is awaiting I/O. Keep demo mutations in order.
            async with app.state.mutation_lock:
                response = await call_next(request)
        else:
            response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        return response

    def identity(request: Request):
        token = request.cookies.get("bookly_session")
        with factory() as db:
            session = db.get(DemoSession, token) if token else None
            if not session:
                raise HTTPException(401, "Select a demo customer to begin.")
            return session.customer_id

    @app.exception_handler(service.DomainError)
    async def domain_error(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.get("/api/health")
    def health():
        with factory() as db:
            db.execute(select(Customer.id).limit(1))
        return {
            "status": "ok",
            "mode": "scripted" if selected_model == "scripted" else "live",
            **model_details(selected_model),
        }

    @app.get("/api/demo/customers")
    def customers():
        with factory() as db:
            return [{"id": c.id, "name": c.name} for c in db.scalars(select(Customer))]

    @app.post("/api/demo/session")
    def login(body: Login, request: Request, response: Response):
        token = secrets.token_urlsafe(32)
        with transaction() as db:
            old = request.cookies.get("bookly_session")
            if old and (previous := db.get(DemoSession, old)):
                db.delete(previous)
            db.add(DemoSession(id=token, customer_id=body.customer_id))
        response.set_cookie(
            "bookly_session",
            token,
            httponly=True,
            samesite="strict",
            max_age=60 * 60 * 24,
            secure=request.url.scheme == "https",
        )
        return {"customer_id": body.customer_id}

    @app.get("/api/me")
    def me(customer_id=Depends(identity)):
        with factory() as db:
            customer = db.get(Customer, customer_id)
            cases = db.scalars(
                select(Case).where(Case.customer_id == customer_id).order_by(Case.created_at.desc())
            ).all()
            return {
                "customer": {
                    "id": customer.id,
                    "name": customer.name,
                    "preferences": customer.preferences,
                },
                "orders": service.orders_for(db, customer_id),
                "cases": [service.case_summary(db, c) for c in cases],
                "mode": "scripted" if selected_model == "scripted" else "live",
                **model_details(selected_model),
            }

    @app.get("/api/demo/channel-prompts")
    def prompts(customer_id=Depends(identity)):
        return prompt_profiles()

    @app.post("/api/demo/reset")
    async def reset(body: ResetDemo, customer_id=Depends(identity)):
        with transaction(resetting=True) as db:
            reset_demo(db)
            case = Case(id=service.uid("case"), customer_id=customer_id, channel=body.channel)
            db.add(case)
            db.flush()
            result = service.case_view(db, case)
        app.state.case_locks.clear()
        return result

    @app.post("/api/cases")
    def new_case(body: Channel, customer_id=Depends(identity)):
        with transaction() as db:
            case = Case(id=service.uid("case"), customer_id=customer_id, channel=body.channel)
            db.add(case)
            db.flush()
            return service.case_view(db, case)

    @app.get("/api/cases/{case_id}")
    def get_case(case_id: str, customer_id=Depends(identity)):
        with factory() as db:
            return service.case_view(db, service.case_for(db, customer_id, case_id))

    @app.post("/api/cases/{case_id}/channel")
    async def channel(case_id: str, body: Channel, customer_id=Depends(identity)):
        async with app.state.case_locks.setdefault(case_id, asyncio.Lock()):
            with transaction() as db:
                case = service.case_for(db, customer_id, case_id, lock=True)
                case.channel = body.channel
                service.record(db, case, "channel.changed", {"channel": body.channel})
                return service.case_view(db, case)

    @app.post("/api/cases/{case_id}/messages")
    async def message(case_id: str, body: Turn, customer_id=Depends(identity)):
        if not body.text.strip():
            raise HTTPException(422, "Please enter a message.")
        if body.request_id.startswith(("confirm-", "memory-")):
            raise HTTPException(422, "This request ID is reserved for application updates.")
        async with app.state.case_locks.setdefault(case_id, asyncio.Lock()):
            try:
                async with asyncio.timeout(60):
                    with transaction() as db:
                        case = service.case_for(db, customer_id, case_id, lock=True)
                        previous = db.scalar(
                            select(Message).where(
                                Message.case_id == case_id,
                                Message.request_id == body.request_id,
                                Message.role == "user",
                            )
                        )
                        if previous:
                            if previous.content != body.text.strip():
                                raise HTTPException(
                                    409, "Request ID already used for another message."
                                )
                            return service.case_view(db, case)
                        service.add_message(db, case, body.request_id, "user", body.text.strip())
                        reply = await run_turn(
                            db, case, body.text.strip(), selected_model, app.state.warehouse
                        )
                        service.add_message(db, case, body.request_id, "assistant", reply)
                        return service.case_view(db, case)
            except (service.DomainError, HTTPException):
                raise
            except Exception as exc:
                # Transaction rolls back proposals/messages too; do not expose provider details.
                logger.warning(
                    "Agent turn failed (%s, HTTP status=%s)",
                    type(exc).__name__,
                    getattr(exc, "status_code", None),
                )
                raise HTTPException(
                    503,
                    "The assistant could not complete that turn. Nothing was submitted. Please retry.",
                ) from None

    @app.post("/api/cases/{case_id}/returns/{proposal_id}/confirm")
    async def confirm(case_id: str, proposal_id: str, customer_id=Depends(identity)):
        async with app.state.case_locks.setdefault(case_id, asyncio.Lock()):
            with transaction() as db:
                case = service.case_for(db, customer_id, case_id, lock=True)
                receipt = service.confirm_return(db, case, proposal_id)
                key = f"confirm-{proposal_id}"
                if not db.scalar(
                    select(Message.id).where(Message.case_id == case_id, Message.request_id == key)
                ):
                    service.add_message(
                        db,
                        case,
                        key,
                        "assistant",
                        f"Your return request for {receipt['title']} is recorded: {receipt['id']}. "
                        "The refund has not been issued yet. Follow the return instructions below.",
                    )
                case.state = {**case.state, "latest_system_update": receipt}
                return service.case_view(db, case)

    @app.post("/api/cases/{case_id}/returns/{proposal_id}/dismiss")
    async def dismiss(case_id: str, proposal_id: str, customer_id=Depends(identity)):
        async with app.state.case_locks.setdefault(case_id, asyncio.Lock()):
            with transaction() as db:
                case = service.case_for(db, customer_id, case_id, lock=True)
                proposal = db.scalar(
                    select(ReturnProposal)
                    .where(ReturnProposal.id == proposal_id, ReturnProposal.case_id == case.id)
                    .with_for_update()
                )
                if not proposal or proposal.status != "pending":
                    raise service.DomainError("That return is no longer pending.")
                proposal.status = "dismissed"
                case.state = {
                    **case.state,
                    "pending_return_id": None,
                    "latest_system_update": {"return": "dismissed"},
                }
                service.record(
                    db, case, "return.dismissed_by_customer", {"proposal_id": proposal_id}
                )
                return service.case_view(db, case)

    @app.post("/api/cases/{case_id}/preferences/{proposal_id}/confirm")
    async def preference(case_id: str, proposal_id: str, customer_id=Depends(identity)):
        async with app.state.case_locks.setdefault(case_id, asyncio.Lock()):
            with transaction() as db:
                case = service.case_for(db, customer_id, case_id, lock=True)
                saved = service.confirm_preference(db, case, proposal_id)
                case.state = {**case.state, "latest_system_update": saved}
                service.add_message(
                    db,
                    case,
                    f"memory-{proposal_id}",
                    "assistant",
                    f"I’ll remember your {saved['field']} preference: {saved['value']}.",
                )
                return service.case_view(db, case)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    return app


app = create_app()
