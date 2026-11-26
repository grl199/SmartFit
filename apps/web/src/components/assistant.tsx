"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { apiRequest, apiUpload } from "@/lib/api";

type Props = { token: string };
type Conversation = {
  id: number;
  title: string;
  updated_at: string;
  message_count: number;
};
type Source = { title: string; url: string };
type Message = {
  id?: number;
  role: "user" | "assistant" | "system";
  content: string;
  sources?: Source[];
  tools?: string[];
};
type ChatResponse = {
  reply: string;
  sources: Source[];
  tools_used: string[];
  conversation_id: number;
  transcription?: string | null;
};

function readableError(error: unknown) {
  return error instanceof Error ? error.message : "No se pudo completar la operación.";
}

export function AssistantPanel({ token }: Props) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [audio, setAudio] = useState<File | null>(null);
  const [audioAvailable, setAudioAvailable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  async function refreshConversations(preferredId?: number | null) {
    const items = await apiRequest<Conversation[]>("/conversations?limit=60", { token });
    setConversations(items);
    if (preferredId !== undefined) setSelectedId(preferredId);
    else if (selectedId === null && items.length) setSelectedId(items[0].id);
  }

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([
      apiRequest<Conversation[]>("/conversations?limit=60", { token }),
      apiRequest<{ audio: boolean }>("/chat/capabilities", { token }),
    ])
      .then(([items, capabilities]) => {
        if (!active) return;
        setConversations(items);
        setAudioAvailable(Boolean(capabilities.audio));
        setSelectedId(items[0]?.id ?? null);
      })
      .catch((reason: unknown) => {
        if (active) setError(readableError(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token]);

  useEffect(() => {
    let active = true;
    if (selectedId === null) {
      setMessages([]);
      return () => {
        active = false;
      };
    }
    apiRequest<Message[]>("/conversations/" + selectedId + "/messages", { token })
      .then((items) => {
        if (active) setMessages(items);
      })
      .catch((reason: unknown) => {
        if (active) setError(readableError(reason));
      });
    return () => {
      active = false;
    };
  }, [selectedId, token]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  function startConversation() {
    setSelectedId(null);
    setMessages([]);
    setDraft("");
    setImage(null);
    setAudio(null);
    setError("");
  }

  async function renameConversation(conversation: Conversation) {
    const title = window.prompt("Nuevo título de la conversación", conversation.title);
    if (!title?.trim() || title.trim() === conversation.title) return;
    setError("");
    try {
      await apiRequest("/conversations/" + conversation.id, {
        method: "PATCH",
        token,
        body: { title: title.trim() },
      });
      await refreshConversations(conversation.id);
    } catch (reason) {
      setError(readableError(reason));
    }
  }

  async function deleteConversation(conversation: Conversation) {
    if (!window.confirm("¿Eliminar esta conversación y todos sus mensajes?")) return;
    setError("");
    try {
      await apiRequest("/conversations/" + conversation.id, { method: "DELETE", token });
      const next = conversations.find((item) => item.id !== conversation.id)?.id ?? null;
      setMessages([]);
      await refreshConversations(next);
    } catch (reason) {
      setError(readableError(reason));
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter envía el mensaje; Shift+Enter conserva el salto de línea nativo del textarea.
    // No interceptar Enter mientras el usuario compone texto con un teclado IME.
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    if (!busy && (draft.trim() || image || audio)) {
      event.currentTarget.form?.requestSubmit();
    }
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = draft.trim();
    if ((!text && !image && !audio) || busy) return;

    const form = new FormData();
    form.append("message", text);
    if (selectedId !== null) form.append("conversation_id", String(selectedId));
    if (image) form.append("image", image, image.name);
    if (audio) form.append("audio", audio, audio.name || "nota-de-voz.wav");

    setBusy(true);
    setError("");
    try {
      const response = await apiUpload<ChatResponse>("/chat", form, token);
      const userContent = [
        text,
        image ? "📷 " + image.name : "",
        response.transcription ? "🎙 " + response.transcription : audio ? "🎙 Nota de voz" : "",
      ].filter(Boolean).join("\n");
      setMessages((current) => [
        ...current,
        { role: "user", content: userContent },
        { role: "assistant", content: response.reply, sources: response.sources ?? [], tools: response.tools_used ?? [] },
      ]);
      setSelectedId(response.conversation_id);
      await refreshConversations(response.conversation_id);
      setDraft("");
      setImage(null);
      setAudio(null);
    } catch (reason) {
      setError(readableError(reason));
    } finally {
      setBusy(false);
    }
  }

  const activeConversation = conversations.find((item) => item.id === selectedId);

  return (
    <section className="assistant-panel panel">
      <div className="assistant-heading">
        <div>
          <span className="eyebrow">ASISTENTE PERSONAL</span>
          <h2>Habla con SmartFit</h2>
          <p className="muted">Consulta tu nutrición, entrenamiento y hábitos. Puedes adjuntar fotos o notas de voz.</p>
        </div>
        <button type="button" className="primary-button compact" onClick={startConversation}>Nueva conversación</button>
      </div>

      {error && <div className="dashboard-alert">{error}<button type="button" onClick={() => setError("")}>Cerrar</button></div>}

      <div className="assistant-layout">
        <aside className="assistant-history">
          <div className="assistant-history-title">Conversaciones</div>
          {loading && <p className="muted">Cargando historial…</p>}
          {!loading && conversations.length === 0 && <p className="muted">Tus conversaciones aparecerán aquí.</p>}
          {conversations.map((conversation) => (
            <div className={"assistant-conversation" + (conversation.id === selectedId ? " active" : "")} key={conversation.id}>
              <button type="button" className="assistant-conversation-open" onClick={() => { setSelectedId(conversation.id); setError(""); }}>
                <strong>{conversation.title}</strong>
                <span>{conversation.message_count} mensajes · {new Date(conversation.updated_at).toLocaleDateString("es-ES")}</span>
              </button>
              {conversation.id === selectedId && (
                <div className="assistant-conversation-actions">
                  <button type="button" onClick={() => void renameConversation(conversation)}>Renombrar</button>
                  <button type="button" onClick={() => void deleteConversation(conversation)}>Eliminar</button>
                </div>
              )}
            </div>
          ))}
        </aside>

        <div className="assistant-chat">
          <div className="assistant-chat-title">
            <strong>{activeConversation?.title ?? "Nueva conversación"}</strong>
            <span>Las respuestas pueden contener errores; contrasta las decisiones importantes.</span>
          </div>

          <div className="assistant-thread" role="log" aria-live="polite">
            {messages.length === 0 && !loading && (
              <div className="assistant-empty">
                <span className="assistant-empty-icon">✦</span>
                <strong>¿En qué te ayudo hoy?</strong>
                <p>Prueba con «¿Cuánta proteína me falta?» o «Analiza mi semana de entrenamiento».</p>
              </div>
            )}
            {messages.map((message, index) => (
              <article className={"assistant-message " + message.role} key={message.id ?? index}>
                <span className="assistant-message-role">{message.role === "user" ? "TÚ" : "SMARTFIT IA"}</span>
                <p>{message.content}</p>
                {!!message.sources?.length && (
                  <div className="assistant-sources">
                    <strong>Fuentes</strong>
                    {message.sources.map((source, sourceIndex) => (
                      <a href={source.url} target="_blank" rel="noreferrer" key={source.url + sourceIndex}>{source.title}</a>
                    ))}
                  </div>
                )}
                {!!message.tools?.length && <span className="assistant-tools">Herramientas: {message.tools.join(" · ")}</span>}
              </article>
            ))}
            {busy && <div className="assistant-thinking">SmartFit está preparando una respuesta…</div>}
            <div ref={bottomRef} />
          </div>

          <form className="assistant-compose" onSubmit={sendMessage}>
            {(image || audio) && (
              <div className="assistant-attachments">
                {image && <span>📷 {image.name} <button type="button" onClick={() => setImage(null)} aria-label="Quitar imagen">×</button></span>}
                {audio && <span>🎙 {audio.name} <button type="button" onClick={() => setAudio(null)} aria-label="Quitar audio">×</button></span>}
              </div>
            )}
            <textarea rows={3} maxLength={12000} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={handleComposerKeyDown} placeholder="Escribe tu mensaje… (Enter para enviar, Shift+Enter para nueva línea)" aria-label="Escribe tu mensaje. Enter para enviar, Shift+Enter para nueva línea." />
            <div className="assistant-compose-actions">
              <div className="assistant-upload-actions">
                <label className="assistant-attach">
                  <span>📷 Adjuntar foto</span>
                  <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={(event) => setImage(event.target.files?.[0] ?? null)} />
                </label>
                <label className={"assistant-attach" + (!audioAvailable ? " disabled" : "")} title={audioAvailable ? "Adjunta una nota de voz" : "La transcripción de audio no está configurada en el backend"}>
                  <span>🎙 Nota de voz</span>
                  <input type="file" accept="audio/*" capture="user" disabled={!audioAvailable} onChange={(event) => setAudio(event.target.files?.[0] ?? null)} />
                </label>
              </div>
              <button type="submit" className="primary-button compact" disabled={busy || (!draft.trim() && !image && !audio)}>
                {busy ? "Enviando…" : "Enviar ↗"}
              </button>
            </div>
            {!audioAvailable && <p className="assistant-capability-note">Las notas de voz se activarán al configurar el proveedor de transcripción en el backend.</p>}
          </form>
        </div>
      </div>
    </section>
  );
}
