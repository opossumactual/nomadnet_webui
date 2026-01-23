# WebUI Conversations Feature Design

**Date:** 2026-01-23
**Status:** Approved for implementation

## Overview

Add core LXMF messaging to the WebUI: view conversations, read messages, send messages, create new conversations. Trust indicators displayed but not editable.

## Scope

**In scope:**
- List conversations with trust icons and unread indicators
- View message threads with delivery state indicators
- Send text messages
- Create new conversations by address

**Out of scope (v1):**
- Trust level editing
- Message sync from propagation nodes
- Paper messages
- Peer identity query UI

## Data Flow

### List Conversations
```
GET /conversations/
  → Conversation.conversation_list(app)
  → Returns: [(source_hash, display_name, trust_level, sort_name, unread), ...]
```

### View Conversation Messages
```
GET /conversations/{hash}
  → conversation = Conversation(hash, app)
  → conversation.messages → list of ConversationMessage
  → Extract: content, title, timestamp, state, source_hash
```

### Send Message
```
POST /conversations/{hash}/send
  body: {content: "...", title: ""}
  → conversation.send(content, title)
  → Redirect to conversation view
```

### New Conversation
```
GET  /conversations/new          # Show form
POST /conversations/new          # Create
  body: {address: "hex_hash", name: "optional"}
  → DirectoryEntry if name provided
  → Conversation(address, app, initiator=True)
  → Redirect to /conversations/{address}
```

## UI Design

### Trust Indicators
| Trust Level | Icon | Color |
|-------------|------|-------|
| TRUSTED     | ✓    | Green |
| UNKNOWN     | ?    | Gray  |
| UNTRUSTED   | ✗    | Red   |

### Message Display
- Outgoing: right-aligned, distinct background
- Incoming: left-aligned
- Show: content, timestamp, delivery state icon

### Delivery State Icons
| State     | Icon |
|-----------|------|
| DELIVERED | ✓    |
| SENT      | →    |
| FAILED    | ✗    |

## Files to Modify

1. `routes/conversations.py` - Message loading, send, new conversation
2. `templates/conversations.html` - Trust icons, messages, new conv modal
3. CSS in `templates/base.html` or separate file

## Implementation Order

1. Load and display actual messages in conversation view
2. Add trust/state icons to template
3. Implement POST send endpoint
4. Add new conversation form and endpoint
5. CSS polish
