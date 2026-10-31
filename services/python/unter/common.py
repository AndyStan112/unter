import os
import httpx
import psycopg
from psycopg.rows import dict_row
from .auth import basic_header


def connect():
    return psycopg.connect(host=os.getenv('DB_HOST', 'postgres'),
                          dbname=os.environ['DB_NAME'], user=os.environ['DB_USER'],
                          password=os.environ['DB_PASSWORD'], row_factory=dict_row)


async def core(method, path, **kwargs):
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.request(method, os.getenv('CORE_URL', 'http://core:8080') + path,
                                        headers={'Authorization': basic_header()}, **kwargs)
        response.raise_for_status()
        return response.json()
