"""User-triggered Photon search, cached and throttled. No client-selected upstream URL."""
import asyncio
import os
import time
from collections import OrderedDict
import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()
cache = OrderedDict()
lock = asyncio.Lock()
last_request = 0.0


@router.get('/places')
async def places(q: str = Query(min_length=3, max_length=200)):
    global last_request
    query = ' '.join(q.split())
    if len(query) < 3:
        raise HTTPException(422, 'Enter at least three characters')
    async with lock:
        saved = cache.get(query.casefold())
        if saved and time.monotonic() - saved[0] < 86400:
            return saved[1]
        if time.monotonic() - last_request < 1:
            raise HTTPException(429, 'Please wait a moment before searching again')
        last_request = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.get(os.getenv('GEOCODING_URL', 'https://photon.komoot.io').rstrip('/') + '/api/',
                    params={'q': query, 'lat': 45.7537, 'lon': 21.2257, 'limit': 5},
                    headers={'User-Agent': 'Unter/1.0 (https://github.com/AndyStan112/unter)'})
                response.raise_for_status()
                results = []
                for feature in response.json()['features'][:5]:
                    lon, lat = feature['geometry']['coordinates'][:2]
                    properties = feature['properties']
                    label = ', '.join(dict.fromkeys(str(properties[k]) for k in
                        ('name', 'street', 'housenumber', 'city', 'country') if properties.get(k)))
                    if -90 <= lat <= 90 and -180 <= lon <= 180:
                        results.append({'lat': lat, 'lon': lon, 'label': label[:250]})
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise HTTPException(503, 'Address search unavailable. Choose a zone or map pin.') from None
        if len(cache) >= 256:
            cache.popitem(last=False)
        cache[query.casefold()] = (time.monotonic(), results)
        return results
