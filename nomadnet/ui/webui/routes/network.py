from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def network_index(request: Request):
    """Network status and announce stream"""
    templates = request.app.state.templates
    nomad_app = request.app.state.nomad_app

    # Get current announce stream
    announces = []
    if hasattr(nomad_app, 'directory') and nomad_app.directory:
        for entry in nomad_app.directory.announce_stream[:100]:
            timestamp, source_hash, app_data, announce_type = entry
            display_name = None
            if app_data:
                try:
                    display_name = app_data.decode('utf-8')
                except:
                    pass

            announces.append({
                "timestamp": timestamp,
                "hash": source_hash.hex() if isinstance(source_hash, bytes) else source_hash,
                "name": display_name,
                "type": announce_type
            })

    # Get interface stats if available
    interfaces = []
    try:
        import RNS
        for interface in RNS.Transport.interfaces:
            interfaces.append({
                "name": str(interface),
                "status": "Online" if interface.online else "Offline",
                "type": interface.__class__.__name__
            })
    except:
        pass

    return templates.TemplateResponse("network.html", {
        "request": request,
        "announces": announces,
        "interfaces": interfaces,
        "identity": nomad_app.identity.hexhash if nomad_app.identity else None
    })
