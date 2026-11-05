import os
import httpx
import psycopg
from psycopg.rows import dict_row
from .auth import basic_header


def connect():
    return psycopg.connect(host=os.getenv('DB_HOST', 'postgres'),
                          port=int(os.getenv('DB_PORT', '5432')),
                          dbname=os.environ['DB_NAME'], user=os.environ['DB_USER'],
                          password=os.environ['DB_PASSWORD'], row_factory=dict_row)


async def core(method, path, **kwargs):
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.request(method, os.getenv('CORE_URL', 'http://core:8080') + path,
                                        headers={'Authorization': basic_header()}, **kwargs)
        response.raise_for_status()
        return response.json()


async def core_read(path, params=None):
    """GET from core with the READER login, which core refuses for anything but GET/HEAD.

    The MCP server's only way to reach core: it holds no login that can write.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(os.getenv('CORE_URL', 'http://core:8080') + path, params=params,
                                    headers={'Authorization': basic_header('READER')})
        response.raise_for_status()
        return response.json()
