from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin_bookings, admin_closures, auth, bookings, labs
from app.core.config import get_settings
from app.core.errors import register_exception_handlers

# Fails here, with a clear message, when JWT_SECRET is unset.
settings = get_settings()

app = FastAPI(title="Lab booking")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(auth.router)
app.include_router(labs.router)
app.include_router(bookings.router)
app.include_router(admin_bookings.router)
app.include_router(admin_closures.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
