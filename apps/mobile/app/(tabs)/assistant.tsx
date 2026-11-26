import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Alert, Linking, Pressable, Text, View } from "react-native";
import { api, apiUpload } from "@/lib/api";
import { useAuth } from "@/auth/AuthProvider";
import { AppButton, ErrorMessage, Field, Muted, PageTitle, Panel, Screen, SectionTitle } from "@/components/ui";
import { colors } from "@/theme";

type Conversation = { id: number; title: string; updated_at: string; message_count: number };
type Source = { title: string; url: string };
type Message = {
  id?: number; role: "user" | "assistant" | "system"; content: string;
  sources?: Source[]; tools?: string[];
};
type ChatResponse = {
  reply: string; sources: Source[]; tools_used: string[]; conversation_id: number;
  transcription?: string | null;
};

export default function AssistantScreen() {
  const { token } = useAuth();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refreshConversations = useCallback(async (preferredId?: number | null) => {
    if (!token) return;
    const items = await api<Conversation[]>("/conversations?limit=60", token);
    setConversations(items);
    if (preferredId !== undefined) setSelectedId(preferredId);
    else if (selectedId === null && items.length > 0) setSelectedId(items[0].id);
  }, [token, selectedId]);

  useEffect(() => {
    let active = true;
    async function loadHistory() {
      if (!token) return;
      setLoading(true);
      setError("");
      try {
        const [items] = await Promise.all([
          api<Conversation[]>("/conversations?limit=60", token),
          api<{ audio: boolean }>("/chat/capabilities", token),
        ]);
        if (active) {
          setConversations(items);
          setSelectedId(current => current ?? items[0]?.id ?? null);
        }
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : "No se pudo cargar el historial.");
      } finally {
        if (active) setLoading(false);
      }
    }
    void loadHistory();
    return () => { active = false; };
  }, [token]);

  useEffect(() => {
    let active = true;
    if (!token || selectedId === null) {
      setMessages([]);
      return () => { active = false; };
    }
    setLoading(true);
    api<Message[]>("/conversations/" + selectedId + "/messages", token)
      .then(items => { if (active) setMessages(items); })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "No se pudieron cargar los mensajes."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [selectedId, token]);

  function startConversation() {
    setSelectedId(null);
    setMessages([]);
    setDraft("");
    setError("");
  }

  function deleteConversation(conversation: Conversation) {
    Alert.alert("Eliminar conversación", "Se eliminarán todos sus mensajes. Esta acción no se puede deshacer.", [
      { text: "Cancelar", style: "cancel" },
      { text: "Eliminar", style: "destructive", onPress: () => {
        void (async () => {
          if (!token) return;
          setBusy(true);
          try {
            await api("/conversations/" + conversation.id, token, { method: "DELETE" });
            const next = conversations.find(item => item.id !== conversation.id)?.id ?? null;
            setMessages([]);
            await refreshConversations(next);
          } catch (reason) {
            setError(reason instanceof Error ? reason.message : "No se pudo eliminar la conversación.");
          } finally {
            setBusy(false);
          }
        })();
      } },
    ]);
  }

  async function sendMessage() {
    const message = draft.trim();
    if (!token || !message || busy) return;
    setBusy(true);
    setError("");
    const form = new FormData();
    form.append("message", message);
    if (selectedId !== null) form.append("conversation_id", String(selectedId));
    try {
      const response = await apiUpload<ChatResponse>("/chat", form, token);
      const outgoing: Message = { role: "user", content: message };
      const incoming: Message = {
        role: "assistant", content: response.reply,
        sources: response.sources ?? [], tools: response.tools_used ?? [],
      };
      setMessages(current => [...current, outgoing, incoming]);
      setSelectedId(response.conversation_id);
      setDraft("");
      await refreshConversations(response.conversation_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo enviar el mensaje.");
    } finally {
      setBusy(false);
    }
  }

  const activeConversation = conversations.find(item => item.id === selectedId);

  return <Screen>
    <PageTitle eyebrow="Asistente personal" title="Habla con SmartFit" subtitle="Pregunta sobre tu nutrición, entrenamiento, hábitos y evolución. El asistente utiliza la información disponible en tu cuenta." />
    <AppButton title="＋ Nueva conversación" onPress={startConversation} variant="secondary" />
    <ErrorMessage message={error} />
    <SectionTitle title="Historial" action={conversations.length + " conversaciones"} />
    {loading && conversations.length === 0 ? <ActivityIndicator color={colors.accent} /> : null}
    {conversations.length === 0 ? <Muted>Tus conversaciones aparecerán aquí. Empieza escribiendo una pregunta.</Muted> :
      <View style={{ gap: 8 }}>
        {conversations.map(item => <View key={item.id} style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Pressable onPress={() => { setSelectedId(item.id); setError(""); }} style={{
            flex: 1, padding: 12, borderRadius: 14, borderWidth: 1,
            borderColor: item.id === selectedId ? colors.accent : colors.border,
            backgroundColor: item.id === selectedId ? colors.accentDark : colors.surface,
          }}>
            <Text numberOfLines={1} style={{ color: colors.text, fontWeight: "800" }}>{item.title}</Text>
            <Muted>{item.message_count} mensajes · {new Date(item.updated_at).toLocaleDateString("es-ES")}</Muted>
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel={"Eliminar " + item.title} onPress={() => deleteConversation(item)} hitSlop={8} style={{ padding: 8 }}>
            <Text style={{ color: colors.danger, fontSize: 18 }}>×</Text>
          </Pressable>
        </View>)}
      </View>
    }
    <SectionTitle title={activeConversation?.title ?? "Nueva conversación"} action="SMARTFIT IA" />
    {messages.length === 0 && !loading ? <Panel style={{ alignItems: "center", paddingVertical: 24 }}>
      <Text style={{ color: colors.accent, fontSize: 26 }}>✦</Text>
      <Text style={{ color: colors.text, fontSize: 17, fontWeight: "800" }}>¿En qué te ayudo hoy?</Text>
      <Muted>Prueba con «¿Cuánta proteína me falta?» o «Analiza mi semana de entrenamiento».</Muted>
    </Panel> : null}
    <View style={{ gap: 10 }}>
      {messages.map((message, index) => <Panel key={message.id ?? index} style={{
        backgroundColor: message.role === "user" ? colors.accentDark : colors.surface,
        borderColor: message.role === "user" ? colors.accent : colors.border,
        marginLeft: message.role === "user" ? 22 : 0,
        marginRight: message.role === "user" ? 0 : 22,
      }}>
        <Text style={{ color: colors.accent, fontSize: 10, fontWeight: "900", letterSpacing: 1 }}>{message.role === "user" ? "TÚ" : "SMARTFIT IA"}</Text>
        <Text selectable style={{ color: colors.text, fontSize: 14, lineHeight: 21 }}>{message.content}</Text>
        {!!message.sources?.length && <View style={{ gap: 6 }}>
          <Muted>Fuentes</Muted>
          {message.sources.map((source, sourceIndex) => <Text key={source.url + sourceIndex} onPress={() => void Linking.openURL(source.url)} style={{ color: colors.accent, textDecorationLine: "underline" }}>{source.title}</Text>)}
        </View>}
        {!!message.tools?.length && <Muted>Herramientas: {message.tools.join(" · ")}</Muted>}
      </Panel>)}
      {busy ? <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}><ActivityIndicator color={colors.accent} /><Muted>SmartFit está preparando una respuesta…</Muted></View> : null}
    </View>
    <Panel>
      <Field label="Tu mensaje" value={draft} onChangeText={setDraft} multiline numberOfLines={4} maxLength={12000} placeholder="Escribe tu pregunta…" />
      <Muted>También podrás consultar y continuar las conversaciones guardadas en la web.</Muted>
      <AppButton title={busy ? "Enviando…" : "Enviar mensaje ↗"} onPress={() => void sendMessage()} loading={busy} disabled={!draft.trim()} />
    </Panel>
    <Muted>Las respuestas de IA pueden contener errores. Contrasta las decisiones importantes y consulta a un profesional cuando corresponda.</Muted>
  </Screen>;
}
