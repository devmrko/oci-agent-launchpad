"""HTTP entry point for the user-owned connected agent."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import re
import sys
from connections import run

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,status,value):
        body=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):self.send(200 if self.path=='/ready' else 404,{'ready':self.path=='/ready'})
    def do_POST(self):
        if self.path!='/invoke':self.send(404,{'error':'NOT_FOUND'});return
        trace=self.headers.get('X-Request-ID','')
        try:
            self.connection.settimeout(5)
            if not re.fullmatch('[0-9a-f]{32}',trace):raise ValueError()
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=4096:raise ValueError()
            payload=json.loads(self.rfile.read(size))
            if not isinstance(payload,dict) or set(payload)!={'message'}:raise ValueError()
            result=run(payload['message'],trace)
            self.send(200 if result['status']=='SUCCEEDED' else 502,result)
        except (ValueError,OSError):self.send(400,{'error':'INVALID_REQUEST'})

if __name__=='__main__':
    HTTPServer((os.environ.get('BIND_HOST','127.0.0.1'),int(sys.argv[1])),Handler).serve_forever()
