import streamlit as st

import api

st.set_page_config(page_title="Asistente", page_icon="💬", layout="wide")
st.title("💬 Asistente")

if "chat" not in st.session_state:
    st.session_state.chat = api.get("/chat/history", limit=50) or []
    st.session_state.used_photos = set()

with st.sidebar:
    st.subheader("📷 Foto")
    cam = st.camera_input("Escanea un código de barras o etiqueta")
    st.caption("La foto se adjunta al siguiente mensaje que envíes.")
    if st.button("🗑 Borrar conversación"):
        api.delete("/chat/history")
        st.session_state.chat = []
        st.rerun()

if not st.session_state.chat:
    st.caption("Prueba: «¿Cuánta proteína me falta hoy?» · «¿Cómo ha sido mi semana?» · adjunta la foto de un producto y pregunta qué lleva.")
for m in st.session_state.chat:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

prompt = st.chat_input("Pregunta algo o adjunta una foto…", accept_file=True, file_type=["jpg", "jpeg", "png", "webp"])
if prompt:
    image = prompt.files[0] if prompt.files else None
    if image is None and cam and cam.file_id not in st.session_state.used_photos:
        image = cam
        st.session_state.used_photos.add(cam.file_id)

    with st.chat_message("user"):
        st.markdown(prompt.text or "")
        if image:
            st.image(image, width=240)
    with st.chat_message("assistant"):
        with st.spinner("Pensando…"):
            res = api.post("/chat", data={"message": prompt.text or ""},
                           files={"image": (image.name, image.getvalue(), image.type)} if image else None)
        if res:
            st.markdown(res["reply"])
            if res["sources"]:
                with st.expander("Fuentes"):
                    for s in res["sources"]:
                        st.markdown(f"- [{s['title']}]({s['url']})")
            if res["tools_used"]:
                st.caption("Herramientas: " + ", ".join(res["tools_used"]))
            st.session_state.chat += [{"role": "user", "content": (prompt.text or "") + (" 📷" if image else "")},
                                      {"role": "assistant", "content": res["reply"]}]
