"use client";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { apiRequest } from "@/lib/api";
import { GeoRouteMap } from "@/components/geo-route-map";
import { GAP_MS, RoutePoint, acceptFix, fixRejectionReason, lastPointTime, minutesText, routeStats } from "@/lib/route";
import { RemoteDraft, StoredDraft, clearLocalDraft, loadLocalDraft, newClientId, pickDraft, saveLocalDraft } from "@/lib/route-draft";

type Props = {
  token: string;
  owner?: string;
  category: "walking" | "running";
  onCategoryChange: (category: "walking" | "running") => void;
  onExit: () => void;
  onTrackingChange: (tracking: boolean) => void;
  onSaved: () => void;
};

const SYNC_EVERY_MS=15000,PERSIST_EVERY_MS=5000,SYNC_BATCH=500,STALE_SIGNAL_S=45;

const durationText = (milliseconds: number) => {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  const two = (value: number) => String(value).padStart(2, "0");
  return hours ? two(hours) + ":" + two(minutes) + ":" + two(rest) : two(minutes) + ":" + two(rest);
};

const paceText = (milliseconds: number, kilometres: number) => {
  if (kilometres < 0.02 || milliseconds <= 0) return "—";
  const total = Math.round(milliseconds / 60000 / kilometres);
  return Math.floor(total / 60) + ":" + String(total % 60).padStart(2, "0") + " /km";
};

export function CardioTracker({ token, owner="", category, onCategoryChange, onExit, onTrackingChange, onSaved }: Props) {
  const [name, setName] = useState(category === "running" ? "Correr" : "Andar");
  const [date, setDate] = useState(new Date().toLocaleDateString("sv-SE"));
  const [steps, setSteps] = useState("");
  const [heartRate, setHeartRate] = useState("");
  const [notes, setNotes] = useState("");
  const [manual, setManual] = useState(false);
  const [manualDuration, setManualDuration] = useState("30");
  const [manualDistance, setManualDistance] = useState("");
  const [manualElevation, setManualElevation] = useState("");
  const [points, setPoints] = useState<RoutePoint[]>([]);
  const [status, setStatus] = useState<"idle" | "tracking" | "finished">("idle");
  const [session,setSession]=useState<{start:number;end:number}|null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [signalAge,setSignalAge]=useState<number|null>(null),[wake,setWake]=useState<"on"|"off"|"unsupported">("off"),[sync,setSync]=useState<"idle"|"ok"|"error">("idle");
  const [receivedFixes,setReceivedFixes]=useState(0),[acceptedFixes,setAcceptedFixes]=useState(0),[rejectedFixes,setRejectedFixes]=useState(0);
  const [recovered,setRecovered]=useState<StoredDraft|null>(null),[notice,setNotice]=useState("");
  const [gpsError, setGpsError] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const watchId = useRef<number | null>(null);
  const startedAt = useRef<number | null>(null);
  const clientId=useRef<string|null>(null),pointsRef=useRef<RoutePoint[]>([]),syncedUpTo=useRef(0),syncPromise=useRef<Promise<void>|null>(null),lastFixAt=useRef<number|null>(null),lastPersist=useRef(0),wakeLock=useRef<WakeLockSentinel|null>(null);
  const trackingRef=useRef(false),watchRetryTimer=useRef<number|null>(null),watchRetryAttempts=useRef(0);
  const meta=useRef({token,owner,name,category,date});meta.current={token,owner,name,category,date};

  function persistNow(){if(!clientId.current||startedAt.current==null)return;const m=meta.current;lastPersist.current=Date.now();saveLocalDraft({clientId:clientId.current,owner:m.owner,kind:m.name,category:m.category,performedOn:m.date,startedAt:new Date(startedAt.current).toISOString(),points:pointsRef.current});}
  function syncNow():Promise<void>{if(syncPromise.current)return syncPromise.current;const id=clientId.current;if(!id||startedAt.current==null)return Promise.resolve();const startIso=new Date(startedAt.current).toISOString();const run=(async()=>{try{do{const from=syncedUpTo.current,batch=pointsRef.current.slice(from,from+SYNC_BATCH),m=meta.current;await apiRequest("/activity-drafts/"+id,{method:"PUT",token:m.token,body:{kind:m.name.trim().slice(0,100)||"Actividad",category:m.category,performed_on:m.date,started_at:startIso,points:batch}});if(clientId.current!==id)return;syncedUpTo.current=from+batch.length;}while(syncedUpTo.current<pointsRef.current.length);setSync("ok");}catch{setSync("error");}})().finally(()=>{syncPromise.current=null;});syncPromise.current=run;return run;}
  async function acquireWakeLock(){if(!("wakeLock" in navigator)){setWake("unsupported");return;}try{const s=await navigator.wakeLock.request("screen");wakeLock.current=s;setWake("on");s.addEventListener("release",()=>{if(wakeLock.current===s){wakeLock.current=null;setWake("off");}});}catch{setWake("off");}}
  function releaseWakeLock(){const s=wakeLock.current;wakeLock.current=null;if(s)void s.release().catch(()=>undefined);setWake("off");}
  function onFix(position:GeolocationPosition){
    const q=position.coords,p:RoutePoint={lat:q.latitude,lng:q.longitude,altitude_m:q.altitude,accuracy_m:q.accuracy,recorded_at:new Date(position.timestamp||Date.now()).toISOString()};
    lastFixAt.current=Date.now();setReceivedFixes(value=>value+1);setAccuracy(q.accuracy);
    const reason=fixRejectionReason(pointsRef.current[pointsRef.current.length-1],p);
    if(reason){setRejectedFixes(value=>value+1);return;}
    setAcceptedFixes(value=>value+1);
    pointsRef.current=[...pointsRef.current,p].slice(-10000);setPoints(pointsRef.current);
    persistNow();
  }
  function scheduleWatchRestart(){
    if(watchRetryTimer.current!=null||!trackingRef.current||document.visibilityState!=="visible")return;
    const delay=Math.min(30000,1000*2**Math.min(watchRetryAttempts.current++,5));
    watchRetryTimer.current=window.setTimeout(()=>{
      watchRetryTimer.current=null;
      if(!trackingRef.current||document.visibilityState!=="visible"||!navigator.geolocation)return;
      try{beginWatch();}catch{scheduleWatchRestart();}
    },delay);
  }
  function onGeoError(e:GeolocationPositionError){
    setGpsError(e.code===1?"No se ha permitido el acceso a la ubicación. Activa el permiso en el navegador o registra la actividad manualmente.":e.code===2?"El navegador no ha podido obtener una posición GPS. Reintentaremos automáticamente.":"La lectura GPS ha agotado el tiempo de espera. Reintentaremos automáticamente.");
    if(watchId.current!=null&&navigator.geolocation){navigator.geolocation.clearWatch(watchId.current);watchId.current=null;}
    if(e.code===1){trackingRef.current=false;stopGps();releaseWakeLock();persistNow();startedAt.current=null;setStatus("idle");onTrackingChange(false);return;}
    scheduleWatchRestart();
  }
  function beginWatch(){
    if(!navigator.geolocation||!trackingRef.current||document.visibilityState!=="visible"||watchId.current!=null)return;
    watchId.current=navigator.geolocation.watchPosition(onFix,onGeoError,{enableHighAccuracy:true,maximumAge:2000,timeout:30000});
    watchRetryAttempts.current=0;setGpsError("");
  }

  const stats=useMemo(()=>{const live=status==="tracking"&&startedAt.current!=null,start=live?startedAt.current:session?.start??null,end=live?(startedAt.current as number)+elapsed:session?.end??null;return routeStats(points,start,end);},[points,status,session,elapsed]);
  const distance=stats.distanceKm,elevation=stats.elevationM,hasAltitude=stats.hasAltitude;

  useEffect(() => {
    if (status !== "tracking") return;
    const tick = () => {
      const now=Date.now();if(startedAt.current!=null)setElapsed(now-startedAt.current);const ref=lastFixAt.current??startedAt.current;setSignalAge(ref!=null?Math.floor((now-ref)/1000):null);
    };
    tick();
    const timer = window.setInterval(tick, 1000);
    const syncTimer=window.setInterval(()=>{persistNow();void syncNow();},SYNC_EVERY_MS);
    const watchdog=window.setInterval(()=>{
      const last=lastFixAt.current??startedAt.current;
      if(trackingRef.current&&document.visibilityState==="visible"&&last!=null&&Date.now()-last>45000){
        if(watchId.current!=null&&navigator.geolocation){navigator.geolocation.clearWatch(watchId.current);watchId.current=null;}
        scheduleWatchRestart();
      }
    },15000);
    const onVisibility=()=>{if(document.visibilityState==="hidden"){persistNow();return;}void acquireWakeLock();if(trackingRef.current){if(watchId.current!=null&&navigator.geolocation){navigator.geolocation.clearWatch(watchId.current);watchId.current=null;}if(watchRetryTimer.current!=null){window.clearTimeout(watchRetryTimer.current);watchRetryTimer.current=null;}beginWatch();}void syncNow();const last=lastPointTime(pointsRef.current)??startedAt.current;if(last!=null&&Date.now()-last>GAP_MS)setNotice("El seguimiento estuvo interrumpido unos "+minutesText(Date.now()-last)+" (pantalla bloqueada o SmartFit en segundo plano). Ese tramo no cuenta en la distancia ni en el ritmo.");};
    const onHide=()=>persistNow(),onOnline=()=>{void syncNow();};document.addEventListener("visibilitychange",onVisibility);window.addEventListener("pagehide",onHide);window.addEventListener("online",onOnline);
    const guard = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", guard);
    return () => { window.clearInterval(timer);window.clearInterval(syncTimer);window.clearInterval(watchdog);document.removeEventListener("visibilitychange",onVisibility);window.removeEventListener("pagehide",onHide);window.removeEventListener("online",onOnline);window.removeEventListener("beforeunload",guard);persistNow();if(startedAt.current!=null)void syncNow(); };
  }, [status]);

  useEffect(() => () => {
    trackingRef.current=false;
    stopGps();
    if(wakeLock.current)void wakeLock.current.release().catch(()=>undefined);
  }, []);

  useEffect(() => {
    setName(category === "running" ? "Correr" : "Andar");
  }, [category]);

  useEffect(()=>{let cancelled=false;(async()=>{const local=loadLocalDraft(owner);let remote:RemoteDraft|null=null;try{remote=await apiRequest<RemoteDraft|null>("/activity-drafts/active",{token});}catch{/* recuperar copia local sin red */}if(cancelled||startedAt.current!=null)return;const candidate=pickDraft(owner,local,remote);if(!candidate)return;if(candidate.points.length<2){clearLocalDraft();void apiRequest("/activity-drafts/"+candidate.clientId,{method:"DELETE",token}).catch(()=>undefined);return;}setRecovered(candidate);})();return()=>{cancelled=true;};},[token,owner]);
  function stopGps() {
    if (watchId.current != null && navigator.geolocation) { navigator.geolocation.clearWatch(watchId.current); watchId.current = null; }
    if (watchRetryTimer.current != null) { window.clearTimeout(watchRetryTimer.current); watchRetryTimer.current = null; }
    watchRetryAttempts.current=0;
  }

  function startGps(resume?:StoredDraft){setError("");setGpsError("");setNotice("");if(!navigator.geolocation){setGpsError("Este navegador no permite geolocalización. Puedes registrar la actividad manualmente.");return;}if(!window.isSecureContext){setGpsError("El GPS requiere HTTPS. Puedes registrar la actividad manualmente.");return;}if(!resume&&clientId.current){const old=clientId.current;void apiRequest("/activity-drafts/"+old,{method:"DELETE",token}).catch(()=>undefined);}const startMs=resume?Date.parse(resume.startedAt):Date.now(),initial=resume?resume.points:[];if(resume)meta.current={...meta.current,name:resume.kind,category:resume.category,date:resume.performedOn};clientId.current=resume?resume.clientId:newClientId();pointsRef.current=initial;syncedUpTo.current=0;lastFixAt.current=null;startedAt.current=startMs;setRecovered(null);setPoints(initial);setSession(null);setElapsed(Date.now()-startMs);setAccuracy(null);setSignalAge(null);setSync("idle");setReceivedFixes(0);setAcceptedFixes(0);setRejectedFixes(0);trackingRef.current=true;setStatus("tracking");onTrackingChange(true);try{beginWatch();void acquireWakeLock();persistNow();void syncNow();}catch{trackingRef.current=false;stopGps();releaseWakeLock();startedAt.current=null;setStatus("idle");onTrackingChange(false);setGpsError("No se pudo iniciar el GPS. Comprueba los permisos del navegador.");}}
  function resumeRecovered(){if(!recovered)return;onCategoryChange(recovered.category);setName(recovered.kind);setDate(recovered.performedOn);startGps(recovered);}
  function saveRecoveredAsIs(){if(!recovered)return;const start=Date.parse(recovered.startedAt),end=lastPointTime(recovered.points)??start;clientId.current=recovered.clientId;pointsRef.current=recovered.points;syncedUpTo.current=recovered.points.length;onCategoryChange(recovered.category);setName(recovered.kind);setDate(recovered.performedOn);setPoints(recovered.points);setSession({start,end});setElapsed(end-start);setStatus("finished");setRecovered(null);}


  function finishGps(){const end=Date.now(),start=startedAt.current??end;persistNow();void syncNow();trackingRef.current=false;stopGps();releaseWakeLock();startedAt.current=null;setSession({start,end});setElapsed(end-start);setStatus("finished");onTrackingChange(false);}

  function resetTracking(){trackingRef.current=false;stopGps();releaseWakeLock();startedAt.current=null;clientId.current=null;pointsRef.current=[];syncedUpTo.current=0;lastFixAt.current=null;clearLocalDraft();setPoints([]);setSession(null);setElapsed(0);setAccuracy(null);setSignalAge(null);setSync("idle");setNotice("");setRecovered(null);setGpsError("");setStatus("idle");onTrackingChange(false);}
  function discardGps(){const id=clientId.current,pending=syncPromise.current;resetTracking();if(id)void(async()=>{await pending;await apiRequest("/activity-drafts/"+id,{method:"DELETE",token}).catch(()=>undefined);})();}
  function discardRecovered(){if(!recovered)return;clearLocalDraft();void apiRequest("/activity-drafts/"+recovered.clientId,{method:"DELETE",token}).catch(()=>undefined);setRecovered(null);}

  function switchToManual() {
    if (status === "tracking" || points.length) discardGps();
    setManual(true);
    setGpsError("");
  }

  async function saveActivity(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!manual && (status !== "finished" || points.length < 2)) {
      setError("Finaliza un recorrido GPS con al menos dos ubicaciones, o selecciona el registro manual.");
      return;
    }
    const durationMin = manual ? Number(manualDuration) : Math.max(1, Math.ceil(stats.activeMs / 60000));
    if (!Number.isInteger(durationMin) || durationMin < 1 || durationMin > 600) {
      setError("La duración debe estar entre 1 y 600 minutos.");
      return;
    }
    if (manual && manualDistance && (Number(manualDistance) <= 0 || Number(manualDistance) > 500)) {
      setError("La distancia debe estar entre 0 y 500 km.");
      return;
    }
    setBusy(true);
    try {
      await syncNow();
      await apiRequest("/workouts", {
        method: "POST",
        token,
        body: {
          performed_on: date,
          kind: name,
          category,
          duration_min: durationMin,
          distance_km: manual ? (manualDistance ? Number(manualDistance) : null) : (distance>0?distance:null),
          elevation_gain_m: manual ? (manualElevation ? Number(manualElevation) : null) : (hasAltitude ? Math.round(elevation) : null),
          steps: steps ? Number(steps) : null,
          avg_hr_bpm: heartRate ? Number(heartRate) : null,
          notes: notes || null,
          sets: [],
          exercise_durations_min: {},
          route_points: manual ? [] : points,
          draft_id: manual ? null : clientId.current,
          estimate_calories: true
        }
      });
      resetTracking();
      setManual(false);
      setManualDuration("30");
      setNotes("");
      setSteps("");
      setHeartRate("");
      setManualDistance("");
      setManualElevation("");
      onSaved();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "No se pudo guardar la actividad.");
    } finally {
      setBusy(false);
    }
  }

  const title = category === "running" ? "Registrar carrera" : "Registrar paseo";
  const activity = category === "running" ? "RUNNING" : "WALKING";

  return (
    <div className="training-cardio-workspace">
      <section className="panel">
        <div className="cardio-title-row">
          <span className="cardio-icon">{category === "running" ? "🏃" : "🚶"}</span>
          <div>
            <span className="eyebrow">{activity}</span>
            <h3>{title}</h3>
            <p className="muted">Seguimiento GPS, distancia y ritmo de tu actividad.</p>
          </div>
        </div>
        <form className="stack-form" onSubmit={saveActivity}>
          <label>Nombre de la actividad<input value={name} required onChange={event => setName(event.target.value)} /></label>
          <div className="training-form-row">
            <label>Fecha<input type="date" max={new Date().toLocaleDateString("sv-SE")} value={date} onChange={event => setDate(event.target.value)} /></label>
            <label>Modalidad<select value={category} onChange={event => onCategoryChange(event.target.value as "walking" | "running")}><option value="walking">Andar</option><option value="running">Correr</option></select></label>
          </div>
          {!manual ? (
            <>
            {recovered && status==="idle" && <div className="cardio-recover" role="alert"><strong>Tienes un recorrido sin terminar</strong><p>{recovered.kind} · {new Date(recovered.startedAt).toLocaleString("es-ES")} · {recovered.points.length} puntos GPS · {routeStats(recovered.points,null,null).distanceKm.toLocaleString("es-ES",{maximumFractionDigits:2})} km</p><div className="cardio-route-actions"><button type="button" className="primary-button" onClick={resumeRecovered}>Reanudar</button><button type="button" className="secondary-button" onClick={saveRecoveredAsIs}>Guardar tal cual</button><button type="button" className="secondary-button" onClick={discardRecovered}>Descartar</button></div></div>}
            <div className="cardio-gps-controls">
              <div className="cardio-live-clock">{durationText(elapsed)}</div>
              <span className={"cardio-status " + status}>{status === "tracking" ? "GPS EN DIRECTO" : status === "finished" ? "RECORRIDO FINALIZADO" : "LISTO PARA SALIR"}</span>
              {status === "idle" && <button type="button" className="primary-button cardio-main-action" onClick={()=>startGps()}>Iniciar recorrido GPS</button>}
              {status === "tracking" && <button type="button" className="primary-button cardio-main-action" onClick={finishGps}>Finalizar recorrido</button>}
              {status === "finished" && <div className="cardio-route-actions"><button type="button" className="secondary-button" onClick={discardGps}>Descartar recorrido</button><button type="button" className="primary-button" onClick={()=>startGps()}>Repetir recorrido</button></div>}
              {status!=="tracking"&&<p className="muted">Al iniciar, el navegador solicitará permiso de ubicación. Mantén SmartFit abierto y la pantalla encendida. Con el móvil bloqueado el navegador puede dejar de entregar ubicaciones.</p>}
              {status==="tracking"&&<div className="cardio-tracking-health"><span className={wake==="on"?"ok":"warn"}>{wake==="on"?"Pantalla activa":wake==="unsupported"?"Pantalla: desactiva el bloqueo automático":"Pantalla: no se puede mantener encendida"}</span><span className={sync==="error"?"warn":"ok"}>{sync==="error"?"Sin conexión: copia local guardada":sync==="ok"?"Recorrido guardado":"Guardando…"}</span><span>GPS: {receivedFixes} lecturas · {acceptedFixes} aceptadas · {rejectedFixes} filtradas</span></div>}
              {status==="tracking"&&signalAge!=null&&signalAge>STALE_SIGNAL_S&&<p className="cardio-gps-error">Sin señal GPS desde hace {signalAge<120?signalAge+" s":minutesText(signalAge*1000)}. Mantén SmartFit en pantalla.</p>}
              {notice&&<p className="cardio-gps-error">{notice}</p>}
              {gpsError && <p className="cardio-gps-error">{gpsError}</p>}
            </div>
            </>
          ) : (
            <div className="cardio-manual-fields">
              <p className="muted">Introduce los datos manualmente si no quieres usar el GPS o no tienes permiso de ubicación.</p>
              <div className="training-form-row">
                <label>Duración (min)<input type="number" min="1" max="600" value={manualDuration} onChange={event => setManualDuration(event.target.value)} /></label>
                <label>Distancia (km)<input type="number" min="0" max="500" step=".01" value={manualDistance} onChange={event => setManualDistance(event.target.value)} /></label>
              </div>
              <label>Desnivel positivo (m)<input type="number" min="0" max="10000" value={manualElevation} onChange={event => setManualElevation(event.target.value)} /></label>
              <button type="button" className="secondary-button" onClick={() => setManual(false)}>Volver al GPS</button>
            </div>
          )}
          {!manual&&status==="finished"&&stats.gapMs>0&&<p className="cardio-gps-error">Durante {minutesText(stats.gapMs)} no llegaron lecturas GPS. Ese tramo no cuenta: se registra {minutesText(stats.activeMs)} de tiempo activo.</p>}
          {!manual && status !== "tracking" && <button type="button" className="cardio-manual-link" onClick={switchToManual}>Registrar manualmente sin GPS</button>}
          {!manual && status === "finished" && (
            <div className="cardio-final-metrics">
              <div><span>Distancia</span><strong>{distance.toLocaleString("es-ES", { maximumFractionDigits: 2 })} km</strong></div>
              <div><span>Ritmo medio</span><strong>{paceText(stats.activeMs, distance)}</strong></div>
              <div><span>Desnivel GPS</span><strong>{hasAltitude ? Math.round(elevation).toLocaleString("es-ES") : "—"} m</strong></div>
            </div>
          )}
          <div className="training-form-row">
            <label>Pasos (opcional)<input type="number" min="0" max="200000" value={steps} onChange={event => setSteps(event.target.value)} /></label>
            <label>FC media (ppm)<input type="number" min="30" max="230" value={heartRate} onChange={event => setHeartRate(event.target.value)} /></label>
          </div>
          <label>Notas<textarea rows={2} maxLength={1000} value={notes} onChange={event => setNotes(event.target.value)} placeholder="Sensaciones, terreno, clima…" /></label>
          <button className="primary-button cardio-save-action" disabled={busy || (!manual && (status !== "finished" || points.length < 2)) || status === "tracking"}>{busy ? "Guardando…" : "Guardar actividad"}</button>
          <button type="button" className="cardio-exit-link" onClick={() => { if (status === "tracking" || points.length) { if (!window.confirm("Se descartará el recorrido GPS que no has guardado. ¿Quieres salir?")) return; discardGps(); } onExit(); }}>Volver a entrenamiento de fuerza</button>
        </form>
      </section>
      <section className="panel cardio-route-panel">
        <div className="list-heading">
          <div><h3>Tu recorrido</h3><p className="muted">{points.length ? points.length + " puntos GPS registrados" : "El trazado aparecerá aquí al iniciar el recorrido."}</p></div>
          <span className="count-chip">{accuracy != null ? "±" + Math.round(accuracy) + " m" : "GPS"}</span>
        </div>
        <div className="cardio-route-map">
          {points.length > 1 ? <GeoRouteMap points={points} /> : (
            <div className="cardio-route-empty"><span>⌖</span><strong>Ruta GPS</strong><p>Cuando empieces, SmartFit irá dibujando tu recorrido sobre el mapa.</p></div>
          )}
        </div>
        <div className="cardio-live-stats">
          <div><span>Tiempo</span><strong>{durationText(elapsed)}</strong></div>
          <div><span>Distancia</span><strong>{distance.toLocaleString("es-ES", { maximumFractionDigits: 2 })} km</strong></div>
          <div><span>Ritmo</span><strong>{paceText(stats.activeMs, distance)}</strong></div>
        </div>
        <p className="muted cardio-privacy-note">Tu ubicación solo se solicita al pulsar «Iniciar recorrido». Mientras grabas, los puntos se guardan en tu dispositivo y en tu cuenta cada pocos segundos para recuperar el recorrido si la página se interrumpe.</p>
        <p className="muted cardio-privacy-note">Para usarla en exteriores, concede permiso de ubicación y mantén SmartFit visible. El registro con pantalla bloqueada requiere la app móvil.</p>
      </section>
    </div>
  );
}
