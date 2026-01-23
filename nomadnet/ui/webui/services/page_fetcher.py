"""
Page Fetcher Service

Fetches pages from NomadNet nodes via RNS.Link.
"""

import os
import time
import threading
import hashlib
from typing import Optional, Dict, Any, Callable
from enum import Enum

import RNS

from .micron import micron_to_html


class FetchStatus(Enum):
    IDLE = "idle"
    RESOLVING = "resolving"
    CONNECTING = "connecting"
    REQUESTING = "requesting"
    RECEIVING = "receiving"
    DONE = "done"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CACHED = "cached"


class PageFetchResult:
    """Result of a page fetch operation"""

    def __init__(self):
        self.status: FetchStatus = FetchStatus.IDLE
        self.markup: Optional[str] = None
        self.html: Optional[str] = None
        self.error: Optional[str] = None
        self.progress: float = 0.0
        self.destination_hash: Optional[str] = None
        self.path: str = "/"
        self.fg_color: Optional[str] = None
        self.bg_color: Optional[str] = None


class PageFetcher:
    """
    Fetches pages from NomadNet nodes.

    Handles:
    - Path resolution via RNS.Transport
    - Link establishment via RNS.Link
    - Page request and response
    - Caching
    - Progress callbacks
    """

    LINK_TIMEOUT = 30.0
    REQUEST_TIMEOUT = 60.0
    CACHE_TTL = 300  # 5 minutes

    def __init__(self, app):
        """
        Initialize the page fetcher.

        Args:
            app: NomadNetworkApp instance
        """
        self.app = app
        self._cache: Dict[str, tuple] = {}  # url -> (timestamp, markup, fg, bg)
        self._active_fetches: Dict[str, PageFetchResult] = {}
        self._lock = threading.Lock()

    def fetch(
        self,
        destination_hash: str,
        path: str = "/",
        request_data: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
        status_callback: Optional[Callable[[FetchStatus, float], None]] = None
    ) -> PageFetchResult:
        """
        Fetch a page from a NomadNet node.

        Args:
            destination_hash: Hex string of the destination hash (or "local")
            path: Page path on the node
            request_data: Form data to send with request
            use_cache: Whether to use cached pages
            status_callback: Called with (status, progress) updates

        Returns:
            PageFetchResult with status, markup/html, or error
        """
        result = PageFetchResult()
        result.destination_hash = destination_hash
        result.path = path

        # Handle local pages
        if destination_hash == "local":
            return self._fetch_local(path, request_data, result)

        # Check cache
        cache_key = f"{destination_hash}:{path}"
        if use_cache and not request_data:
            cached = self._get_cached(cache_key)
            if cached:
                result.status = FetchStatus.CACHED
                result.markup = cached[0]
                result.fg_color = cached[1]
                result.bg_color = cached[2]
                result.html = micron_to_html(
                    result.markup,
                    destination=destination_hash,
                    path=path,
                    fg_color=result.fg_color,
                    bg_color=result.bg_color
                )
                if status_callback:
                    status_callback(FetchStatus.CACHED, 1.0)
                return result

        # Fetch from remote node
        return self._fetch_remote(
            destination_hash, path, request_data, result, status_callback
        )

    def _fetch_local(
        self,
        path: str,
        request_data: Optional[Dict[str, Any]],
        result: PageFetchResult
    ) -> PageFetchResult:
        """Fetch a page from the local node's pages directory"""
        try:
            # Clean up path
            if not path.startswith('/'):
                path = '/' + path

            # Strip /page/ prefix - NomadNet URLs use /page/ but files are in pages dir
            if path.startswith('/page/'):
                path = path[6:]  # Remove '/page/'
            elif path.startswith('page/'):
                path = path[5:]  # Remove 'page/'

            if not path.startswith('/'):
                path = '/' + path
            if path == '/':
                path = '/index.mu'
            if not path.endswith('.mu'):
                path = path + '.mu'

            # Get pages directory from app
            pages_dir = self.app.pagespath

            # Construct full path (prevent directory traversal)
            safe_path = os.path.normpath(path).lstrip('/')
            full_path = os.path.join(pages_dir, safe_path)

            # Verify it's within pages directory
            if not os.path.abspath(full_path).startswith(os.path.abspath(pages_dir)):
                result.status = FetchStatus.FAILED
                result.error = "Invalid path"
                return result

            if not os.path.exists(full_path):
                result.status = FetchStatus.FAILED
                result.error = f"Page not found: {path}"
                return result

            # Check if it's a Python page (executable)
            with open(full_path, 'r') as f:
                content = f.read()

            # Check for Python shebang
            if content.startswith('#!'):
                # Execute as Python page
                markup = self._execute_page(full_path, request_data)
            else:
                markup = content

            # Extract color headers
            fg_color, bg_color = self._extract_colors(markup)

            result.status = FetchStatus.DONE
            result.markup = markup
            result.fg_color = fg_color
            result.bg_color = bg_color
            result.html = micron_to_html(
                markup,
                destination="local",
                path=path,
                fg_color=fg_color,
                bg_color=bg_color
            )
            return result

        except Exception as e:
            result.status = FetchStatus.FAILED
            result.error = str(e)
            return result

    def _execute_page(
        self,
        page_path: str,
        request_data: Optional[Dict[str, Any]]
    ) -> str:
        """Execute a Python page and capture its output"""
        import subprocess
        import tempfile

        # Set up environment with request data
        env = os.environ.copy()
        env['remote_identity'] = self.app.identity.hexhash if self.app.identity else 'anonymous'

        if request_data:
            for key, value in request_data.items():
                # Keep field_ and var_ prefixes as NomadNet pages expect them
                env[key] = str(value)

        try:
            # Run the page script using system Python to access system packages
            # (the venv Python may not have all required modules like libzim)
            python_path = '/usr/bin/python3'
            proc = subprocess.run(
                [python_path, page_path],
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
                cwd=os.path.dirname(page_path)
            )
            if proc.returncode != 0 and proc.stderr:
                return f">Error\n\n{proc.stderr}"
            return proc.stdout if proc.stdout else ""
        except subprocess.TimeoutExpired:
            return ">Error\n\nPage execution timed out."
        except Exception as e:
            return f">Error\n\n{str(e)}"

    def _fetch_remote(
        self,
        destination_hash: str,
        path: str,
        request_data: Optional[Dict[str, Any]],
        result: PageFetchResult,
        status_callback: Optional[Callable[[FetchStatus, float], None]]
    ) -> PageFetchResult:
        """Fetch a page from a remote node via RNS.Link"""
        try:
            # Convert hex hash to bytes
            dest_hash_bytes = bytes.fromhex(destination_hash)

            # Update status
            result.status = FetchStatus.RESOLVING
            if status_callback:
                status_callback(FetchStatus.RESOLVING, 0.0)

            # Check if we have a path to the destination
            if not RNS.Transport.has_path(dest_hash_bytes):
                RNS.Transport.request_path(dest_hash_bytes)

                # Wait for path (with timeout)
                timeout = time.time() + self.LINK_TIMEOUT
                while not RNS.Transport.has_path(dest_hash_bytes):
                    if time.time() > timeout:
                        result.status = FetchStatus.TIMEOUT
                        result.error = "Path resolution timeout"
                        if status_callback:
                            status_callback(FetchStatus.TIMEOUT, 0.0)
                        return result
                    time.sleep(0.1)

            # Get the destination identity
            dest_identity = RNS.Identity.recall(dest_hash_bytes)
            if not dest_identity:
                result.status = FetchStatus.FAILED
                result.error = "Could not recall destination identity"
                if status_callback:
                    status_callback(FetchStatus.FAILED, 0.0)
                return result

            # Create destination
            destination = RNS.Destination(
                dest_identity,
                RNS.Destination.OUT,
                RNS.Destination.SINGLE,
                "nomadnetwork",
                "node"
            )

            # Update status
            result.status = FetchStatus.CONNECTING
            if status_callback:
                status_callback(FetchStatus.CONNECTING, 0.1)

            # Create link
            link_established = threading.Event()
            link_failed = threading.Event()
            link_ref = [None]

            def on_established(link):
                link_ref[0] = link
                link_established.set()

            def on_closed(link):
                if not link_established.is_set():
                    link_failed.set()

            link = RNS.Link(
                destination,
                established_callback=on_established,
                closed_callback=on_closed
            )

            # Wait for link establishment
            timeout = time.time() + self.LINK_TIMEOUT
            while not link_established.is_set() and not link_failed.is_set():
                if time.time() > timeout:
                    link.teardown()
                    result.status = FetchStatus.TIMEOUT
                    result.error = "Link establishment timeout"
                    if status_callback:
                        status_callback(FetchStatus.TIMEOUT, 0.0)
                    return result
                time.sleep(0.1)

            if link_failed.is_set():
                result.status = FetchStatus.FAILED
                result.error = "Link establishment failed"
                if status_callback:
                    status_callback(FetchStatus.FAILED, 0.0)
                return result

            # Link established, request page
            result.status = FetchStatus.REQUESTING
            if status_callback:
                status_callback(FetchStatus.REQUESTING, 0.2)

            # Prepare request path - remote nodes expect /page/ prefix
            request_path = path if path.startswith('/') else '/' + path
            if not request_path.startswith('/page/'):
                request_path = '/page' + request_path

            response_data = [None]
            response_received = threading.Event()
            response_failed = threading.Event()
            progress_value = [0.2]

            def on_response(receipt):
                response_data[0] = receipt.response
                response_received.set()

            def on_failed(receipt):
                response_failed.set()

            def on_progress(receipt):
                progress_value[0] = 0.2 + (receipt.progress * 0.8)
                result.progress = progress_value[0]
                if status_callback:
                    status_callback(FetchStatus.RECEIVING, progress_value[0])

            # Send request
            receipt = link.request(
                request_path,
                data=request_data,
                response_callback=on_response,
                failed_callback=on_failed,
                progress_callback=on_progress
            )

            result.status = FetchStatus.RECEIVING
            if status_callback:
                status_callback(FetchStatus.RECEIVING, 0.3)

            # Wait for response
            timeout = time.time() + self.REQUEST_TIMEOUT
            while not response_received.is_set() and not response_failed.is_set():
                if time.time() > timeout:
                    link.teardown()
                    result.status = FetchStatus.TIMEOUT
                    result.error = "Request timeout"
                    if status_callback:
                        status_callback(FetchStatus.TIMEOUT, 0.0)
                    return result
                time.sleep(0.1)

            # Close link
            link.teardown()

            if response_failed.is_set():
                result.status = FetchStatus.FAILED
                result.error = "Request failed"
                if status_callback:
                    status_callback(FetchStatus.FAILED, 0.0)
                return result

            # Process response
            page_data = response_data[0]
            if page_data is None:
                result.status = FetchStatus.FAILED
                result.error = "Empty response"
                if status_callback:
                    status_callback(FetchStatus.FAILED, 0.0)
                return result

            # Decode markup
            try:
                markup = page_data.decode('utf-8')
            except:
                markup = str(page_data)

            # Extract colors
            fg_color, bg_color = self._extract_colors(markup)

            # Cache the result
            cache_key = f"{destination_hash}:{path}"
            self._set_cached(cache_key, markup, fg_color, bg_color)

            # Set result
            result.status = FetchStatus.DONE
            result.markup = markup
            result.fg_color = fg_color
            result.bg_color = bg_color
            result.html = micron_to_html(
                markup,
                destination=destination_hash,
                path=path,
                fg_color=fg_color,
                bg_color=bg_color
            )
            result.progress = 1.0

            if status_callback:
                status_callback(FetchStatus.DONE, 1.0)

            return result

        except Exception as e:
            result.status = FetchStatus.FAILED
            result.error = str(e)
            if status_callback:
                status_callback(FetchStatus.FAILED, 0.0)
            return result

    def _extract_colors(self, markup: str) -> tuple:
        """Extract #!fg= and #!bg= headers from markup"""
        fg_color = None
        bg_color = None

        for line in markup.split('\n')[:10]:  # Only check first 10 lines
            if line.startswith('#!fg='):
                fg_color = line[5:].strip()
            elif line.startswith('#!bg='):
                bg_color = line[5:].strip()

        return fg_color, bg_color

    def _get_cached(self, key: str) -> Optional[tuple]:
        """Get cached page if still valid"""
        with self._lock:
            if key in self._cache:
                timestamp, markup, fg, bg = self._cache[key]
                if time.time() - timestamp < self.CACHE_TTL:
                    return (markup, fg, bg)
                else:
                    del self._cache[key]
        return None

    def _set_cached(self, key: str, markup: str, fg: Optional[str], bg: Optional[str]):
        """Cache a page"""
        with self._lock:
            self._cache[key] = (time.time(), markup, fg, bg)

    def clear_cache(self):
        """Clear the page cache"""
        with self._lock:
            self._cache.clear()
