"""Read-only calculator tool, served by the official MCP SDK on loopback."""
import argparse
from mcp.server import MCPServer
server = MCPServer('launchpad-calculator')

@server.tool()
def multiply(a: int, b: int) -> dict:
    """Multiply two integers between -1000 and 1000."""
    if not -1000 <= a <= 1000 or not -1000 <= b <= 1000:
        raise ValueError('Operands out of range')
    return {'result': a * b}

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8097)
    server.run(transport='streamable-http',host='127.0.0.1',port=p.parse_args().port,json_response=True)
