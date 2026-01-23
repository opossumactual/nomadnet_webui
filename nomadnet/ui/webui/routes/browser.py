import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse

from ..services.page_fetcher import PageFetcher, FetchStatus

router = APIRouter()

# Thread pool for blocking RNS operations
_executor = ThreadPoolExecutor(max_workers=4)


def _get_fetcher(request: Request) -> PageFetcher:
    """Get or create page fetcher for this app"""
    if not hasattr(request.app.state, 'page_fetcher'):
        request.app.state.page_fetcher = PageFetcher(request.app.state.nomad_app)
    return request.app.state.page_fetcher


@router.get("/", response_class=HTMLResponse)
async def browser_index(request: Request):
    """Browser main page - shows local node's index"""
    templates = request.app.state.templates
    fetcher = _get_fetcher(request)

    # Fetch local index page
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        _executor,
        lambda: fetcher.fetch("local", "/index.mu")
    )

    if result.status == FetchStatus.DONE or result.status == FetchStatus.CACHED:
        content = result.html
        status = "ready"
    else:
        content = f'<div class="error">Error: {result.error or "Failed to load page"}</div>'
        status = "error"

    return templates.TemplateResponse("browser.html", {
        "request": request,
        "destination": "local",
        "path": "/index.mu",
        "content": content,
        "status": status,
        "raw_markup": result.markup or ""
    })


@router.get("/{destination:path}", response_class=HTMLResponse)
async def browse_destination(request: Request, destination: str):
    """Browse a specific destination/path"""
    templates = request.app.state.templates
    fetcher = _get_fetcher(request)

    # Parse destination - could be "hash/path" or just "hash"
    parts = destination.split("/", 1)
    dest_hash = parts[0]
    path = "/" + parts[1] if len(parts) > 1 else "/"

    # Default to index.mu if just a directory
    if path == "/" or path.endswith("/"):
        path = path.rstrip("/") + "/index.mu"

    # Fetch the page
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        _executor,
        lambda: fetcher.fetch(dest_hash, path)
    )

    if result.status == FetchStatus.DONE or result.status == FetchStatus.CACHED:
        content = result.html
        status = "ready"
    elif result.status == FetchStatus.TIMEOUT:
        content = f'''
            <div class="error">
                <h2>Connection Timeout</h2>
                <p>Could not reach destination <code>{dest_hash}</code></p>
                <p>The node may be offline or unreachable.</p>
            </div>
        '''
        status = "timeout"
    else:
        content = f'''
            <div class="error">
                <h2>Error Loading Page</h2>
                <p>{result.error or "Unknown error"}</p>
            </div>
        '''
        status = "error"

    return templates.TemplateResponse("browser.html", {
        "request": request,
        "destination": dest_hash,
        "path": path,
        "content": content,
        "status": status,
        "raw_markup": result.markup or ""
    })


@router.post("/{destination:path}", response_class=HTMLResponse)
async def browse_destination_post(request: Request, destination: str):
    """Handle form submission to a page"""
    templates = request.app.state.templates
    fetcher = _get_fetcher(request)

    # Parse destination
    parts = destination.split("/", 1)
    dest_hash = parts[0]
    path = "/" + parts[1] if len(parts) > 1 else "/"

    # Get form data
    form_data = await request.form()
    request_data = {}

    # Process form fields - form_data.multi_items() gets all values including duplicates
    for key, value in form_data.multi_items():
        if key.startswith('field_'):
            request_data[key] = value
        elif key == '__link_field':
            # Hidden field from link submission - format is "key=value" or just "key"
            # NomadNet adds var_ prefix to link field values
            if '=' in value:
                link_key, link_value = value.split('=', 1)
                request_data['var_' + link_key] = link_value
            else:
                request_data['var_' + value] = 'true'
        else:
            request_data[key] = value

    # Fetch the page with form data
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        _executor,
        lambda: fetcher.fetch(dest_hash, path, request_data=request_data, use_cache=False)
    )

    if result.status == FetchStatus.DONE or result.status == FetchStatus.CACHED:
        content = result.html
        status = "ready"
    else:
        content = f'''
            <div class="error">
                <h2>Error</h2>
                <p>{result.error or "Unknown error"}</p>
            </div>
        '''
        status = "error"

    return templates.TemplateResponse("browser.html", {
        "request": request,
        "destination": dest_hash,
        "path": path,
        "content": content,
        "status": status,
        "raw_markup": result.markup or ""
    })
