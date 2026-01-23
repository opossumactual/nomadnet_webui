from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()


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
        "error": None
    })


@router.post("/login")
async def login_submit(request: Request, password: str = Form(...)):
    """Handle login form submission"""
    config = request.app.state.config

    if password == config.effective_password:
        response = RedirectResponse("/", status_code=302)
        response.set_cookie("webui_session", password, httponly=True)
        return response

    templates = request.app.state.templates
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "Invalid password"
    })


@router.get("/logout")
async def logout():
    """Clear session and redirect to login"""
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("webui_session")
    return response
