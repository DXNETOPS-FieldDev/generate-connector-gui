"""AppNeta Alarm Connector Generator — standalone Flask application.

Exposes:
  GET  /              → redirect to /connector
  GET  /connector     → web UI
  POST /api/connector/generate → JSON generation API
"""

import os
import sys

# Lib modules use bare imports; add lib/ to path before any local imports.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))

from flask import Flask, redirect, url_for
from connector_app import connector_bp

app = Flask(__name__, template_folder="templates")
app.register_blueprint(connector_bp)


@app.get("/")
def root():
    return redirect(url_for("connector.index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
