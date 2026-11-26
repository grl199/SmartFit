import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Alert, AppState, Text, View } from "react-native";
import * as Location from "expo-location";
import { useKeepAwake } from "expo-keep-awake";
import { WebView } from "react-native-webview";
import { api } from "@/lib/api";
import { localDateISO } from "@/lib/format";
import { AppButton, ErrorMessage, Field, Muted, Panel, SectionTitle } from "@/components/ui";
import { colors } from "@/theme";

type Category = "walking" | "running";
type RoutePoint = {
  lat: number; lng: number; altitude_m: number | null;
  accuracy_m: number | null; recorded_at: string;
};
type RemoteDraft = {
  client_id: string; kind: string; category: Category; performed_on?: string | null;
  started_at: string; points: RoutePoint[]; point_count: number; synced_point_count?: number;
};
type LocalDraft = RemoteDraft & { owner: string };
type Props = { token: string; owner: string; visible: boolean; onSaved: () => void };
type RouteStats = { distanceKm: number; elevationM: number; gapMs: number; activeMs: number };

const MAX_POINTS = 10000;
const LOCAL_PERSIST_MS = 5000;
const SYNC_BATCH = 500;
const GAP_MS = 120000;
const MAX_ACCURACY_M = 50;
const MAX_SPEED_MS = 12;
const EARTH_RADIUS_KM = 6371.0088;

function distanceKm(a: RoutePoint, b: RoutePoint) {
  const rad = (value: number) => value * Math.PI / 180;
  const dLat = rad(b.lat - a.lat);
  const dLng = rad(b.lng - a.lng);
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return EARTH_RADIUS_KM * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(Math.max(0, 1 - x)));
}

function acceptFix(previous: RoutePoint | undefined, next: RoutePoint) {
  if (next.accuracy_m != null && next.accuracy_m > MAX_ACCURACY_M) return false;
  if (!previous) return true;
  const seconds = (Date.parse(next.recorded_at) - Date.parse(previous.recorded_at)) / 1000;
  if (!(seconds > 0)) return false;
  const km = distanceKm(previous, next);
  if (km < 0.005 && seconds < 5) return false;
  return km * 1000 / seconds <= MAX_SPEED_MS;
}

function routeStats(points: RoutePoint[], startMs: number | null, endMs: number | null): RouteStats {
  let distance = 0;
  let elevation = 0;
  let gap = 0;
  for (let i = 1; i < points.length; i++) {
    const delta = Date.parse(points[i].recorded_at) - Date.parse(points[i - 1].recorded_at);
    if (delta > GAP_MS) { gap += delta; continue; }
    distance += distanceKm(points[i - 1], points[i]);
    const before = points[i - 1].altitude_m;
    const after = points[i].altitude_m;
    if (before != null && after != null) elevation += Math.max(0, after - before);
  }
  if (points.length && startMs != null && Date.parse(points[0].recorded_at) - startMs > GAP_MS) {
    gap += Date.parse(points[0].recorded_at) - startMs;
  }
  if (points.length && endMs != null) {
    const tail = endMs - Date.parse(points[points.length - 1].recorded_at);
    if (tail > GAP_MS) gap += tail;
  }
  const total = startMs != null && endMs != null ? Math.max(0, endMs - startMs) : 0;
  return {
    distanceKm: distance,
    elevationM: elevation,
    gapMs: gap,
    activeMs: Math.max(0, total - gap),
  };
}

function durationText(ms: number) {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  const two = (value: number) => String(value).padStart(2, "0");
  return hours ? two(hours) + ":" + two(minutes) + ":" + two(rest) : two(minutes) + ":" + two(rest);
}

function paceText(ms: number, km: number) {
  if (km < 0.02 || ms <= 0) return "—";
  const total = Math.round(ms / 60000 / km);
  return Math.floor(total / 60) + ":" + String(total % 60).padStart(2, "0") + " /km";
}

const ROUTE_MAP_HTML = `<!doctype html>
<html><head>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
html,body,#map{margin:0;padding:0;width:100%;height:100%;background:#0e1612}
.leaflet-container{background:#0e1612;font:12px sans-serif}
.leaflet-control-attribution{font-size:9px!important}
</style>
</head><body>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
(function(){
  if(!window.L){document.body.innerHTML="<div style='color:#fff;padding:20px;font:14px sans-serif'>No se pudo cargar el mapa. Comprueba la conexión a internet.</div>";return;}
  var map=L.map("map",{zoomControl:true,attributionControl:true}).setView([40.4168,-3.7038],13);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{
    maxZoom:19,
    attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
  }).addTo(map);
  var routeLayer=L.featureGroup().addTo(map);
  window.setSmartFitRoute=function(points){
    routeLayer.clearLayers();
    if(!Array.isArray(points)||!points.length)return;
    if(points.length===1){
      map.setView(points[0],16);
      L.circleMarker(points[0],{radius:7,color:"#ffffff",weight:2,fillColor:"#63e6a6",fillOpacity:1}).addTo(routeLayer);
      return;
    }
    var line=L.polyline(points,{color:"#16a86b",weight:5,opacity:.95,lineJoin:"round"}).addTo(routeLayer);
    L.circleMarker(points[0],{radius:6,color:"#ffffff",weight:2,fillColor:"#237bd1",fillOpacity:1}).bindTooltip("Inicio").addTo(routeLayer);
    L.circleMarker(points[points.length-1],{radius:7,color:"#ffffff",weight:2,fillColor:"#16a86b",fillOpacity:1}).bindTooltip("Fin").addTo(routeLayer);
    map.fitBounds(line.getBounds().pad(.16),{maxZoom:17});
  };
  window.setTimeout(function(){map.invalidateSize();},250);
})();
</script></body></html>`;

export function RouteMapPreview({ points, initiallyVisible = false, height = 220 }: {
  points: RoutePoint[]; initiallyVisible?: boolean; height?: number;
}) {
  const [visible,setVisible] = useState(initiallyVisible);
  const [failed,setFailed] = useState(false);
  const webViewRef = useRef<any>(null);
  const MapWebView = WebView as unknown as React.ComponentType<any>;
  const loadedRef = useRef(false);
  const pointsRef = useRef(points);
  pointsRef.current = points;

  const pushPoints = useCallback(() => {
    if (!loadedRef.current || !webViewRef.current) return;
    const payload = JSON.stringify(pointsRef.current.map(point => [point.lat,point.lng]));
    webViewRef.current.injectJavaScript("window.setSmartFitRoute && window.setSmartFitRoute("+payload+"); true;");
  }, []);

  useEffect(() => {
    if (visible) pushPoints();
  }, [points,visible,pushPoints]);

  if (!visible) {
    return <AppButton title="Ver mapa del recorrido" variant="quiet" onPress={() => setVisible(true)} disabled={points.length === 0}/>;
  }
  if (failed) {
    return <View style={{height,alignItems:"center",justifyContent:"center",gap:8,backgroundColor:colors.surfaceRaised,borderRadius:12,padding:14}}>
      <Muted>No se pudo cargar el mapa de OpenStreetMap.</Muted>
      <AppButton title="Reintentar mapa" variant="quiet" onPress={() => {setFailed(false);loadedRef.current=false;}}/>
    </View>;
  }
  return <View style={{height,overflow:"hidden",borderRadius:12,borderWidth:1,borderColor:colors.border}}>
    <MapWebView
      ref={webViewRef}
      source={{html:ROUTE_MAP_HTML,baseUrl:"https://smartfit.local"}}
      originWhitelist={["*"]}
      javaScriptEnabled
      domStorageEnabled
      scrollEnabled={false}
      nestedScrollEnabled={false}
      onLoadEnd={() => {loadedRef.current=true;pushPoints();}}
      onError={() => setFailed(true)}
      style={{flex:1,backgroundColor:colors.surface}}
    />
    <View style={{position:"absolute",right:8,top:8}}>
      <AppButton title="Ocultar mapa" variant="secondary" onPress={() => setVisible(false)}/>
    </View>
  </View>;
}

function KeepAwakeWhileTracking() {
  useKeepAwake("smartfit-cardio-gps");
  return null;
}

export function CardioGpsTracker({ token, owner, visible, onSaved }: Props) {
  const [category, setCategory] = useState<Category>("running");
  const [name, setName] = useState("Correr");
  const [date, setDate] = useState(localDateISO());
  const [points, setPoints] = useState<RoutePoint[]>([]);
  const [status, setStatus] = useState<"idle" | "tracking" | "finished">("idle");
  const [elapsed, setElapsed] = useState(0);
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [signalAge, setSignalAge] = useState<number | null>(null);
  const [syncState, setSyncState] = useState<"idle" | "syncing" | "ok" | "error">("idle");
  const [recovered, setRecovered] = useState<RemoteDraft | null>(null);
  const [steps, setSteps] = useState("");
  const [heartRate, setHeartRate] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const pointsRef = useRef<RoutePoint[]>([]);
  const lastLocalPersistRef = useRef(0);
  const localDraftKey = useMemo(() => "smartfit.activeRun.v1." + owner, [owner]);
  const startedAtRef = useRef<number | null>(null);
  const endedAtRef = useRef<number | null>(null);
  const clientIdRef = useRef<string | null>(null);
  const syncedUpToRef = useRef(0);
  const subscriptionRef = useRef<Location.LocationSubscription | null>(null);
  const syncPromiseRef = useRef<Promise<void> | null>(null);
  const lastFixAtRef = useRef<number | null>(null);
  const metaRef = useRef({ token, name, category, date });
  metaRef.current = { token, name, category, date };

  const stopWatch = useCallback(() => {
    subscriptionRef.current?.remove();
    subscriptionRef.current = null;
  }, []);

  const onFix = useCallback((location: Location.LocationObject) => {
    const coords = location.coords;
    const next: RoutePoint = {
      lat: coords.latitude,
      lng: coords.longitude,
      altitude_m: coords.altitude,
      accuracy_m: coords.accuracy,
      recorded_at: new Date(location.timestamp || Date.now()).toISOString(),
    };
    if (!acceptFix(pointsRef.current[pointsRef.current.length - 1], next)) return;
    lastFixAtRef.current = Date.now();
    setAccuracy(coords.accuracy);
    pointsRef.current = [...pointsRef.current, next].slice(-MAX_POINTS);
    setPoints(pointsRef.current);
  }, []);

  const startWatch = useCallback(async () => {
    if (subscriptionRef.current) return;
    subscriptionRef.current = await Location.watchPositionAsync(
      {
        accuracy: Location.Accuracy.High,
        distanceInterval: 5,
        timeInterval: 1000,
        mayShowUserSettingsDialog: true,
      },
      onFix,
      reason => setError(reason || "El proveedor de ubicación no pudo continuar."),
    );
  }, [onFix]);

  const persistLocalDraft = useCallback(async () => {
    const clientId = clientIdRef.current;
    const startMs = startedAtRef.current;
    if (!owner || !clientId || startMs == null) return;
    const meta = metaRef.current;
    const draft: LocalDraft = {
      owner,
      client_id: clientId,
      kind: meta.name.trim().slice(0,100) || "Actividad",
      category: meta.category,
      performed_on: meta.date,
      started_at: new Date(startMs).toISOString(),
      points: pointsRef.current,
      point_count: pointsRef.current.length,
      synced_point_count: syncedUpToRef.current,
    };
    try {
      await AsyncStorage.setItem(localDraftKey, JSON.stringify(draft));
      lastLocalPersistRef.current = Date.now();
    } catch {
      // La copia remota seguirá sincronizándose cuando haya conexión.
    }
  }, [owner, localDraftKey]);

  const clearLocalDraft = useCallback(async () => {
    try { await AsyncStorage.removeItem(localDraftKey); }
    catch { /* Best effort: no bloquear el guardado de la actividad. */ }
  }, [localDraftKey]);

  const syncNow = useCallback((): Promise<void> => {
    if (syncPromiseRef.current) return syncPromiseRef.current;
    const clientId = clientIdRef.current;
    const startMs = startedAtRef.current;
    if (!clientId || startMs == null) return Promise.resolve();
    const run = (async () => {
      try {
        while (syncedUpToRef.current < pointsRef.current.length) {
          const from = syncedUpToRef.current;
          const batch = pointsRef.current.slice(from, from + SYNC_BATCH);
          if (!batch.length) break;
          const meta = metaRef.current;
          setSyncState("syncing");
          await api("/activity-drafts/" + clientId, meta.token, {
            method: "PUT",
            body: {
              kind: meta.name.trim().slice(0, 100) || "Actividad",
              category: meta.category,
              performed_on: meta.date,
              started_at: new Date(startMs).toISOString(),
              points: batch,
            },
          });
          if (clientIdRef.current !== clientId) return;
          syncedUpToRef.current = from + batch.length;
        }
        setSyncState("ok");
      } catch {
        setSyncState("error");
      }
    })().finally(() => { syncPromiseRef.current = null; });
    syncPromiseRef.current = run;
    return run;
  }, [api]);

  useEffect(() => {
    let active = true;
    async function recoverDraft() {
      const [remoteResult, localRaw] = await Promise.all([
        api<RemoteDraft | null>("/activity-drafts/active", token).then(value => ({ value, failed: false })).catch(() => ({ value: null, failed: true })),
        AsyncStorage.getItem(localDraftKey).catch(() => null),
      ]);
      if (!active || startedAtRef.current != null) return;
      let local: LocalDraft | null = null;
      if (localRaw) {
        try {
          const parsed = JSON.parse(localRaw) as LocalDraft;
          if (parsed.owner === owner && parsed.client_id && Array.isArray(parsed.points)) local = parsed;
        } catch { local = null; }
      }
      const remote = remoteResult.value;
      let candidate: RemoteDraft | null = null;
      if (local && remote && local.client_id === remote.client_id) {
        const remoteTimestamps = new Set(remote.points.map(point => point.recorded_at));
        const merged = new Map<string, RoutePoint>();
        for (const point of [...remote.points, ...local.points]) merged.set(point.recorded_at, point);
        const points = [...merged.values()].sort((a,b) => Date.parse(a.recorded_at)-Date.parse(b.recorded_at)).slice(-MAX_POINTS);
        const syncedCount = points.filter(point => remoteTimestamps.has(point.recorded_at)).length;
        candidate = { ...remote, points, point_count: points.length, synced_point_count: syncedCount };
      } else if (local && remote) {
        const localLast = local.points.length ? Date.parse(local.points[local.points.length-1].recorded_at) : Date.parse(local.started_at);
        const remoteLast = remote.points.length ? Date.parse(remote.points[remote.points.length-1].recorded_at) : Date.parse(remote.started_at);
        candidate = localLast >= remoteLast
          ? { ...local, point_count: local.points.length, synced_point_count: local.synced_point_count ?? 0 }
          : { ...remote, synced_point_count: remote.points.length };
      } else if (local) {
        candidate = { ...local, point_count: local.points.length, synced_point_count: local.synced_point_count ?? 0 };
      } else if (remote) {
        candidate = { ...remote, synced_point_count: remote.points.length };
      }
      if (!candidate) return;
      if (candidate.points.length >= 2) {
        setRecovered(candidate);
      } else {
        if (local) await clearLocalDraft();
        if (remote && !remoteResult.failed) void api("/activity-drafts/"+remote.client_id,token,{method:"DELETE"}).catch(()=>undefined);
      }
    }
    void recoverDraft();
    return () => { active = false; };
  }, [token, owner, localDraftKey, clearLocalDraft]);

  useEffect(() => {
    if (status !== "tracking") return;
    const tick = () => {
      const start = startedAtRef.current;
      if (start == null) return;
      const now = Date.now();
      setElapsed(now - start);
      const last = lastFixAtRef.current ?? start;
      setSignalAge(Math.floor((now - last) / 1000));
    };
    tick();
    const timer = setInterval(tick, 1000);
    const syncTimer = setInterval(() => { void syncNow(); }, 15000);
    const localTimer = setInterval(() => { if (Date.now() - lastLocalPersistRef.current >= LOCAL_PERSIST_MS) void persistLocalDraft(); }, 1000);
    const appState = AppState.addEventListener("change", next => {
      if (next === "active") {
        void startWatch().catch(() => setError("No se pudo reanudar la señal GPS."));
        void syncNow();
      } else {
        stopWatch();
        void persistLocalDraft();
        void syncNow();
        setNotice("La ubicación se registra mientras SmartFit permanece en primer plano. Al salir de la app, el tramo puede quedar sin puntos GPS.");
      }
    });
    return () => {
      clearInterval(timer);
      clearInterval(syncTimer);
      clearInterval(localTimer);
      appState.remove();
      void persistLocalDraft();
      void syncNow();
    };
  }, [status, startWatch, stopWatch, syncNow, persistLocalDraft]);

  useEffect(() => () => {
    stopWatch();
    void persistLocalDraft();
    void syncNow();
  }, [stopWatch, persistLocalDraft, syncNow]);

  useEffect(() => {
    setName(category === "running" ? "Correr" : "Andar");
  }, [category]);

  async function startGps(resume?: RemoteDraft) {
    setError(""); setNotice("");
    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (permission.status !== "granted") {
        setError("Necesitas permitir la ubicación mientras usas SmartFit para registrar una ruta GPS.");
        return;
      }
      const startMs = resume ? Date.parse(resume.started_at) : Date.now();
      const initialPoints = resume?.points ?? [];
      if (clientIdRef.current && !resume) {
        const oldId = clientIdRef.current;
        void api("/activity-drafts/" + oldId, token, { method: "DELETE" }).catch(() => undefined);
      }
      const id = resume?.client_id ?? ("run-" + Math.random().toString(36).slice(2) + Date.now().toString(36));
      clientIdRef.current = id;
      pointsRef.current = initialPoints;
      syncedUpToRef.current = Math.min(resume?.synced_point_count ?? initialPoints.length, initialPoints.length);
      startedAtRef.current = startMs;
      endedAtRef.current = null;
      lastFixAtRef.current = initialPoints.length ? Date.parse(initialPoints[initialPoints.length - 1].recorded_at) : startMs;
      setPoints(initialPoints);
      setRecovered(null);
      setElapsed(Date.now() - startMs);
      setAccuracy(null);
      setSignalAge(null);
      setSyncState(resume ? "ok" : "idle");
      setStatus("tracking");
      await startWatch();
      await persistLocalDraft();
      void syncNow();
    } catch (reason) {
      stopWatch();
      startedAtRef.current = null;
      setStatus("idle");
      setError(reason instanceof Error ? reason.message : "No se pudo iniciar el seguimiento GPS.");
    }
  }

  function resumeRecovered() {
    if (!recovered) return;
    setCategory(recovered.category);
    setName(recovered.kind);
    setDate(recovered.performed_on ?? localDateISO());
    void startGps(recovered);
  }

  function saveRecoveredAsIs() {
    if (!recovered) return;
    const startMs = Date.parse(recovered.started_at);
    const endMs = Date.parse(recovered.points[recovered.points.length - 1].recorded_at);
    clientIdRef.current = recovered.client_id;
    pointsRef.current = recovered.points;
    syncedUpToRef.current = recovered.points.length;
    startedAtRef.current = startMs;
    endedAtRef.current = endMs;
    setCategory(recovered.category);
    setName(recovered.kind);
    setDate(recovered.performed_on ?? localDateISO());
    setPoints(recovered.points);
    setElapsed(endMs - startMs);
    setStatus("finished");
    setRecovered(null);
  }

  async function discardGps() {
    const clientId = clientIdRef.current;
    stopWatch();
    startedAtRef.current = null;
    endedAtRef.current = null;
    clientIdRef.current = null;
    pointsRef.current = [];
    syncedUpToRef.current = 0;
    lastFixAtRef.current = null;
    setPoints([]);
    setElapsed(0);
    setAccuracy(null);
    setSignalAge(null);
    setSyncState("idle");
    setRecovered(null);
    setStatus("idle");
    if (clientId) await api("/activity-drafts/" + clientId, token, { method: "DELETE" }).catch(() => undefined);
    await clearLocalDraft();
  }

  async function finishGps() {
    stopWatch();
    endedAtRef.current = Date.now();
    setElapsed(endedAtRef.current - (startedAtRef.current ?? endedAtRef.current));
    setStatus("finished");
    await syncNow();
  }

  async function saveActivity() {
    if (pointsRef.current.length < 2 || !clientIdRef.current || startedAtRef.current == null) {
      setError("Necesitas al menos dos ubicaciones GPS válidas para guardar el recorrido.");
      return;
    }
    const start = startedAtRef.current;
    const end = endedAtRef.current ?? Date.now();
    const stats = routeStats(pointsRef.current, start, end);
    const durationMin = Math.max(1, Math.min(600, Math.ceil(stats.activeMs / 60000)));
    if (stats.distanceKm > 500) {
      setError("El recorrido supera la distancia máxima permitida.");
      return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      await syncNow();
      await api("/workouts", token, {
        method: "POST",
        body: {
          performed_on: date,
          kind: name.trim() || (category === "running" ? "Correr" : "Andar"),
          category,
          duration_min: durationMin,
          distance_km: stats.distanceKm > 0 ? Number(stats.distanceKm.toFixed(3)) : null,
          elevation_gain_m: stats.elevationM > 0 ? Math.round(stats.elevationM) : null,
          steps: steps.trim() ? Number(steps) : null,
          avg_hr_bpm: heartRate.trim() ? Number(heartRate) : null,
          notes: notes.trim() || null,
          sets: [],
          exercise_durations_min: {},
          route_points: pointsRef.current,
          draft_id: clientIdRef.current,
          estimate_calories: true,
        },
      });
      await discardGps();
      setNotes(""); setSteps(""); setHeartRate("");
      onSaved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo guardar la actividad GPS.");
    } finally { setBusy(false); }
  }

  const stats = useMemo(() => {
    const end = status === "tracking" ? startedAtRef.current == null ? null : startedAtRef.current + elapsed : endedAtRef.current;
    return routeStats(points, startedAtRef.current, end);
  }, [points, elapsed, status]);
  const pace = paceText(stats.activeMs, stats.distanceKm);
  const lastFixAge = signalAge == null ? null : signalAge;

  if (!visible) {
    return status === "tracking" ? <KeepAwakeWhileTracking /> : null;
  }

  return <>
    {status === "tracking" ? <KeepAwakeWhileTracking /> : null}
    <Panel>
      <SectionTitle title="Seguimiento GPS" action={category === "running" ? "CARRERA" : "PASEO"} />
      <Text style={{ color: colors.text, fontWeight: "700" }}>Modalidad</Text>
      <View style={{ flexDirection: "row", gap: 8 }}>
        <View style={{ flex: 1 }}><AppButton title="🏃 Correr" variant={category === "running" ? "primary" : "secondary"} onPress={() => setCategory("running")} disabled={status !== "idle"} /></View>
        <View style={{ flex: 1 }}><AppButton title="🚶 Andar" variant={category === "walking" ? "primary" : "secondary"} onPress={() => setCategory("walking")} disabled={status !== "idle"} /></View>
      </View>
      <Field label="Nombre de la actividad" value={name} onChangeText={setName} />
      <Field label="Fecha (AAAA-MM-DD)" value={date} onChangeText={setDate} placeholder={localDateISO()} />
      {recovered && status === "idle" ? <Panel>
        <Text style={{ color: colors.text, fontWeight: "900" }}>Tienes un recorrido sin terminar</Text>
        <Muted>{recovered.kind} · {new Date(recovered.started_at).toLocaleString("es-ES")} · {recovered.points.length} puntos · {routeStats(recovered.points, null, null).distanceKm.toFixed(2)} km</Muted>
        <View style={{ flexDirection: "row", gap: 8 }}>
          <View style={{ flex: 1 }}><AppButton title="Reanudar" onPress={resumeRecovered} /></View>
          <View style={{ flex: 1 }}><AppButton title="Guardar ruta" variant="secondary" onPress={saveRecoveredAsIs} /></View>
        </View>
        <AppButton title="Descartar recorrido" variant="quiet" onPress={() => {
          void api("/activity-drafts/" + recovered.client_id, token, { method: "DELETE" }).catch(() => undefined);
          void clearLocalDraft();
          setRecovered(null);
        }} />
      </Panel> : null}
      {status === "idle" ? <AppButton title="Iniciar recorrido GPS" onPress={() => void startGps()} loading={busy} /> : null}
      {status === "tracking" ? <AppButton title="Finalizar recorrido" onPress={() => void finishGps()} variant="secondary" /> : null}
      {status === "finished" ? <View style={{ flexDirection: "row", gap: 8 }}>
        <View style={{ flex: 1 }}><AppButton title="Guardar actividad" onPress={() => void saveActivity()} loading={busy} /></View>
        <View style={{ flex: 1 }}><AppButton title="Descartar" variant="quiet" onPress={() => Alert.alert("Descartar recorrido", "¿Eliminar este borrador GPS?", [
          { text: "Cancelar", style: "cancel" }, { text: "Eliminar", style: "destructive", onPress: () => void discardGps() },
        ])} disabled={busy} /></View>
      </View> : null}
      {status === "tracking" ? <Muted>La pantalla permanece encendida mientras registras. El GPS se pausa al llevar SmartFit al segundo plano; vuelve a la app para reanudar la señal.</Muted> : null}
      {lastFixAge != null && lastFixAge > 20 && status === "tracking" ? <Text style={{ color: colors.danger, fontWeight: "700" }}>Sin señal GPS desde hace {lastFixAge} s. Comprueba los permisos o sal al exterior.</Text> : null}
      <View style={{ flexDirection: "row", gap: 10 }}>
        <Panel style={{ flex: 1 }}>
          <Muted>Tiempo activo</Muted>
          <Text style={{ color: colors.text, fontWeight: "900", fontSize: 22 }}>{durationText(stats.activeMs)}</Text>
        </Panel>
        <Panel style={{ flex: 1 }}>
          <Muted>Distancia</Muted>
          <Text style={{ color: colors.text, fontWeight: "900", fontSize: 22 }}>{stats.distanceKm.toFixed(2)} km</Text>
        </Panel>
      </View>
      <View style={{ flexDirection: "row", gap: 10 }}>
        <Panel style={{ flex: 1 }}>
          <Muted>Ritmo medio</Muted>
          <Text style={{ color: colors.text, fontWeight: "900", fontSize: 22 }}>{pace}</Text>
        </Panel>
        <Panel style={{ flex: 1 }}>
          <Muted>Desnivel positivo</Muted>
          <Text style={{ color: colors.text, fontWeight: "900", fontSize: 22 }}>{Math.round(stats.elevationM)} m</Text>
        </Panel>
      </View>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <Muted>{points.length} puntos GPS</Muted>
        <Muted>{accuracy == null ? "Precisión —" : "±" + Math.round(accuracy) + " m"}</Muted>
        <Muted>{syncState === "ok" ? "Ruta sincronizada" : syncState === "error" ? "Error al sincronizar" : syncState === "syncing" ? "Guardando ruta…" : "Pendiente"}</Muted>
      </View>
      {syncState === "error" ? <AppButton title="Reintentar sincronización" variant="quiet" onPress={() => void syncNow()} /> : null}
      <Field label="Pasos (opcional)" value={steps} onChangeText={setSteps} keyboardType="number-pad" placeholder="Si los conoces" />
      <Field label="Frecuencia cardiaca media (ppm), opcional" value={heartRate} onChangeText={setHeartRate} keyboardType="number-pad" />
      <Field label="Notas" value={notes} onChangeText={setNotes} multiline numberOfLines={2} maxLength={1000} />
      <Muted>Se conservan huecos GPS largos sin inventar distancia. Mantén SmartFit abierto durante la actividad para seguir recopilando puntos.</Muted>
      <ErrorMessage message={error} />
      {notice ? <Text style={{ color: colors.accent }}>{notice}</Text> : null}
    </Panel>
    <Panel>
      <SectionTitle title="Mapa de tu recorrido" action={status === "tracking" ? "EN DIRECTO" : status === "finished" ? "FINALIZADO" : "GPS"} />
      <RouteMapPreview points={points} initiallyVisible height={260} />
    </Panel>
  </>;
}
