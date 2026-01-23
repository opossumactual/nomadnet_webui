# NomadNet WebUI Design

**Date:** 2026-01-23
**Status:** Approved for implementation

## Overview

Implement a web-based UI for NomadNet to enable:
- Local browser access (localhost)
- LAN access from other devices
- Headless server management via browser

## Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Backend | FastAPI | Async fits RNS callback model, WebSocket support |
| Templates | Jinja2 | Server-rendered, no build step |
| Interactivity | HTMX | Real-time updates without custom JS |
| Styling | Minimal CSS | Dark theme, monospace, mobile-responsive |

## Features (v1)

1. **Page Browser** - Browse Micron pages, submit forms
2. **Conversations** - LXMF messaging (list + detail view)

Future: Network/Directory, Config, Interfaces, Log, Map, Guide

## Project Structure

```
nomadnet/ui/
├── WebUI.py              # Entry point (replaces stub)
├── webui/
│   ├── __init__.py
│   ├── app.py            # FastAPI application factory
│   ├── auth.py           # Password auth middleware
│   ├── config.py         # WebUI settings
│   │
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── browser.py    # Page browsing endpoints
│   │   ├── conversations.py  # Messaging endpoints
│   │   └── api.py        # WebSocket + JSON API
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── micron.py     # Micron markup → HTML converter
│   │   ├── page_fetcher.py   # RNS.Link wrapper
│   │   └── lxmf_bridge.py    # Conversation interface
│   │
│   ├── templates/
│   │   ├── base.html
│   │   ├── browser.html
│   │   ├── conversations.html
│   │   └── partials/
│   │
│   └── static/
│       ├── style.css
│       └── htmx.min.js
```

## Configuration

Added to `~/.nomadnetwork/config`:

```ini
[webui]
# Bind address: 127.0.0.1 for local only, 0.0.0.0 for LAN
bind = 127.0.0.1

# Port
port = 8282

# Password required when bind != 127.0.0.1
# Leave blank to generate random password on startup
password =
```

## Authentication

- **Localhost (127.0.0.1):** No password required
- **LAN/Remote (0.0.0.0):** Password required
- Session cookie set after login, expires on browser close
- If no password configured for LAN mode, generate random token and log it

## Data Flow

### Page Browsing

```
GET /browse/{destination_hash}/{path}
    ↓
page_fetcher.fetch(dest_hash, path, form_data)
    ↓
RNS.Link.request() with callbacks
    ↓
WebSocket pushes status updates → HTMX swaps progress
    ↓
Response received → micron.to_html(markup)
    ↓
HTML partial returned → HTMX swaps into #page-content
```

### Conversations

```
GET /conversations → List threads
GET /conversations/{hash} → Thread messages
POST /conversations/{hash}/send → Send via LXMF
WebSocket → delivery status + incoming messages
```

## WebSocket Events

Single connection at `/ws` pushes:

```json
{"type": "page_status", "status": "connecting|established|requesting|receiving|done|failed"}
{"type": "page_progress", "percent": 45}
{"type": "new_message", "conversation": "hash", "preview": "text..."}
{"type": "delivery_status", "message_id": "...", "status": "sent|delivered|failed"}
```

HTMX handles swaps via `hx-swap-oob="true"` partials.

## Micron → HTML Conversion

### Text Formatting

| Micron | HTML |
|--------|------|
| `>Header` | `<h1>` |
| `>>Subheader` | `<h2>` |
| `` `!bold` `` | `<strong>` |
| `` `_underline` `` | `<u>` |
| `` `*italic` `` | `<em>` |
| `` `F00text` `` | `<span style="color:#F00">` |
| `--` | `<hr>` |

### Form Elements

| Micron | HTML |
|--------|------|
| `<^fieldname` | `<input type="text" name="field_fieldname">` |
| `<^!password` | `<input type="password">` |
| `<^>textarea` | `<textarea>` |
| `<^|opt|val|*` | `<input type="radio" checked>` |
| `<^?|check` | `<input type="checkbox">` |
| `=>Submit` | `<button type="submit">` |

### Links

| Micron | HTML |
|--------|------|
| `:/page.mu` | `<a href="/browse/current_node/page.mu">` |
| `:abc123:/path` | `<a href="/browse/abc123/path">` |
| `::https://...` | `<a href="..." target="_blank">` |

## UI Layout

```html
<body class="dark">
    <nav>Browser | Conversations <span id="unread-badge"></span></nav>
    <main id="content">{% block content %}</main>
    <footer id="status-bar"></footer>
    <div hx-ws="connect:/ws"></div>
</body>
```

- Dark theme default
- Monospace font for Micron content
- Two-column conversations (list + detail), single column on mobile
- Browser: URL bar, nav buttons, content area

## Dependencies

Add to `setup.py`:

```python
install_requires=[
    ...,
    "fastapi",
    "uvicorn[standard]",
    "jinja2",
    "python-multipart",
]
```

## Implementation Order

1. WebUI.py entry point + basic FastAPI app
2. Config parsing for [webui] section
3. Static file serving + base template
4. Micron → HTML converter (port from MicronParser.py)
5. Page fetcher service (wrap RNS.Link)
6. Browser routes + template
7. WebSocket for live updates
8. Conversations routes + template
9. Auth middleware
10. Polish and testing
