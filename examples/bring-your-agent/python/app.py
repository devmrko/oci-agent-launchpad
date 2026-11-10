"""User-owned business logic example; no Launchpad or Foundation imports."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import sys

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path=='/ready':body='ready'
        elif self.path=='/answer':body='python '+os.environ.get('APP_VERSION','unknown')+' result=42'
        else:self.send_error(404);return
        self.send_response(200);self.end_headers();self.wfile.write(body.encode())
    def log_message(self,fmt,*args):print(fmt % args,flush=True)

print('Python user app started '+os.environ.get('APP_VERSION','unknown'),flush=True)
HTTPServer((os.environ.get('BIND_HOST','127.0.0.1'),int(sys.argv[1])),Handler).serve_forever()
