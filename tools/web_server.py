"""Serve the Flutter web bundle with compression and resumable APK downloads."""
import argparse
from pathlib import Path

import uvicorn
from starlette.middleware.gzip import GZipMiddleware
from starlette.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--directory', type=Path, default=ROOT / 'web')
parser.add_argument('--host', default='127.0.0.1')
parser.add_argument('--port', type=int, default=8080)
args = parser.parse_args()

files = StaticFiles(directory=args.directory, html=True)
compressed = GZipMiddleware(files, minimum_size=1024, compresslevel=5)


async def app(scope, receive, send):
    ranged = any(name == b'range' for name, _ in scope.get('headers', []))
    if scope.get('path', '').endswith('.apk') or ranged:
        await files(scope, receive, send)
    else:
        await compressed(scope, receive, send)


if __name__ == '__main__':
    uvicorn.run(app, host=args.host, port=args.port, lifespan='off')
