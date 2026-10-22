"""Run the Match Center locally: python -m tacticlens.api [port]"""
import sys

import uvicorn

uvicorn.run("tacticlens.api.app:app", host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
