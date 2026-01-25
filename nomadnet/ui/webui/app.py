import os
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

from .config import WebUIConfig


def timestamp_format(value):
    """Convert Unix timestamp to readable time string"""
    try:
        dt = datetime.fromtimestamp(value)
        return dt.strftime("%H:%M:%S")
    except:
        return str(value)

# Get the directory where this file is located
WEBUI_DIR = Path(__file__).parent
TEMPLATES_DIR = WEBUI_DIR / "templates"
STATIC_DIR = WEBUI_DIR / "static"


def create_app(nomad_app, config: WebUIConfig) -> FastAPI:
    """Create and configure the FastAPI application"""

    app = FastAPI(
        title="NomadNet WebUI",
        description="Web interface for NomadNet",
        version="0.1.0"
    )

    # Store references for use in routes
    app.state.nomad_app = nomad_app
    app.state.config = config

    # Set up templates
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters['timestamp_format'] = timestamp_format
    app.state.templates = templates

    # Mount static files
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Auth middleware
    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        # Skip auth for localhost binding
        if not config.requires_auth:
            return await call_next(request)

        # Allow static files and login page
        if request.url.path.startswith("/static") or request.url.path == "/login":
            return await call_next(request)

        # Check session cookie
        session = request.cookies.get("webui_session")
        if session != config.effective_password:
            if request.url.path != "/login":
                return RedirectResponse("/login", status_code=302)

        return await call_next(request)

    # Import and include routers
    from .routes import browser, conversations, main, api, network, settings

    app.include_router(main.router)
    app.include_router(browser.router, prefix="/browse")
    app.include_router(conversations.router, prefix="/conversations")
    app.include_router(network.router, prefix="/network")
    app.include_router(settings.router, prefix="/settings")
    app.include_router(api.router)

    # Store the connection manager for use in callbacks
    app.state.ws_manager = api.get_manager()

    return app
