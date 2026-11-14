"""Cliente del backend. El token de sesión vive en st.session_state (por usuario/navegador), NUNCA en
una variable global: Streamlit comparte el proceso entre sesiones."""
import os

import httpx
import streamlit as st

BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
_client = httpx.Client(base_url=BASE_URL, timeout=120)
LONG_TIMEOUT = 240  # llamadas que esperan al LLM (onboarding, regenerar objetivos)


def _headers() -> dict:
    tok = st.session_state.get("token")
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def _detail(r: httpx.Response) -> str:
    try:
        d = r.json().get("detail", r.text)
    except ValueError:
        return r.text[:300]
    if isinstance(d, list):  # errores de validación de pydantic
        return "; ".join(f"{'.'.join(map(str, e.get('loc', [])[1:]))}: {e.get('msg', '')}" for e in d)
    return str(d)


def logout(message: str | None = None) -> None:
    for k in ("token", "me", "onboarding_result", "chat", "_foods", "scan_res", "scan_id"):
        st.session_state.pop(k, None)
    if message:
        st.session_state["login_notice"] = message


def call(method: str, path: str, *, timeout: float | None = None, **kw):
    try:
        r = _client.request(method, path, headers=_headers(), timeout=timeout or _client.timeout, **kw)
    except httpx.HTTPError as e:
        st.error(f"No se puede conectar con el backend ({BASE_URL}): {e}")
        return None
    if r.status_code == 401 and st.session_state.get("token"):
        logout("Tu sesión ha caducado. Inicia sesión de nuevo.")
        st.rerun()
    if r.status_code == 403 and _detail(r) == "onboarding_required":
        st.session_state.pop("me", None)
        st.rerun()
    if not r.is_success:
        st.error(f"Error {r.status_code}: {_detail(r)}")
        return None
    return r.json() if r.content else {"ok": True}  # 204: éxito sin cuerpo (None queda reservado para error)


def auth_request(path: str, name: str, password: str) -> tuple[dict | None, str | None]:
    """login / register. Devuelve (datos, mensaje_de_error)."""
    try:
        r = _client.post(path, json={"name": name, "password": password})
    except httpx.HTTPError as e:
        return None, f"No se puede conectar con el backend ({BASE_URL}): {e}"
    return (r.json(), None) if r.is_success else (None, _detail(r))


def get(path, **params): return call("GET", path, params=params or None)
def post(path, **kw): return call("POST", path, **kw)
def put(path, json): return call("PUT", path, json=json)
def delete(path): return call("DELETE", path)


@st.cache_data(ttl=3600, show_spinner=False)
def options() -> dict:
    """Listas cerradas (sexo, objetivo, actividad, experiencia): código -> etiqueta."""
    try:
        return _client.get("/meta/options").json()
    except (httpx.HTTPError, ValueError):
        return {}
