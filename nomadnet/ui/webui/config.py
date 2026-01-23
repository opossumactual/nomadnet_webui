import os
import secrets

class WebUIConfig:
    """Configuration for WebUI"""

    def __init__(self, app_config=None):
        self.bind = "127.0.0.1"
        self.port = 8282
        self.password = None
        self._generated_password = None

        if app_config and "webui" in app_config:
            webui_config = app_config["webui"]

            if "bind" in webui_config:
                self.bind = webui_config["bind"]

            if "port" in webui_config:
                self.port = int(webui_config["port"])

            if "password" in webui_config and webui_config["password"]:
                self.password = webui_config["password"]

    @property
    def requires_auth(self):
        """Auth required when not binding to localhost"""
        return self.bind != "127.0.0.1"

    @property
    def effective_password(self):
        """Get password, generating one if needed for non-localhost binding"""
        if self.password:
            return self.password

        if self.requires_auth and not self._generated_password:
            self._generated_password = secrets.token_urlsafe(16)

        return self._generated_password

    @property
    def is_generated_password(self):
        """True if using auto-generated password"""
        return self.requires_auth and not self.password and self._generated_password
