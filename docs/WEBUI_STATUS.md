# NomadNet WebUI - Project Status

## Overview

A web-based interface for NomadNet mesh network, providing browser access to NomadNet pages, network status, and (eventually) LXMF messaging.

**Repository:** https://github.com/opossumactual/nomadnet_webui
**Started:** 2026-01-23
**Status:** MVP functional, conversations not yet implemented

## How to Run

```bash
cd /home/opossum/odev/claudenet/NomadNet
source .venv/bin/activate
pip install -e ".[webui]"  # Install with webui dependencies
nomadnet -w                 # or --webui
```

Access at: http://localhost:8282

## What's Working

### Page Browser (`/browse`)
- [x] Local page browsing with Micron markup rendering
- [x] Remote node page fetching via RNS.Link
- [x] Form submissions (voting, posting, searching)
- [x] Field handling (`field_` prefix preserved, `var_` prefix added to link fields)
- [x] Path resolution (`/page/` prefix for remote, stripped for local)
- [x] Python page execution using system Python (for libzim, etc.)
- [x] Text wrapping for readability
- [x] Links render as clickable anchors (not all as submit buttons)

### Network Page (`/network`)
- [x] Real-time announce stream via WebSocket
- [x] Clickable node entries (entire row is a link)
- [x] Keyboard navigation (Tab + Enter)
- [x] Interface status display
- [x] Identity display

### Micron Parser (`services/micron.py`)
- [x] Headings (`>`, `>>`, `>>>`)
- [x] Text formatting (bold `!`, underline `_`, italic `*`)
- [x] Colors (`Fxxx` foreground, `Bxxx` background)
- [x] Links (`[label`url]`, internal/external/remote)
- [x] Form fields (text, password, radio, checkbox)
- [x] Submit buttons (for links with field references)
- [x] Literal blocks (`` `= ``)
- [x] Dividers (`-`)
- [x] Alignment (`c` center, `l` left, `r` right)

### Infrastructure
- [x] FastAPI with Jinja2 templates
- [x] HTMX for dynamic updates
- [x] WebSocket for real-time events
- [x] Dark theme CSS
- [x] Password auth for non-localhost access
- [x] Callback bridge to RNS events

## What's NOT Working / TODO

### High Priority
- [ ] **Conversations page** - Currently just a skeleton
  - Need to integrate with LXMF message router
  - List conversations
  - Read message threads
  - Compose and send messages
  - Mark as read/unread
  - Real-time new message notifications

### Medium Priority
- [ ] **File downloads** - Nodes serve files at `/file/` paths
- [ ] **Browser history** - Back/forward may not work well with POST forms
- [ ] **Page caching UI** - Show cached status, force refresh option
- [ ] **Loading indicators** - Show progress during remote fetches
- [ ] **Error pages** - Better styled error messages

### Low Priority
- [ ] **Bookmarks** - Save frequently visited nodes/pages
- [ ] **Search** - Search across known nodes
- [ ] **Mobile responsive** - Test and fix on small screens
- [ ] **Themes** - Light theme option
- [ ] **Settings page** - Configure timeouts, cache, etc.

## Architecture

```
nomadnet/ui/webui/
├── __init__.py
├── app.py              # FastAPI app factory
├── config.py           # WebUIConfig from nomadnet config
├── callbacks.py        # Bridge RNS events to WebSocket
├── routes/
│   ├── main.py         # Home, login, logout
│   ├── browser.py      # Page browsing (GET/POST)
│   ├── network.py      # Announce stream
│   ├── conversations.py # LXMF messages (skeleton)
│   └── api.py          # WebSocket endpoint
├── services/
│   ├── micron.py       # Micron markup → HTML
│   └── page_fetcher.py # Local/remote page fetching
├── templates/          # Jinja2 HTML templates
└── static/             # CSS, HTMX
```

## Key Technical Decisions

1. **System Python for page execution** - Pages may need system packages (libzim, etc.) that aren't in the venv. Using `/usr/bin/python3` instead of venv python.

2. **`/page/` prefix handling** - Remote nodes expect `/page/index.mu` but local files are at `~/.nomadnetwork/storage/pages/index.mu`. Remote requests add `/page/`, local requests strip it.

3. **Form field prefixes** - NomadNet pages expect:
   - `field_xxx` for form input fields (preserved as-is)
   - `var_xxx` for link field values (we add `var_` prefix)

4. **Links vs Submit buttons** - Only links with field references (`[label`url`field1|field2]`) become submit buttons. Plain links are anchor tags.

5. **WebSocket for announces** - The announce stream updates via WebSocket. JavaScript creates `<a>` elements (not `<div>`) so they're clickable.

## Configuration

WebUI reads from NomadNet config (`~/.nomadnetwork/config`):

```
[webui]
port = 8282
host = 127.0.0.1
password = optional_password_for_lan_access
```

If host is not `127.0.0.1` or `localhost`, password is required.

## Dependencies

Added to `setup.py` extras:
- fastapi
- uvicorn
- jinja2
- python-multipart

## Git Remotes

- `origin` → https://github.com/opossumactual/nomadnet_webui.git (your fork)
- `upstream` → https://github.com/markqvist/NomadNet.git (original)

## Known Issues

1. ASCII art banners may wrap on narrow windows (trade-off for text readability)
2. Some complex Micron markup edge cases may not render perfectly
3. Remote node connections can timeout if nodes are offline/slow

## Files Modified from Original NomadNet

- `nomadnet/nomadnet.py` - Added `-w`/`--webui` CLI flag
- `nomadnet/NomadNetworkApp.py` - Added webui parameter handling
- `nomadnet/ui/WebUI.py` - Replaced stub with actual implementation
- `setup.py` - Added webui extras_require

## Next Session Context

To continue development, the main focus should be:

1. **Conversations** - Look at how TextUI handles LXMF:
   - `nomadnet/ui/textui/Conversations.py`
   - `nomadnet/ui/textui/Messages.py`
   - `app.message_router` for LXMF access

2. **Testing** - The webui server can run alongside TextUI (different processes)

3. **Start server**: `cd /home/opossum/odev/claudenet/NomadNet && source .venv/bin/activate && nomadnet -w`
