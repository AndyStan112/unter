"""Deterministic OSRM/Photon fixture for integration; never used by production."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        path = urlsplit(self.path).path
        if path.startswith('/route/v1/driving/'):
            coordinates = [[float(n) for n in point.split(',')] for point in path.rsplit('/', 1)[1].split(';')]
            data = {'code': 'Ok', 'routes': [{'distance': 3000, 'duration': 600,
                'geometry': {'type': 'LineString', 'coordinates': coordinates},
                'legs': [{'steps': [{'distance': 3000, 'duration': 600, 'name': 'Test Street',
                    'maneuver': {'type': 'depart', 'location': coordinates[0]}}]}]}]}
            if coordinates[0] == [0.0,0.0]:
                data = {'code':'NoRoute','routes':[]}
        elif path == '/api/':
            data = {'features': [{'geometry': {'coordinates': [21.2257,45.7537]},
                                  'properties': {'name': 'Test address', 'city': 'Timișoara'}}]}
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

ThreadingHTTPServer(('0.0.0.0',8000), Handler).serve_forever()
