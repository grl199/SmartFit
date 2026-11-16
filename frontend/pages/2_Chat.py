from datetime import date, datetime, timedelta

import streamlit as st

import api
import auth
import ui

st.set_page_config(page_title="Asistente", page_icon="💬", layout="wide")
ui.inject_css()
auth.require_login()

st.session_state.setdefault("used_photos", set())
convs = api.get("/conversations", limit=60) or []
by_id = {c["id"]: c for c in convs}

# La primera vez se abre la última conversación; después se respeta lo elegido (None = conversación nueva).
if "conv_id" not in st.session_state:
    st.session_state.conv_id = convs[0]["id"] if convs else None
if st.session_state.conv_id is not None and st.session_state.conv_id not in by_id and st.session_state.get("chat_conv") != st.session_state.conv_id:
    st.session_state.conv_id = None  # la conversación ya no existe (p. ej. borrada desde otra pestaña)
conv_id = st.session_state.conv_id
if st.session_state.get("chat_conv", "unset") != conv_id:  # cambió la conversación: cargar sus mensajes
    st.session_state.chat = (api.get(f"/conversations/{conv_id}/messages") or []) if conv_id else []
    st.session_state.chat_conv = conv_id


def open_conversation(cid: int | None) -> None:
    st.session_state.conv_id = cid


def group_of(updated: str) -> str:
    d = datetime.fromisoformat(updated.replace("Z", "+00:00")).astimezone().date()
    today = date.today()
    return ("Hoy" if d == today else "Ayer" if d == today - timedelta(days=1)
            else "Últimos 7 días" if d > today - timedelta(days=7) else "Anteriores")


# ───────── Barra lateral: histórico de conversaciones ─────────
with st.sidebar:
    st.subheader("💬 Conversaciones")
    st.button("➕ Nueva conversación", on_click=open_conversation, args=(None,), width="stretch",
              type="primary" if conv_id is None else "secondary")
    last_group = None
    for c in convs:
        g = group_of(c["updated_at"])
        if g != last_group:
            st.caption(g)
            last_group = g
        st.button(c["title"][:38], key=f"conv_{c['id']}", on_click=open_conversation, args=(c["id"],), width="stretch",
                  type="primary" if c["id"] == conv_id else "secondary", help=f"{c['message_count']} mensajes")
    if not convs:
        st.caption("Tus conversaciones se guardarán aquí para que puedas volver a ellas.")

    if conv_id in by_id:
        with st.expander("⚙ Opciones de esta conversación"):
            new_title = st.text_input("Título", value=by_id[conv_id]["title"], key=f"title_{conv_id}", max_chars=120)
            if st.button("Guardar título", key="save_title") and new_title.strip() and new_title.strip() != by_id[conv_id]["title"]:
                if api.call("PATCH", f"/conversations/{conv_id}", json={"title": new_title}):
                    st.rerun()
            sure = st.checkbox("Confirmo que quiero eliminarla", key=f"sure_{conv_id}")
            if st.button("🗑 Eliminar conversación", disabled=not sure, key="del_conv"):
                if api.delete(f"/conversations/{conv_id}"):
                    st.session_state.conv_id = None
                    st.rerun()

    with st.expander("📷 Adjuntar foto con la cámara"):
        cam = st.camera_input("Código de barras o etiqueta", label_visibility="collapsed")
        st.caption("La foto se adjunta al siguiente mensaje que envíes.")

# ───────── Conversación ─────────
st.title("💬 Asistente")
st.caption(by_id[conv_id]["title"] if conv_id in by_id else "Nueva conversación")
if not st.session_state.chat:
    st.info("Prueba: «¿Cuánta proteína me falta hoy?» · «¿Cómo ha sido mi semana de entreno?» · adjunta la foto de un producto y pregunta qué lleva.")
for m in st.session_state.chat:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m.get("sources"):
            with st.expander("Fuentes"):
                for s in m["sources"]:
                    st.markdown(f"- [{s['title']}]({s['url']})")
        if m.get("tools"):
            st.caption("Herramientas: " + ", ".join(m["tools"]))

prompt = st.chat_input("Pregunta algo o adjunta una foto…", accept_file=True, file_type=["jpg", "jpeg", "png", "webp"])
if prompt:
    text = prompt.text or ""
    image = prompt.files[0] if prompt.files else None
    if image is None and cam and cam.file_id not in st.session_state.used_photos:
        image = cam
        st.session_state.used_photos.add(cam.file_id)

    with st.chat_message("user"):
        st.markdown(text)
        if image:
            st.image(image, width=240)
    with st.chat_message("assistant"):
        with st.spinner("Pensando…"):
            data = {"message": text, **({"conversation_id": str(conv_id)} if conv_id else {})}
            res = api.post("/chat", data=data, files={"image": (image.name, image.getvalue(), image.type)} if image else None)
    if res:
        st.session_state.chat += [{"role": "user", "content": text + (" 📷" if image else "")},
                                  {"role": "assistant", "content": res["reply"], "sources": res["sources"], "tools": res["tools_used"]}]
        st.session_state.conv_id = st.session_state.chat_conv = res["conversation_id"]  # una conversación nueva queda abierta
        st.rerun()  # refresca la lista lateral (título y orden)
