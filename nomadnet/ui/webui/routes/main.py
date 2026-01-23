from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main landing page"""
    templates = request.app.state.templates
    nomad_app = request.app.state.nomad_app

    return templates.TemplateResponse("index.html", {
        "request": request,
        "identity": nomad_app.identity,
        "node_name": getattr(nomad_app, 'node_name', 'NomadNet Node'),
    })


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
