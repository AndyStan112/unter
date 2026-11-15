"""Serve generated frontend files and only the application's known HTML routes."""
from fastapi.staticfiles import StaticFiles


class FrontendFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        normalized = path.strip('/')
        if normalized in {'reports', 'schedule', 'activity', 'proposals'}:
            path = 'index.html'
        elif normalized in {'ride/passenger', 'ride/driver'}:
            path = 'ride/index.html'
        response = await super().get_response(path, scope)
        # Revalidate entry points and workers; built asset filenames carry a hash.
        if (response.headers.get('content-type', '').startswith('text/html')
                or normalized.endswith('.webmanifest')
                or normalized in {'sw.js', 'ride/sw.js'}):
            response.headers['Cache-Control'] = 'no-cache'
        return response
