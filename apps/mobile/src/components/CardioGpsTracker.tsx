import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Alert, AppState, Text, View } from "react-native";
import * as Location from "expo-location";
import { useKeepAwake } from "expo-keep-awake";
import { WebView } from "react-native-webview";
import { api } from "@/lib/api";
import {
  appendCardioLocations, clearLocalCardioDraft, readLocalCardioDraft, saveLocalCardioDraft,
  startCardioBackgroundUpdates, stopCardioBackgroundUpdates, syncLocalCardioDraft,
  type CardioLocalDraft,
} from "@/lib/cardio-location-task";
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
  received_fix_count?: number; accepted_fix_count?: number; rejected_fix_count?: number;
  last_fix_at?: string | null; last_accuracy_m?: number | null; last_location_error?: string | null;
};
type Props = { token: string; owner: string; visible: boolean; initialCategory: Category; onSaved: () => void };
type RouteStats = { distanceKm: number; elevationM: number; gapMs: number; activeMs: number };

const MAX_POINTS = 10000;
const LOCAL_PERSIST_MS = 5000;
const GAP_MS = 120000;
const GPS_STALE_MS = 45000;
const EARTH_RADIUS_KM = 6371.0088;

function distanceKm(a: RoutePoint, b: RoutePoint) {
  const rad = (value: number) => value * Math.PI / 180;
  const dLat = rad(b.lat - a.lat);
  const dLng = rad(b.lng - a.lng);
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return EARTH_RADIUS_KM * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(Math.max(0, 1 - x)));
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

export function CardioGpsTracker({ token, owner, visible, initialCategory, onSaved }: Props) {
  const [category, setCategory] = useState<Category>(initialCategory);
  const [name, setName] = useState("Correr");
  const [date, setDate] = useState(localDateISO());
  const [points, setPoints] = useState<RoutePoint[]>([]);
  const [status, setStatus] = useState<"idle" | "tracking" | "finished">("idle");
  const [elapsed, setElapsed] = useState(0);
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [signalAge, setSignalAge] = useState<number | null>(null);
  const [syncState, setSyncState] = useState<"idle" | "syncing" | "ok" | "error">("idle");
  const [receivedFixCount, setReceivedFixCount] = useState(0);
  const [acceptedFixCount, setAcceptedFixCount] = useState(0);
  const [rejectedFixCount, setRejectedFixCount] = useState(0);
  const [backgroundTracking, setBackgroundTracking] = useState(false);
  const [recovered, setRecovered] = useState<RemoteDraft | null>(null);
  const [steps, setSteps] = useState("");
  const [heartRate, setHeartRate] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const pointsRef = useRef<RoutePoint[]>([]);
  const receivedFixCountRef = useRef(0);
  const acceptedFixCountRef = useRef(0);
  const rejectedFixCountRef = useRef(0);
  const lastLocalPersistRef = useRef(0);
  const localDraftKey = useMemo(() => "smartfit.activeRun.v1." + owner, [owner]);
  const startedAtRef = useRef<number | null>(null);
  const endedAtRef = useRef<number | null>(null);
  const clientIdRef = useRef<string | null>(null);
  const syncedUpToRef = useRef(0);
  const subscriptionRef = useRef<Location.LocationSubscription | null>(null);
  const syncPromiseRef = useRef<Promise<void> | null>(null);
  const lastFixAtRef = useRef<number | null>(null);
  const lastFixPersistPromiseRef = useRef<Promise<void> | null>(null);
  const watchActiveRef = useRef(false);
  const backgroundTrackingRef = useRef(false);
  const watchRecoveryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const watchRecoveryAttemptsRef = useRef(0);
  const lastRecoveryAttemptRef = useRef(0);
  const restartWatchRef = useRef<() => void>(() => undefined);
  const metaRef = useRef({ token, name, category, date });
  metaRef.current = { token, name, category, date };

  const stopWatch = useCallback(() => {
    subscriptionRef.current?.remove();
    subscriptionRef.current = null;
    if (watchRecoveryTimerRef.current) {
      clearTimeout(watchRecoveryTimerRef.current);
      watchRecoveryTimerRef.current = null;
    }
    watchRecoveryAttemptsRef.current = 0;
  }, []);

  const onFix = useCallback((location: Location.LocationObject) => {
    // La hora de recepción se actualiza aunque la lectura se descarte por ruido.
    lastFixAtRef.current = Date.now();
    setAccuracy(location.coords.accuracy);
    const pending = appendCardioLocations(localDraftKey, [location]).then(draft => {
      if (!draft || draft.client_id !== clientIdRef.current) return;
      pointsRef.current = draft.points;
      receivedFixCountRef.current = draft.received_fix_count;
      acceptedFixCountRef.current = draft.accepted_fix_count;
      rejectedFixCountRef.current = draft.rejected_fix_count;
      setPoints(draft.points);
      setReceivedFixCount(draft.received_fix_count);
      setAcceptedFixCount(draft.accepted_fix_count);
      setRejectedFixCount(draft.rejected_fix_count);
    }).catch(reason => {
      setError(reason instanceof Error ? reason.message : "No se pudo guardar la lectura GPS localmente.");
    });
    lastFixPersistPromiseRef.current = pending;
  }, [localDraftKey]);

  const startWatch = useCallback(async () => {
    if (subscriptionRef.current || !watchActiveRef.current || AppState.currentState !== "active") return;
    const subscription = await Location.watchPositionAsync(
      {
        accuracy: Location.Accuracy.High,
        distanceInterval: 3,
        timeInterval: 1000,
        mayShowUserSettingsDialog: true,
      },
      onFix,
      reason => {
        subscriptionRef.current?.remove();
        subscriptionRef.current = null;
        setError(reason || "El proveedor GPS se interrumpió; SmartFit intentará recuperarlo.");
        restartWatchRef.current();
      },
    );
    if (!watchActiveRef.current || AppState.currentState !== "active") {
      subscription.remove();
      return;
    }
    subscriptionRef.current = subscription;
    watchRecoveryAttemptsRef.current = 0;
  }, [onFix]);

  restartWatchRef.current = () => {
    if (watchRecoveryTimerRef.current || !watchActiveRef.current || AppState.currentState !== "active") return;
    const delay = Math.min(30000, 1000 * 2 ** Math.min(watchRecoveryAttemptsRef.current++, 5));
    watchRecoveryTimerRef.current = setTimeout(() => {
      watchRecoveryTimerRef.current = null;
      void startWatch().catch(reason => {
        setError(reason instanceof Error ? reason.message : "No se pudo reiniciar el observador GPS.");
        restartWatchRef.current();
      });
    }, delay);
  };

  const persistLocalDraft = useCallback(async () => {
    const clientId = clientIdRef.current;
    const startMs = startedAtRef.current;
    if (!owner || !clientId || startMs == null) return;
    try {
      const meta = metaRef.current;
      const previous = await readLocalCardioDraft(localDraftKey);
      const draft: CardioLocalDraft = {
        owner,
        client_id: clientId,
        kind: meta.name.trim().slice(0,100) || "Actividad",
        category: meta.category,
        performed_on: meta.date,
        started_at: new Date(startMs).toISOString(),
        points: pointsRef.current,
        point_count: pointsRef.current.length,
        synced_point_count: previous?.synced_point_count ?? syncedUpToRef.current,
        received_fix_count: receivedFixCountRef.current,
        accepted_fix_count: acceptedFixCountRef.current,
        rejected_fix_count: rejectedFixCountRef.current,
        last_fix_at: previous?.last_fix_at ?? null,
        last_accuracy_m: previous?.last_accuracy_m ?? null,
        last_location_error: previous?.last_location_error ?? null,
      };
      await saveLocalCardioDraft(localDraftKey, draft);
      lastLocalPersistRef.current = Date.now();
    } catch {
      setError("No se pudo persistir la copia local de la ruta.");
    }
  }, [owner, localDraftKey]);

  const clearLocalDraft = useCallback(async () => {
    try { await clearLocalCardioDraft(localDraftKey); }
    catch { /* Best effort: no bloquear el guardado de la actividad. */ }
  }, [localDraftKey]);

  const syncNow = useCallback((): Promise<void> => {
    if (syncPromiseRef.current) return syncPromiseRef.current;
    if (!clientIdRef.current || startedAtRef.current == null) return Promise.resolve();
    const run = (async () => {
      try {
        setSyncState("syncing");
        const draft = await syncLocalCardioDraft(localDraftKey, metaRef.current.token);
        if (draft && draft.client_id === clientIdRef.current) {
          syncedUpToRef.current = draft.synced_point_count ?? 0;
          pointsRef.current = draft.points;
          setPoints(draft.points);
        }
        setSyncState("ok");
      } catch {
        setSyncState("error");
      }
    })().finally(() => { syncPromiseRef.current = null; });
    syncPromiseRef.current = run;
    return run;
  }, [localDraftKey]);

  useEffect(() => {
    let active = true;
    async function recoverDraft() {
      const [remoteResult, localRaw] = await Promise.all([
        api<RemoteDraft | null>("/activity-drafts/active", token).then(value => ({ value, failed: false })).catch(() => ({ value: null, failed: true })),
        readLocalCardioDraft(localDraftKey).catch(() => null),
      ]);
      if (!active || startedAtRef.current != null) return;
      const local: CardioLocalDraft | null = localRaw && localRaw.owner === owner ? localRaw : null;
      const remote = remoteResult.value;
      let candidate: RemoteDraft | null = null;
      if (local && remote && local.client_id === remote.client_id) {
        const remoteTimestamps = new Set(remote.points.map(point => point.recorded_at));
        const merged = new Map<string, RoutePoint>();
        for (const point of [...remote.points, ...local.points]) merged.set(point.recorded_at, point);
        const points = [...merged.values()].sort((a,b) => Date.parse(a.recorded_at)-Date.parse(b.recorded_at)).slice(-MAX_POINTS);
        const syncedCount = points.filter(point => remoteTimestamps.has(point.recorded_at)).length;
        candidate = { ...remote, points, point_count: points.length, synced_point_count: syncedCount, received_fix_count: local.received_fix_count, accepted_fix_count: local.accepted_fix_count, rejected_fix_count: local.rejected_fix_count, last_fix_at: local.last_fix_at, last_accuracy_m: local.last_accuracy_m, last_location_error: local.last_location_error };
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
      if (candidate.points.length >= 1) {
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
    const watchdog = setInterval(() => {
      const last = lastFixAtRef.current ?? startedAtRef.current;
      if (AppState.currentState !== "active" || !watchActiveRef.current || last == null || Date.now() - last < GPS_STALE_MS) return;
      if (Date.now() - lastRecoveryAttemptRef.current < GPS_STALE_MS) return;
      lastRecoveryAttemptRef.current = Date.now();
      void Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High })
        .then(onFix)
        .catch(() => undefined);
      stopWatch();
      restartWatchRef.current();
    }, 15000);
    const appState = AppState.addEventListener("change", next => {
      if (next === "active") {
        void readLocalCardioDraft(localDraftKey).then(draft => {
          if (!draft || draft.client_id !== clientIdRef.current) return;
          pointsRef.current = draft.points;
          setPoints(draft.points);
          lastFixAtRef.current = Date.parse(draft.last_fix_at || "") || lastFixAtRef.current;
          if (draft.last_accuracy_m != null) setAccuracy(draft.last_accuracy_m);
          receivedFixCountRef.current = draft.received_fix_count ?? 0;
          acceptedFixCountRef.current = draft.accepted_fix_count ?? draft.points.length;
          rejectedFixCountRef.current = draft.rejected_fix_count ?? 0;
          setReceivedFixCount(receivedFixCountRef.current);
          setAcceptedFixCount(acceptedFixCountRef.current);
          setRejectedFixCount(rejectedFixCountRef.current);
        }).catch(() => undefined);
        void startWatch().catch(() => restartWatchRef.current());
        void syncNow();
        setNotice(backgroundTrackingRef.current
          ? "El servicio GPS sigue activo en segundo plano mediante la notificación de SmartFit."
          : "El permiso de segundo plano no está activo; el GPS se registrará mientras SmartFit permanezca abierto.");
      } else {
        stopWatch();
        void persistLocalDraft();
        void syncNow();
        setNotice(backgroundTrackingRef.current
          ? "SmartFit continúa registrando la ruta en segundo plano."
          : "La ubicación puede interrumpirse al salir de SmartFit porque no está activo el permiso de segundo plano.");
      }
    });
    return () => {
      clearInterval(timer);
      clearInterval(syncTimer);
      clearInterval(localTimer);
      clearInterval(watchdog);
      appState.remove();
      void persistLocalDraft();
      void syncNow();
    };
  }, [status, startWatch, stopWatch, syncNow, persistLocalDraft, localDraftKey, onFix]);

  useEffect(() => () => {
    watchActiveRef.current = false;
    stopWatch();
    void persistLocalDraft();
    void syncNow();
  }, [stopWatch, persistLocalDraft, syncNow]);

  useEffect(() => {
    if (visible && status === "idle") setCategory(initialCategory);
  }, [initialCategory, visible, status]);

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
      let allowBackground = false;
      try {
        const backgroundPermission = await Location.requestBackgroundPermissionsAsync();
        allowBackground = backgroundPermission.status === "granted";
      } catch {
        allowBackground = false;
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
      lastFixPersistPromiseRef.current = null;
      syncedUpToRef.current = Math.min(resume?.synced_point_count ?? initialPoints.length, initialPoints.length);
      receivedFixCountRef.current = resume?.received_fix_count ?? initialPoints.length;
      acceptedFixCountRef.current = resume?.accepted_fix_count ?? initialPoints.length;
      rejectedFixCountRef.current = resume?.rejected_fix_count ?? 0;
      setReceivedFixCount(receivedFixCountRef.current);
      setAcceptedFixCount(acceptedFixCountRef.current);
      setRejectedFixCount(rejectedFixCountRef.current);
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
      watchActiveRef.current = true;
      lastRecoveryAttemptRef.current = 0;
      await persistLocalDraft();
      if (allowBackground) {
        try {
          await startCardioBackgroundUpdates(localDraftKey);
          backgroundTrackingRef.current = true;
          setBackgroundTracking(true);
        } catch (backgroundError) {
          backgroundTrackingRef.current = false;
          setBackgroundTracking(false);
          setNotice("No se pudo activar el seguimiento en segundo plano. La actividad seguirá mientras SmartFit esté abierto.");
          setError(backgroundError instanceof Error ? backgroundError.message : "No se pudo activar el servicio GPS en segundo plano.");
        }
      } else {
        await stopCardioBackgroundUpdates(localDraftKey).catch(() => undefined);
        backgroundTrackingRef.current = false;
        setBackgroundTracking(false);
        setNotice("Para registrar con la pantalla bloqueada, permite el acceso a la ubicación siempre en los ajustes del teléfono.");
      }
      await startWatch();
      void syncNow();
    } catch (reason) {
      watchActiveRef.current = false;
      stopWatch();
      if (backgroundTrackingRef.current) await stopCardioBackgroundUpdates(localDraftKey).catch(() => undefined);
      backgroundTrackingRef.current = false;
      setBackgroundTracking(false);
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

  async function saveRecoveredAsIs() {
    if (!recovered) return;
    await stopCardioBackgroundUpdates(localDraftKey).catch(() => undefined);
    backgroundTrackingRef.current = false;
    setBackgroundTracking(false);
    const startMs = Date.parse(recovered.started_at);
    const endMs = Date.parse(recovered.points[recovered.points.length - 1].recorded_at);
    clientIdRef.current = recovered.client_id;
    pointsRef.current = recovered.points;
    syncedUpToRef.current = recovered.synced_point_count ?? recovered.points.length;
    receivedFixCountRef.current = recovered.received_fix_count ?? recovered.points.length;
    acceptedFixCountRef.current = recovered.accepted_fix_count ?? recovered.points.length;
    rejectedFixCountRef.current = recovered.rejected_fix_count ?? 0;
    startedAtRef.current = startMs;
    endedAtRef.current = endMs;
    lastFixAtRef.current = Date.parse(recovered.last_fix_at || "") || endMs;
    setCategory(recovered.category);
    setName(recovered.kind);
    setDate(recovered.performed_on ?? localDateISO());
    setPoints(recovered.points);
    setReceivedFixCount(receivedFixCountRef.current);
    setAcceptedFixCount(acceptedFixCountRef.current);
    setRejectedFixCount(rejectedFixCountRef.current);
    setElapsed(endMs - startMs);
    setStatus("finished");
    setRecovered(null);
  }

  async function discardGps() {
    const clientId = clientIdRef.current;
    watchActiveRef.current = false;
    stopWatch();
    if (backgroundTrackingRef.current) await stopCardioBackgroundUpdates(localDraftKey).catch(() => undefined);
    backgroundTrackingRef.current = false;
    setBackgroundTracking(false);
    startedAtRef.current = null;
    endedAtRef.current = null;
    clientIdRef.current = null;
    pointsRef.current = [];
    syncedUpToRef.current = 0;
    lastFixAtRef.current = null;
    receivedFixCountRef.current = 0;
    acceptedFixCountRef.current = 0;
    rejectedFixCountRef.current = 0;
    setReceivedFixCount(0); setAcceptedFixCount(0); setRejectedFixCount(0);
    setPoints([]);
    setElapsed(0);
    setAccuracy(null);
    setSignalAge(null);
    setSyncState("idle");
    setRecovered(null);
    setStatus("idle");
    await lastFixPersistPromiseRef.current;
    if (clientId) await api("/activity-drafts/" + clientId, token, { method: "DELETE" }).catch(() => undefined);
    await clearLocalDraft();
  }

  async function finishGps() {
    watchActiveRef.current = false;
    stopWatch();
    if (backgroundTrackingRef.current) await stopCardioBackgroundUpdates(localDraftKey).catch(() => undefined);
    backgroundTrackingRef.current = false;
    setBackgroundTracking(false);
    await lastFixPersistPromiseRef.current;
    endedAtRef.current = Date.now();
    setElapsed(endedAtRef.current - (startedAtRef.current ?? endedAtRef.current));
    await persistLocalDraft();
    await syncNow();
    setStatus("finished");
  }

  async function saveActivity() {
    await lastFixPersistPromiseRef.current;
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
          void (async () => {
            await stopCardioBackgroundUpdates(localDraftKey).catch(() => undefined);
            await api("/activity-drafts/" + recovered.client_id, token, { method: "DELETE" }).catch(() => undefined);
            await clearLocalDraft();
            backgroundTrackingRef.current = false;
            setBackgroundTracking(false);
            setRecovered(null);
          })();
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
      {status === "tracking" ? <Muted>{backgroundTracking ? "GPS activo también en segundo plano. Android mostrará una notificación persistente de SmartFit." : "GPS activo mientras SmartFit está abierto. Activa el permiso de ubicación siempre para continuar con la pantalla bloqueada."}</Muted> : null}
      {lastFixAge != null && lastFixAge > 45 && status === "tracking" ? <Text style={{ color: colors.danger, fontWeight: "700" }}>No se reciben lecturas GPS desde hace {lastFixAge} s. SmartFit está intentando recuperar el GPS.</Text> : null}
      {status === "tracking" ? <Muted>Lecturas GPS: {receivedFixCount} · aceptadas: {acceptedFixCount} · filtradas: {rejectedFixCount}</Muted> : null}
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
      <Muted>Las lecturas se guardan primero en el dispositivo y se sincronizan con tu cuenta. Los huecos largos no generan distancia inventada.</Muted>
      <ErrorMessage message={error} />
      {notice ? <Text style={{ color: colors.accent }}>{notice}</Text> : null}
    </Panel>
    <Panel>
      <SectionTitle title="Mapa de tu recorrido" action={status === "tracking" ? "EN DIRECTO" : status === "finished" ? "FINALIZADO" : "GPS"} />
      <RouteMapPreview points={points} initiallyVisible height={260} />
    </Panel>
  </>;
}
