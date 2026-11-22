from types import SimpleNamespace as NS
from unittest.mock import patch

from conftest import onboard_new_user, register


class FakeLLM:
    """Cliente Chat Completions simulado: guarda los mensajes que recibe y responde con texto fijo."""
    def __init__(self):
        self.calls = []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw["messages"])
        return NS(choices=[NS(message=NS(content=f"Respuesta {len(self.calls)}", tool_calls=None))])

    def sent_text(self, i=-1):
        return "\n".join(str(m.get("content")) for m in self.calls[i])


def send(client, h, text, conv=None, llm=None):
    data = {"message": text, **({"conversation_id": str(conv)} if conv else {})}
    with patch("app.agent.agent.get_chat_client", lambda: llm):
        return client.post("/chat", data=data, headers=h)


def test_title_from():
    from app.agent.agent import title_from
    assert title_from("  ¿Cuánta   proteína me falta? ") == "¿Cuánta proteína me falta?"
    assert title_from("x" * 100).endswith("…") and len(title_from("x" * 100)) == 58
    assert title_from("📷") == "Foto"


def test_conversations_keep_independent_histories(client, onboarded):
    h, llm = onboarded["headers"], FakeLLM()
    a = send(client, h, "Hablemos de mi cena de ayer", llm=llm).json()
    assert a["conversation_title"] == "Hablemos de mi cena de ayer" and a["reply"] == "Respuesta 1"
    send(client, h, "¿y de postre?", conv=a["conversation_id"], llm=llm)
    assert "Hablemos de mi cena de ayer" in llm.sent_text() and "Respuesta 1" in llm.sent_text()      # misma conversación: recuerda
    b = send(client, h, "Plan de entreno ZEBRA42", llm=llm).json()
    assert b["conversation_id"] != a["conversation_id"]
    assert "cena de ayer" not in llm.sent_text()                                                      # otra conversación: no mezcla
    # volver a la primera sin perder nada
    send(client, h, "¿qué decíamos?", conv=a["conversation_id"], llm=llm)
    assert "cena de ayer" in llm.sent_text() and "ZEBRA42" not in llm.sent_text()
    # histórico: más reciente primero, con recuento
    lst = client.get("/conversations", headers=h).json()
    assert [c["id"] for c in lst] == [a["conversation_id"], b["conversation_id"]]
    assert [c["message_count"] for c in lst] == [6, 2]
    msgs = client.get(f"/conversations/{a['conversation_id']}/messages", headers=h).json()
    assert [m["role"] for m in msgs] == ["user", "assistant"] * 3 and msgs[0]["content"] == "Hablemos de mi cena de ayer"


def test_rename_delete_and_validation(client, onboarded):
    h, llm = onboarded["headers"], FakeLLM()
    c = send(client, h, "Primera", llm=llm).json()["conversation_id"]
    r = client.patch(f"/conversations/{c}", json={"title": "  Dieta de volumen  "}, headers=h)
    assert r.status_code == 200 and r.json()["title"] == "Dieta de volumen" and r.json()["message_count"] == 2
    send(client, h, "otra", conv=c, llm=llm)
    assert client.get("/conversations", headers=h).json()[0]["title"] == "Dieta de volumen"           # el título manual no se pisa
    assert client.patch(f"/conversations/{c}", json={"title": ""}, headers=h).status_code == 422
    assert client.delete(f"/conversations/{c}", headers=h).status_code == 204
    assert client.get(f"/conversations/{c}/messages", headers=h).status_code == 404
    assert c not in [x["id"] for x in client.get("/conversations", headers=h).json()]
    assert client.post("/chat", data={"message": ""}, headers=h).status_code == 422


def test_conversations_are_private(client, onboarded):
    h, llm = onboarded["headers"], FakeLLM()
    c = send(client, h, "Algo privado", llm=llm).json()["conversation_id"]
    other = onboard_new_user(client)["headers"]
    assert client.get(f"/conversations/{c}/messages", headers=other).status_code == 404
    assert client.patch(f"/conversations/{c}", json={"title": "x"}, headers=other).status_code == 404
    assert client.delete(f"/conversations/{c}", headers=other).status_code == 404
    assert send(client, other, "intruso", conv=c, llm=llm).status_code == 404
    assert client.get("/conversations", headers=other).json() == []
    assert send(client, register(client)["headers"], "hola", llm=llm).status_code == 403             # sin onboarding


def test_legacy_messages_are_grouped_by_migration(client, onboarded):
    from sqlalchemy import select
    from app.db import SessionLocal, engine
    from app.migrations import run_migrations
    from app.models import ChatMessage, Conversation
    uid = onboarded["id"]
    with SessionLocal() as db:
        db.add_all([ChatMessage(user_id=uid, role="user", content="mensaje antiguo"),
                    ChatMessage(user_id=uid, role="assistant", content="respuesta antigua")])
        db.commit()
    for _ in range(2):                                               # idempotente: la segunda pasada no duplica nada
        with engine.begin() as conn:
            run_migrations(conn)
    with SessionLocal() as db:
        convs = db.scalars(select(Conversation).where(Conversation.user_id == uid, Conversation.title == "Conversación anterior")).all()
        assert len(convs) == 1
        msgs = db.scalars(select(ChatMessage).where(ChatMessage.user_id == uid)).all()
        assert len(msgs) == 2 and all(m.conversation_id == convs[0].id for m in msgs)
    assert client.get("/conversations", headers=onboarded["headers"]).json()[0]["title"] == "Conversación anterior"


def test_account_deletion_removes_conversations(client, onboarded):
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models import ChatMessage, Conversation
    send(client, onboarded["headers"], "hola", llm=FakeLLM())
    assert client.request("DELETE", "/auth/me", headers=onboarded["headers"], json={"password": onboarded["password"]}).status_code == 204
    with SessionLocal() as db:
        assert db.scalar(select(Conversation).where(Conversation.user_id == onboarded["id"])) is None
        assert db.scalar(select(ChatMessage).where(ChatMessage.user_id == onboarded["id"])) is None


def test_voice_note_is_transcribed_and_sent_as_user_message(client, onboarded):
    llm = FakeLLM()
    with patch("app.routers.chat.transcribe_audio", return_value="He comido arroz con pollo y verduras") as transcribe, \
         patch("app.agent.agent.get_chat_client", lambda: llm):
        response = client.post(
            "/chat",
            headers=onboarded["headers"],
            data={"message": "Ayúdame con esta receta"},
            files={"audio": ("nota.wav", b"fake-audio", "audio/wav")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["transcription"] == "He comido arroz con pollo y verduras"
    assert "arroz con pollo y verduras" in llm.sent_text()
    messages = client.get(
        f"/conversations/{payload['conversation_id']}/messages",
        headers=onboarded["headers"],
    ).json()
    assert "arroz con pollo y verduras" in messages[0]["content"]
    transcribe.assert_called_once()
