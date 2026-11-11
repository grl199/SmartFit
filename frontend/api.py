"""Cliente mínimo del backend. Si migras el frontend (React/Flutter), este contrato HTTP es lo único que importa."""
import os

import httpx
import streamlit as st

BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
API_TOKEN = os.getenv("API_TOKEN")

_client = httpx.Client(base_url=BASE_URL, timeout=120,
                       headers={"X-API-Key": API_TOKEN} if API_TOKEN else {})


def call(method: str, path: str, **kw):
    try:
        r = _client.request(method, path, **kw)
        r.raise_for_status()
        return r.json() if r.content else None
    except httpx.HTTPStatusError as e:
        st.error(f"Error {e.response.status_code}: {e.response.text[:300]}")
    except httpx.HTTPError as e:
        st.error(f"No se puede conectar con el backend ({BASE_URL}): {e}")
    return None


def get(path, **params): return call("GET", path, params=params or None)
def post(path, **kw): return call("POST", path, **kw)
def put(path, json): return call("PUT", path, json=json)
def delete(path): return call("DELETE", path)
