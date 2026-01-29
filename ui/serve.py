"""Simple HTTP server to serve the Math Tutor Dashboard UI."""

import http.server
import socketserver
import webbrowser
from pathlib import Path

PORT = 3000


def main():
    """Start the UI server."""
    ui_dir = Path(__file__).parent

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ui_dir), **kwargs)

    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        url = f"http://localhost:{PORT}"
        print(f"Serving UI at {url}")
        print("Press Ctrl+C to stop")

        # Open browser
        webbrowser.open(url)

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")


if __name__ == "__main__":
    main()
