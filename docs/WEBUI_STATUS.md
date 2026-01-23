# NomadNet WebUI - Project Status

## Overview

A web-based interface for NomadNet mesh network, providing browser access to NomadNet pages, network status, and (eventually) LXMF messaging.

**Repository:** https://github.com/opossumactual/nomadnet_webui
**Started:** 2026-01-23
**Status:** MVP functional with conversations

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
- [x] **Conversations page** - Core messaging implemented
  - [x] List conversations with trust indicators
  - [x] Read message threads with delivery status
  - [x] Compose and send messages
  - [x] Mark as read when viewed
  - [x] Create new conversations
  - [ ] Real-time new message notifications (WebSocket push)
  - [ ] Trust level editing
  - [ ] Message sync from propagation nodes

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

### Critical Bugs (Need Fixing)

1. **Peer identity never found** - When opening a conversation with a node from the announce stream, the "identity unknown" message appears and never resolves, even after waiting and refreshing. The `RNS.Transport.request_path()` call may not be working correctly, or there's an issue with how we check `conversation.source_known`.

2. **Network page nodes not clickable** - After adding the message/browse icons, clicking on the node row itself no longer navigates to the browser. The entire row should be clickable, or at least the node name should link to browse.

3. **Browser can't load remote pages** - The page browser fails to load pages hosted by other nodes (e.g., their Wikipedia server, links to other NomadNet pages). Need to debug the remote page fetching in `page_fetcher.py`.

4. **Browser can't load local pages** - Local page browsing may also be broken. Need to verify local file path resolution.

### UI Improvements Needed

5. **Missing type tags in new conversation** - The "Known Peers" list in the new conversation window should show type indicators (Peer/Node/Prop.Node) like the network announce stream does. Currently only shows name and hash.

### Minor Issues

6. ASCII art banners may wrap on narrow windows (trade-off for text readability)
7. Some complex Micron markup edge cases may not render perfectly
8. Remote node connections can timeout if nodes are offline/slow

## Files Modified from Original NomadNet

- `nomadnet/nomadnet.py` - Added `-w`/`--webui` CLI flag
- `nomadnet/NomadNetworkApp.py` - Added webui parameter handling
- `nomadnet/ui/WebUI.py` - Replaced stub with actual implementation
- `setup.py` - Added webui extras_require

## Next Session Context

To continue development, focus on fixing the critical bugs:

### Priority 1: Fix Page Browser
- Debug `services/page_fetcher.py` for remote page loading
- Check path resolution for local vs remote pages
- Test with known working nodes (e.g., Wikipedia servers on the network)

### Priority 2: Fix Identity Discovery
- Investigate why `RNS.Transport.request_path()` doesn't result in identity being found
- Check if `RNS.Identity.recall()` is being called correctly
- Compare with TextUI's `Conversations.py` to see how it handles identity discovery
- May need to wait for path response before checking identity

### Priority 3: Fix Network Page Clicking
- The announce entries changed from `<a>` to `<div>` when adding icons
- Either make the div clickable, or make the name/hash a link to browse

### Priority 4: Add Type Tags
- Update `_get_known_peers()` in `routes/conversations.py` to include type
- Update `conversations.html` template to display type badges

### Start Server
```bash
cd /home/opossum/odev/claudenet/NomadNet
source .venv/bin/activate
nomadnet -w
```
