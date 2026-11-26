import React, { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Alert, Image, Linking, Platform, Pressable, Text, View } from "react-native";
import * as ImagePicker from "expo-image-picker";
import { AudioModule, RecordingPresets, setAudioModeAsync, useAudioRecorder, useAudioRecorderState } from "expo-audio";
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
  const [photo, setPhoto] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [audioUri, setAudioUri] = useState<string | null>(null);
  const [audioAvailable, setAudioAvailable] = useState(false);
  const audioRecorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const audioRecorderState = useAudioRecorderState(audioRecorder, 400);
  const wasRecording = useRef(false);
  const wasRecording = useRef(false);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameTitle, setRenameTitle] = useState("");
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
    if (wasRecording.current && !audioRecorderState.isRecording && !audioUri && audioRecorder.uri) {
      setAudioUri(audioRecorder.uri);
      void setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
    }
    wasRecording.current = audioRecorderState.isRecording;
  }, [audioRecorderState.isRecording, audioRecorder, audioUri]);

  useEffect(() => {
    let active = true;
    async function loadHistory() {
      if (!token) return;
      setLoading(true);
      setError("");
      try {
        const [items, capabilities] = await Promise.all([
          api<Conversation[]>("/conversations?limit=60", token),
          api<{ audio: boolean }>("/chat/capabilities", token),
        ]);
        if (active) {
          setConversations(items);
          setAudioAvailable(Boolean(capabilities.audio));
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

  useEffect(() => {
    if (wasRecording.current && !audioRecorderState.isRecording && !audioUri && audioRecorder.uri) {
      setAudioUri(audioRecorder.uri);
    }
    wasRecording.current = audioRecorderState.isRecording;
  }, [audioRecorderState.isRecording, audioRecorder, audioUri]);

  function startConversation() {
    setSelectedId(null);
    setMessages([]);
    setDraft("");
    setPhoto(null);
    setAudioUri(null);
    setError("");
  }

  async function choosePhoto(source: "camera" | "library") {
    setError("");
    try {
      if (source === "camera") {
        const permission = await ImagePicker.requestCameraPermissionsAsync();
        if (!permission.granted) {
          setError("Necesitas permitir el acceso a la cámara para adjuntar una foto.");
          return;
        }
      } else {
        const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
        if (!permission.granted) {
          setError("Necesitas permitir el acceso a tus fotos para adjuntar una imagen.");
          return;
        }
      }
      const options: ImagePicker.ImagePickerOptions = {
        mediaTypes: ["images"], allowsEditing: true, quality: 0.85,
      };
      const result = source === "camera"
        ? await ImagePicker.launchCameraAsync(options)
        : await ImagePicker.launchImageLibraryAsync(options);
      if (!result.canceled && result.assets[0]) setPhoto(result.assets[0]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo seleccionar la foto.");
    }
  }

  async function startVoiceNote() {
    if (!audioAvailable) {
      setError("La transcripción de audio no está configurada en el servidor.");
      return;
    }
    setError("");
    try {
      const permission = await AudioModule.requestRecordingPermissionsAsync();
      if (!permission.granted) {
        setError("Necesitas permitir el acceso al micrófono para grabar una nota de voz.");
        return;
      }
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
      await audioRecorder.prepareToRecordAsync();
      setAudioUri(null);
      audioRecorder.record({ forDuration: 120 });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo iniciar la grabación.");
    }
  }

  async function stopVoiceNote() {
    try {
      await audioRecorder.stop();
      setAudioUri(audioRecorder.uri);
      await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo finalizar la grabación.");
    }
  }

  async function saveRename(conversation: Conversation) {
    if (!token || !renameTitle.trim() || renameTitle.trim().length > 120) {
      setError("El título debe tener entre 1 y 120 caracteres.");
      return;
    }
    setBusy(true); setError("");
    try {
      await api("/conversations/" + conversation.id, token, { method: "PATCH", body: { title: renameTitle.trim() } });
      setRenamingId(null);
      setRenameTitle("");
      await refreshConversations(conversation.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo renombrar la conversación.");
    } finally { setBusy(false); }
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
    if (!token || (!message && !photo && !audioUri) || busy) return;
    setBusy(true);
    setError("");
    const form = new FormData();
    form.append("message", message);
    if (selectedId !== null) form.append("conversation_id", String(selectedId));
    try {
      if (photo) {
        if (Platform.OS === "web") {
          const response = await fetch(photo.uri);
          const blob = await response.blob();
          form.append("image", blob, photo.fileName ?? "foto.jpg");
        } else {
          form.append("image", {
            uri: photo.uri, name: photo.fileName ?? "foto.jpg",
            type: photo.mimeType ?? "image/jpeg",
          } as unknown as Blob);
        }
      }
      if (audioUri) {
        if (Platform.OS === "web") {
          const response = await fetch(audioUri);
          const blob = await response.blob();
          form.append("audio", blob, "nota-de-voz.webm");
        } else {
          form.append("audio", {
            uri: audioUri, name: "nota-de-voz.m4a", type: "audio/mp4",
          } as unknown as Blob);
        }
      }
      const response = await apiUpload<ChatResponse>("/chat", form, token);
      const userContent = [
        message,
        photo ? "📷 " + (photo.fileName ?? "Foto adjunta") : "",
        response.transcription ? "🎙 " + response.transcription : audioUri ? "🎙 Nota de voz" : "",
      ].filter(Boolean).join("\\n");
      const outgoing: Message = { role: "user", content: userContent };
      const incoming: Message = {
        role: "assistant", content: response.reply,
        sources: response.sources ?? [], tools: response.tools_used ?? [],
      };
      setMessages(current => [...current, outgoing, incoming]);
      setSelectedId(response.conversation_id);
      setDraft("");
      setPhoto(null);
      setAudioUri(null);
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
          <View style={{ flex: 1, gap: 5 }}>
            <Pressable onPress={() => { setSelectedId(item.id); setError(""); }} style={{
              padding: 12, borderRadius: 14, borderWidth: 1,
              borderColor: item.id === selectedId ? colors.accent : colors.border,
              backgroundColor: item.id === selectedId ? colors.accentDark : colors.surface,
            }}>
              <Text numberOfLines={1} style={{ color: colors.text, fontWeight: "800" }}>{item.title}</Text>
              <Muted>{item.message_count} mensajes · {new Date(item.updated_at).toLocaleDateString("es-ES")}</Muted>
            </Pressable>
            {renamingId === item.id ? <View style={{ gap: 6 }}>
              <Field label="Nuevo título" value={renameTitle} onChangeText={setRenameTitle} maxLength={120} />
              <View style={{ flexDirection: "row", gap: 7 }}>
                <View style={{ flex: 1 }}><AppButton title="Guardar título" onPress={() => void saveRename(item)} loading={busy} /></View>
                <View style={{ flex: 1 }}><AppButton title="Cancelar" variant="quiet" onPress={() => setRenamingId(null)} /></View>
              </View>
            </View> : <Text onPress={() => { setRenamingId(item.id); setRenameTitle(item.title); }} style={{ color: colors.accent, fontSize: 12, fontWeight: "800", paddingLeft: 4 }}>Renombrar</Text>}
          </View>
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
      {photo ? <View style={{ gap: 6 }}>
        <Image source={{ uri: photo.uri }} style={{ width: "100%", height: 170, borderRadius: 12, backgroundColor: colors.surfaceRaised }} resizeMode="cover" />
        <Text onPress={() => setPhoto(null)} style={{ color: colors.danger, fontWeight: "800", padding: 5 }}>Quitar foto adjunta</Text>
      </View> : null}
      {audioUri ? <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
        <Muted>🎙 Nota de voz preparada</Muted>
        <Text onPress={() => setAudioUri(null)} style={{ color: colors.danger, fontWeight: "800", padding: 5 }}>Quitar audio</Text>
      </View> : null}
      <View style={{ flexDirection: "row", gap: 8 }}>
        <View style={{ flex: 1 }}><AppButton title="Hacer foto" variant="secondary" onPress={() => void choosePhoto("camera")} loading={busy} /></View>
        <View style={{ flex: 1 }}><AppButton title="Galería" variant="secondary" onPress={() => void choosePhoto("library")} loading={busy} /></View>
      </View>
      {audioAvailable ? <>
        <View style={{ flexDirection: "row", gap: 8 }}>
          <View style={{ flex: 1 }}><AppButton title={audioRecorderState.isRecording ? "Grabando…" : "Grabar nota de voz"} variant="secondary" onPress={() => void startVoiceNote()} loading={busy} disabled={audioRecorderState.isRecording} /></View>
          <View style={{ flex: 1 }}><AppButton title="Detener grabación" variant="quiet" onPress={() => void stopVoiceNote()} disabled={!audioRecorderState.isRecording} /></View>
        </View>
        {audioRecorderState.isRecording ? <Muted>Grabando {Math.floor(audioRecorderState.durationMillis / 1000)} s · máximo 120 s</Muted> : null}
      </> : <Muted>El proveedor de transcripción de audio no está configurado en el servidor.</Muted>}
      <Muted>Las fotos y notas de voz se envían junto a tu mensaje a SmartFit IA.</Muted>
      <AppButton title={busy ? "Enviando…" : "Enviar mensaje ↗"} onPress={() => void sendMessage()} loading={busy} disabled={!draft.trim() && !photo && !audioUri} />
    </Panel>
    <Muted>Las respuestas de IA pueden contener errores. Contrasta las decisiones importantes y consulta a un profesional cuando corresponda.</Muted>
  </Screen>;
}
