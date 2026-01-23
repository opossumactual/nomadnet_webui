import RNS
import nomadnet

from nomadnet import NomadNetworkApp


class WebUI:

    def __init__(self):
        # Lazy imports to avoid requiring fastapi when WebUI isn't used
        from nomadnet.ui.webui.config import WebUIConfig
        from nomadnet.ui.webui.app import create_app
        from nomadnet.ui.webui.callbacks import setup_callbacks

        self.app = NomadNetworkApp.get_shared_instance()
        self.app.ui = self
        self.main_display = None  # Will be set up by callbacks

        # Load WebUI configuration
        self.config = WebUIConfig(self.app.config)

        RNS.log("Starting NomadNet WebUI...", RNS.LOG_INFO)
        RNS.log(f"  Binding to: {self.config.bind}:{self.config.port}", RNS.LOG_INFO)

        if self.config.requires_auth:
            if self.config.is_generated_password:
                RNS.log("", RNS.LOG_WARNING)
                RNS.log("=" * 60, RNS.LOG_WARNING)
                RNS.log("  WebUI password (auto-generated):", RNS.LOG_WARNING)
                RNS.log(f"  {self.config.effective_password}", RNS.LOG_WARNING)
                RNS.log("=" * 60, RNS.LOG_WARNING)
                RNS.log("", RNS.LOG_WARNING)
            else:
                RNS.log("  Authentication: enabled (password from config)", RNS.LOG_INFO)
        else:
            RNS.log("  Authentication: disabled (localhost only)", RNS.LOG_INFO)

        # Create FastAPI app
        self.fastapi_app = create_app(self.app, self.config)

        # Set up callbacks for real-time updates
        setup_callbacks(self, self.fastapi_app.state.ws_manager)
        RNS.log("  WebSocket callbacks registered", RNS.LOG_INFO)

        # Run the server (blocking)
        try:
            import uvicorn
            uvicorn.run(
                self.fastapi_app,
                host=self.config.bind,
                port=self.config.port,
                log_level="warning",
                access_log=False
            )
        except ImportError:
            RNS.log("WebUI requires uvicorn. Install with: pip install uvicorn[standard]", RNS.LOG_ERROR)
            nomadnet.panic()
        except Exception as e:
            RNS.log(f"WebUI error: {e}", RNS.LOG_ERROR)
            nomadnet.panic()
