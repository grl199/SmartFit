"use client";

import { FormEvent, useEffect, useState } from "react";
import type { components } from "@smartfit/contracts";
import { ApiError, authenticate, completeOnboarding, getCurrentUser, logoutWebSession } from "@/lib/api";
import { Workspace } from "@/components/workspace";

type User = components["schemas"]["UserOut"];
type OnboardingResult = components["schemas"]["OnboardingOut"];
type Mode = "login" | "register";

const initialProfile = {
  sex: "male" as "male" | "female",
  birth_date: "1995-01-01",
  height_cm: "175",
  weight_kg: "75",
  activity_level: "moderate" as "sedentary" | "light" | "moderate" | "high" | "very_high",
  goal: "recomposition" as "gain_muscle" | "lose_fat" | "definition" | "recomposition" | "maintain",
  experience_level: "beginner" as "beginner" | "intermediate" | "advanced",
  available_training_days: "3",
};

export default function Home() {
  const [mode, setMode] = useState<Mode>("login");
  const [user, setUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [sessionCheckError, setSessionCheckError] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<OnboardingResult | null>(null);
  const [profile, setProfile] = useState(initialProfile);

  useEffect(() => {
    let active = true;
    getCurrentUser()
      .then((currentUser) => { if (active) setUser(currentUser); })
      .catch((err: unknown) => {
        if (!active) return;
        // 401 significa que no hay una sesión válida; otros errores son fallos
        // de API/despliegue y no deben disfrazarse como un logout.
        if (err instanceof ApiError && err.status === 401) {
          setUser(null);
          return;
        }
        setSessionCheckError(
          err instanceof Error ? err.message : "No se pudo comprobar la sesión. Revisa la conexión con SmartFit API.",
        );
      })
      .finally(() => { if (active) setAuthReady(true); });
    return () => { active = false; };
  }, []);

  async function onAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const response = await authenticate(mode, {
        name: String(form.get("name") ?? ""),
        password: String(form.get("password") ?? ""),
      });
      setUser(response.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo iniciar sesión.");
    } finally {
      setBusy(false);
    }
  }

  async function onOnboarding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const input = {
        ...profile,
        height_cm: Number(profile.height_cm),
        weight_kg: Number(profile.weight_kg),
        available_training_days: Number(profile.available_training_days),
      } as unknown as components["schemas"]["OnboardingIn"];
      const response = await completeOnboarding(input);
      setResult(response);
      setUser((current: User | null) => current ? { ...current, onboarding_completed: true } : current);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar el perfil.");
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    try { await logoutWebSession(); } finally {
      setUser(null);
      setResult(null);
    }
  }

  if (!authReady) {
    return (
      <main className="shell auth-shell">
        <section className="auth-panel">
          <div className="form-card">
            <div className="eyebrow">SMARTFIT</div>
            <p className="intro">Comprobando tu sesión…</p>
          </div>
        </section>
      </main>
    );
  }

  if (sessionCheckError) {
    return (
      <main className="shell auth-shell">
        <section className="auth-panel">
          <div className="form-card">
            <div className="eyebrow">SMARTFIT / SESIÓN</div>
            <h2>No se pudo comprobar tu sesión.</h2>
            <p className="intro">{sessionCheckError}</p>
            <button className="primary-button" onClick={() => window.location.reload()}>
              Reintentar conexión
            </button>
          </div>
        </section>
      </main>
    );
  }

  if (user?.onboarding_completed) {
    return (
      <Workspace
        token=""
        userName={user.name}
        onLogout={logout}
      />
    );
  }

  if (user && !user.onboarding_completed) {
    return (
      <main className="shell">
        <header className="topbar"><a className="brand" href="#"><span className="brand-mark">S</span> SMARTFIT</a><button className="quiet-button" onClick={logout}>Cerrar sesión</button></header>
        <section className="form-card wide">
          <div className="eyebrow">01 / CONFIGURACIÓN INICIAL</div>
          <h1>Construyamos tu <em>punto de partida.</em></h1>
          <p className="intro">Estos datos permiten calcular tus necesidades y adaptar el plan a tu objetivo.</p>
          <form onSubmit={onOnboarding} className="form-grid">
            <label>Sexo biológico<select value={profile.sex} onChange={e => setProfile({...profile, sex: e.target.value as typeof profile.sex})}><option value="male">Hombre</option><option value="female">Mujer</option></select></label>
            <label>Fecha de nacimiento<input type="date" required value={profile.birth_date} onChange={e => setProfile({...profile, birth_date: e.target.value})} /></label>
            <label>Altura (cm)<input type="number" min="100" max="250" required value={profile.height_cm} onChange={e => setProfile({...profile, height_cm: e.target.value})} /></label>
            <label>Peso actual (kg)<input type="number" min="30.1" max="299.9" step="0.1" required value={profile.weight_kg} onChange={e => setProfile({...profile, weight_kg: e.target.value})} /></label>
            <label className="span-two">Nivel de actividad<select value={profile.activity_level} onChange={e => setProfile({...profile, activity_level: e.target.value as typeof profile.activity_level})}><option value="sedentary">Sedentario</option><option value="light">Ligero (1–2 días/semana)</option><option value="moderate">Moderado (3–5 días/semana)</option><option value="high">Alto (6–7 días/semana)</option><option value="very_high">Muy alto</option></select></label>
            <label>Objetivo<select value={profile.goal} onChange={e => setProfile({...profile, goal: e.target.value as typeof profile.goal})}><option value="gain_muscle">Ganar músculo</option><option value="lose_fat">Perder grasa</option><option value="definition">Definición</option><option value="recomposition">Recomposición corporal</option><option value="maintain">Mantener</option></select></label>
            <label>Experiencia<select value={profile.experience_level} onChange={e => setProfile({...profile, experience_level: e.target.value as typeof profile.experience_level})}><option value="beginner">Principiante</option><option value="intermediate">Intermedio</option><option value="advanced">Avanzado</option></select></label>
            <label className="span-two">Días disponibles para entrenar<select value={profile.available_training_days} onChange={e => setProfile({...profile, available_training_days: e.target.value})}>{[1,2,3,4,5,6,7].map(n => <option key={n} value={n}>{n} días por semana</option>)}</select></label>
            <button className="primary-button span-two" disabled={busy}>{busy ? "Guardando tu perfil…" : "Guardar y calcular mis objetivos"}</button>
          </form>
          {error && <p className="error">{error}</p>}
          <p className="footnote">El cálculo de objetivos usa el servicio de IA configurado en el backend. Si no está disponible, podrás reintentar cuando esté configurado.</p>
        </section>
      </main>
    );
  }

  return (
    <main className="shell auth-shell">
      <div className="hero-copy">
        <a className="brand" href="#"><span className="brand-mark">S</span> SMARTFIT</a>
        <div className="hero-content">
          <div className="eyebrow">ENTRENAMIENTO · NUTRICIÓN · HÁBITOS</div>
          <h1>Tu progreso,<br /><em>con criterio.</em></h1>
          <p>Una visión conectada de tu salud y tu rendimiento. Menos ruido, mejores decisiones y constancia que se nota.</p>
          <div className="hero-foot"><span className="status-dot" /> Tu espacio. Tu ritmo. Tu evolución.</div>
        </div>
        <span className="hero-index">SMARTFIT / 001</span>
      </div>
      <section className="auth-panel">
        <div className="form-card">
          <div className="eyebrow">BIENVENIDO A SMARTFIT</div>
          <h2>{mode === "login" ? "Qué bueno verte." : "Empieza por aquí."}</h2>
          <p className="intro">{mode === "login" ? "Accede a tu espacio personal." : "Crea tu cuenta y configura tu punto de partida."}</p>
          <form onSubmit={onAuth}>
            <label>Nombre de usuario<input name="name" autoComplete="username" minLength={3} maxLength={40} required placeholder="Tu usuario" /></label>
            <label>Contraseña<input name="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={8} maxLength={128} required placeholder="Mínimo 8 caracteres" /></label>
            <button className="primary-button" disabled={busy}>{busy ? "Un momento…" : mode === "login" ? "Iniciar sesión" : "Crear cuenta"} <span>↗</span></button>
          </form>
          {error && <p className="error">{error}</p>}
          <p className="switch-mode">{mode === "login" ? "¿Aún no tienes cuenta?" : "¿Ya tienes cuenta?"} <button onClick={() => {setMode(mode === "login" ? "register" : "login"); setError("");}}>{mode === "login" ? "Regístrate" : "Inicia sesión"}</button></p>
          <div className="secure-note"><span>⌁</span> Conexión segura con la API de SmartFit</div>
        </div>
      </section>
    </main>
  );
}
