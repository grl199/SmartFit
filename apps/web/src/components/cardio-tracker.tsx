"use client";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { apiRequest } from "@/lib/api";
import { GeoRouteMap } from "@/components/geo-route-map";

type RoutePoint = {
  lat: number;
  lng: number;
  altitude_m: number | null;
  accuracy_m: number | null;
  recorded_at: string;
};

type Props = {
  token: string;
  category: "walking" | "running";
  onCategoryChange: (category: "walking" | "running") => void;
  onExit: () => void;
  onSaved: () => void;
};

const distanceKm = (a: RoutePoint, b: RoutePoint) => {
  const rad = (value: number) => value * Math.PI / 180;
  const dLat = rad(b.lat - a.lat);
  const dLng = rad(b.lng - a.lng);
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 6371.0088 * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(Math.max(0, 1 - x)));
};

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

export function CardioTracker({ token, category, onCategoryChange, onExit, onSaved }: Props) {
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
  const [elapsed, setElapsed] = useState(0);
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [gpsError, setGpsError] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const watchId = useRef<number | null>(null);
  const startedAt = useRef<number | null>(null);

  const distance = useMemo(() => points.slice(1).reduce((total, point, index) => total + distanceKm(points[index], point), 0), [points]);
  const elevation = useMemo(() => points.slice(1).reduce((total, point, index) => {
    const previous = points[index];
    return total + (point.altitude_m != null && previous.altitude_m != null ? Math.max(0, point.altitude_m - previous.altitude_m) : 0);
  }, 0), [points]);

  useEffect(() => {
    if (status !== "tracking") return;
    const tick = () => {
      if (startedAt.current != null) setElapsed(Date.now() - startedAt.current);
    };
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [status]);

  useEffect(() => () => {
    if (watchId.current != null && navigator.geolocation) navigator.geolocation.clearWatch(watchId.current);
  }, []);

  useEffect(() => {
    setName(category === "running" ? "Correr" : "Andar");
  }, [category]);

  function stopGps() {
    if (watchId.current != null && navigator.geolocation) {
      navigator.geolocation.clearWatch(watchId.current);
      watchId.current = null;
    }
  }

  function startGps() {
    setError("");
    setGpsError("");
    if (!navigator.geolocation) {
      setGpsError("Este navegador no permite geolocalización. Puedes registrar la actividad manualmente.");
      return;
    }
    if (!window.isSecureContext) {
      setGpsError("El GPS requiere una conexión segura HTTPS. Puedes registrar la actividad manualmente.");
      return;
    }
    setPoints([]);
    setElapsed(0);
    setAccuracy(null);
    startedAt.current = Date.now();
    setStatus("tracking");
    try {
      watchId.current = navigator.geolocation.watchPosition(position => {
        const coords = position.coords;
        if (coords.accuracy > 80) return;
        const point: RoutePoint = {
          lat: coords.latitude,
          lng: coords.longitude,
          altitude_m: coords.altitude,
          accuracy_m: coords.accuracy,
          recorded_at: new Date(position.timestamp || Date.now()).toISOString()
        };
        setAccuracy(coords.accuracy);
        setPoints(current => {
          const previous = current[current.length - 1];
          if (previous && distanceKm(previous, point) < 0.005 && Date.now() - Date.parse(previous.recorded_at) < 5000) return current;
          return [...current, point].slice(-10000);
        });
      }, geoError => {
        const message = geoError.code === 1
          ? "No se ha permitido el acceso a la ubicación. Activa el permiso en el navegador o registra la actividad manualmente."
          : geoError.code === 2
            ? "No se pudo obtener una señal GPS. Prueba en el exterior o usa el registro manual."
            : "La señal GPS ha tardado demasiado. Comprueba la ubicación del dispositivo.";
        setGpsError(message);
        if (geoError.code === 1) {
          stopGps();
          startedAt.current = null;
          setStatus("idle");
        }
      }, { enableHighAccuracy: true, maximumAge: 1000, timeout: 20000 });
    } catch {
      startedAt.current = null;
      setStatus("idle");
      setGpsError("No se pudo iniciar el GPS. Comprueba los permisos del navegador.");
    }
  }

  function finishGps() {
    if (startedAt.current != null) setElapsed(Date.now() - startedAt.current);
    stopGps();
    startedAt.current = null;
    setStatus("finished");
  }

  function discardGps() {
    stopGps();
    startedAt.current = null;
    setPoints([]);
    setElapsed(0);
    setAccuracy(null);
    setGpsError("");
    setStatus("idle");
  }

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
    const durationMin = manual ? Number(manualDuration) : Math.max(1, Math.ceil(elapsed / 60000));
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
      await apiRequest("/workouts", {
        method: "POST",
        token,
        body: {
          performed_on: date,
          kind: name,
          category,
          duration_min: durationMin,
          distance_km: manual ? (manualDistance ? Number(manualDistance) : null) : distance,
          elevation_gain_m: manual ? (manualElevation ? Number(manualElevation) : null) : Math.round(elevation),
          steps: steps ? Number(steps) : null,
          avg_hr_bpm: heartRate ? Number(heartRate) : null,
          notes: notes || null,
          sets: [],
          exercise_durations_min: {},
          route_points: manual ? [] : points,
          estimate_calories: true
        }
      });
      discardGps();
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
            <div className="cardio-gps-controls">
              <div className="cardio-live-clock">{durationText(elapsed)}</div>
              <span className={"cardio-status " + status}>{status === "tracking" ? "GPS EN DIRECTO" : status === "finished" ? "RECORRIDO FINALIZADO" : "LISTO PARA SALIR"}</span>
              {status === "idle" && <button type="button" className="primary-button cardio-main-action" onClick={startGps}>Iniciar recorrido GPS</button>}
              {status === "tracking" && <button type="button" className="primary-button cardio-main-action" onClick={finishGps}>Finalizar recorrido</button>}
              {status === "finished" && <div className="cardio-route-actions"><button type="button" className="secondary-button" onClick={discardGps}>Descartar recorrido</button><button type="button" className="primary-button" onClick={startGps}>Repetir recorrido</button></div>}
              <p className="muted">Al iniciar, el navegador solicitará permiso de ubicación. Mantén SmartFit abierto durante el recorrido.</p>
              {gpsError && <p className="cardio-gps-error">{gpsError}</p>}
            </div>
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
          {!manual && status === "idle" && <button type="button" className="cardio-manual-link" onClick={switchToManual}>Registrar manualmente sin GPS</button>}
          {!manual && status === "finished" && (
            <div className="cardio-final-metrics">
              <div><span>Distancia</span><strong>{distance.toLocaleString("es-ES", { maximumFractionDigits: 2 })} km</strong></div>
              <div><span>Ritmo medio</span><strong>{paceText(elapsed, distance)}</strong></div>
              <div><span>Desnivel GPS</span><strong>{Math.round(elevation).toLocaleString("es-ES")} m</strong></div>
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
          <div><span>Ritmo</span><strong>{paceText(elapsed, distance)}</strong></div>
        </div>
        <p className="muted cardio-privacy-note">Tu ubicación solo se solicita al pulsar «Iniciar recorrido». Los puntos GPS se guardan junto a esta actividad cuando la registras.</p>
        <p className="muted cardio-privacy-note">La vista muestra el trazado GPS. Para usarla en exteriores, concede permiso de ubicación y mantén el navegador abierto.</p>
      </section>
    </div>
  );
}
