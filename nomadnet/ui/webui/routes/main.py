import secrets

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()


def _get_csrf_token(request: Request) -> str:
    """Get CSRF token for the current session"""
    session_manager = request.app.state.session_manager
    session_token = request.cookies.get("webui_session")
    csrf_token = session_manager.get_csrf_token(session_token)
    return csrf_token or ""


def _get_cookie_settings(request: Request) -> dict:
    """Get secure cookie settings based on config"""
    config = request.app.state.config
    settings = {
        "httponly": True,
        "samesite": "strict",
    }
    # Only set secure flag if not binding to localhost (assumes HTTPS in production)
    if config.bind != "127.0.0.1":
        settings["secure"] = True
    return settings


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main landing page"""
    import RNS

    templates = request.app.state.templates
    nomad_app = request.app.state.nomad_app

    # Get interface stats
    interfaces = []
    try:
        for interface in RNS.Transport.interfaces:
            interfaces.append({
                "name": str(interface),
                "status": "Online" if interface.online else "Offline",
                "type": interface.__class__.__name__
            })
    except:
        pass

    # Get display name
    display_name = nomad_app.get_display_name() if hasattr(nomad_app, 'get_display_name') else "Unknown"

    # Get LXMF destination hash (used for peer messaging)
    lxmf_hash = None
    try:
        if hasattr(nomad_app, 'lxmf_destination'):
            lxmf_dest = nomad_app.lxmf_destination
            if hasattr(lxmf_dest, 'hash'):
                lxmf_hash = RNS.prettyhexrep(lxmf_dest.hash).replace("<", "").replace(">", "")
                RNS.log(f"WebUI: Got LXMF hash: {lxmf_hash}", RNS.LOG_DEBUG)
            else:
                RNS.log("WebUI: lxmf_destination has no hash attribute", RNS.LOG_ERROR)
        else:
            RNS.log("WebUI: nomad_app has no lxmf_destination attribute", RNS.LOG_ERROR)
    except Exception as e:
        RNS.log(f"WebUI: Error getting LXMF hash: {e}", RNS.LOG_ERROR)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "identity": nomad_app.identity,
        "lxmf_hash": lxmf_hash,
        "display_name": display_name,
        "interfaces": interfaces,
        "csrf_token": _get_csrf_token(request),
    })


@router.post("/settings/name")
async def update_display_name(request: Request, display_name: str = Form(...)):
    """Update the node's display name and announce"""
    import RNS

    nomad_app = request.app.state.nomad_app

    try:
        new_name = display_name.strip()
        if new_name:
            nomad_app.set_display_name(new_name)
            RNS.log(f"WebUI: Updated display name to '{new_name}'", RNS.LOG_NOTICE)
            # Also announce with the new name
            nomad_app.announce_now()
            RNS.log("WebUI: Announced with new display name", RNS.LOG_NOTICE)
    except Exception as e:
        RNS.log(f"WebUI: Error updating display name: {e}", RNS.LOG_ERROR)

    return RedirectResponse("/", status_code=302)


@router.post("/settings/announce")
async def trigger_announce(request: Request):
    """Trigger an immediate announce"""
    import RNS

    nomad_app = request.app.state.nomad_app

    try:
        identity_hash = nomad_app.lxmf_destination.hexhash
        display_name = nomad_app.peer_settings.get("display_name", "Unknown")
        nomad_app.announce_now()
        RNS.log(f"WebUI: Sent announce for <{identity_hash}> ({display_name})", RNS.LOG_NOTICE)
        return RedirectResponse("/?announced=1", status_code=302)
    except Exception as e:
        RNS.log(f"WebUI: Error triggering announce: {e}", RNS.LOG_ERROR)
        return RedirectResponse("/?announced=0", status_code=302)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    templates = request.app.state.templates
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": None,
        "csrf_token": _get_csrf_token(request),
    })


@router.post("/login")
async def login_submit(request: Request, password: str = Form(...)):
    """Handle login form submission"""
    config = request.app.state.config
    session_manager = request.app.state.session_manager

    # Use timing-safe comparison to prevent timing attacks
    if secrets.compare_digest(password, config.effective_password):
        # Create secure session token instead of storing password
        session_token, csrf_token = session_manager.create_session()

        response = RedirectResponse("/", status_code=302)
        cookie_settings = _get_cookie_settings(request)
        response.set_cookie("webui_session", session_token, **cookie_settings)
        return response

    templates = request.app.state.templates
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "Invalid password",
        "csrf_token": _get_csrf_token(request),
    })


@router.get("/logout")
async def logout(request: Request):
    """Clear session and redirect to login"""
    session_manager = request.app.state.session_manager
    session_token = request.cookies.get("webui_session")

    # Destroy the server-side session
    session_manager.destroy_session(session_token)

    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("webui_session")
    return response


@router.get("/api/csrf-token")
async def get_csrf_token(request: Request):
    """Get CSRF token for the current session"""
    from fastapi.responses import JSONResponse

    session_manager = request.app.state.session_manager
    session_token = request.cookies.get("webui_session")

    csrf_token = session_manager.get_csrf_token(session_token)
    if csrf_token:
        return JSONResponse({"csrf_token": csrf_token})

    return JSONResponse({"error": "No valid session"}, status_code=401)
