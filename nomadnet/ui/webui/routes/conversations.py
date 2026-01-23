from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def conversations_list(request: Request):
    """List all conversations"""
    templates = request.app.state.templates
    nomad_app = request.app.state.nomad_app

    # Get conversations from the app
    conversations = []
    try:
        from nomadnet.Conversation import Conversation
        conv_list = Conversation.conversation_list(nomad_app)
        for source_hash, display_name, unread in conv_list:
            conversations.append({
                "hash": source_hash,
                "name": display_name or source_hash[:16] + "...",
                "unread": unread
            })
    except Exception as e:
        pass  # Handle gracefully if conversations aren't available

    return templates.TemplateResponse("conversations.html", {
        "request": request,
        "conversations": conversations,
        "selected": None,
        "messages": []
    })


@router.get("/{conv_hash}", response_class=HTMLResponse)
async def conversation_detail(request: Request, conv_hash: str):
    """View a specific conversation"""
    templates = request.app.state.templates
    nomad_app = request.app.state.nomad_app

    # Get conversations list
    conversations = []
    messages = []
    selected_name = conv_hash[:16] + "..."

    try:
        from nomadnet.Conversation import Conversation
        conv_list = Conversation.conversation_list(nomad_app)
        for source_hash, display_name, unread in conv_list:
            is_selected = source_hash == conv_hash
            conversations.append({
                "hash": source_hash,
                "name": display_name or source_hash[:16] + "...",
                "unread": unread,
                "selected": is_selected
            })
            if is_selected:
                selected_name = display_name or source_hash[:16] + "..."

        # TODO: Load actual messages from conversation
        # For now, placeholder

    except Exception as e:
        pass

    return templates.TemplateResponse("conversations.html", {
        "request": request,
        "conversations": conversations,
        "selected": conv_hash,
        "selected_name": selected_name,
        "messages": messages
    })
