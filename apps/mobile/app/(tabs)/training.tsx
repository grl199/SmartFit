import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Alert, Linking, Text, View } from "react-native";
import { api } from "@/lib/api";
import { dateLabel, localDateISO } from "@/lib/format";
import { useAuth } from "@/auth/AuthProvider";
import { AppButton, ChoiceRow, ErrorMessage, Field, Muted, PageTitle, Panel, Screen, SectionTitle } from "@/components/ui";
import { colors } from "@/theme";
import { ExerciseAnimation } from "@/components/ExerciseAnimation";
import { CardioGpsTracker } from "@/components/CardioGpsTracker";

type Exercise = { id: number; name: string; kind: string; primary_muscle: string; secondary_muscles: string[]; equipment: string[] };
type SetDraft = { reps: string; weight_kg: string; reached_failure: string };
type DraftExercise = { exercise: Exercise; sets: SetDraft[]; duration_min: string };
type Workout = {
  id: number; performed_on: string; kind: string; category?: string | null; duration_min: number;
  kcal_burned?: number | null; kcal_source?: string | null; kcal_note?: string | null;
  distance_km?: number | null; elevation_gain_m?: number | null; steps?: number | null;
  avg_hr_bpm?: number | null; notes?: string | null;
  exercises: Array<{ exercise_id: number; exercise: string; primary_muscle: string; duration_min?: number | null; sets: Array<{ reps: number; weight_kg?: number | null; reached_failure?: boolean | null }> }>;
  feedback?: Array<{ exercise: string; message: string }>;
};
type PlanExercise = { id: number; exercise_id: number; exercise: string; sets: number; reps_min: number; reps_max: number; rest_s?: number | null; notes?: string | null };
type PlanDay = { id: number; position: number; label: string; muscle_focus: string[]; exercises: PlanExercise[] };
type PlanResponse = { has_plan: boolean; plan?: { id: number; name: string; source: string; days: PlanDay[] } | null; legacy_markdown?: string | null };
type MuscleSummary = { start: string; end: string; sessions: number; muscles: Record<string, { sets: number; strength_sets: number; cardio_sets: number; volume_kg: number; exercises: string[] }> };
type Content = { description?: string | null; start_position?: string | null; instructions?: string[]; common_mistakes?: string[]; image_url?: string | null; video_url?: string | null; media_type?: string | null; media_credit?: string | null };
type ExerciseHistory = Array<{ workout_id: number; date: string; sets: Array<{ set_number: number; reps: number; weight_kg?: number | null; reached_failure?: boolean | null; rpe?: number | null }> }>;
type ExerciseProgress = Array<{ date: string; best_weight_kg?: number | null; est_1rm_kg?: number | null; sets: number; volume_kg: number }>;
type Tab = "session" | "plan" | "history" | "muscles" | "gps";
type PlanExerciseDraft = { exercise_id: number; exercise: string; sets: string; reps_min: string; reps_max: string; rest_s: string; notes: string };
const muscleOptions = ["chest","shoulders","biceps","triceps","forearms","abs","quadriceps","hamstrings","glutes","calves","lats","upper_back","lower_back","traps","neck","abductors","adductors"];
const equipmentOptions = ["none","barbell","dumbbell","machine","kettlebell","resistance_band","bench","plate","wheel","medicine_ball","box","suspension","other"];
const kindFilterOptions = [
  { value: "", label: "Todos" }, { value: "strength", label: "Fuerza" },
  { value: "full_body", label: "Cuerpo entero" }, { value: "stretching", label: "Estiramientos" },
];
const muscleFilterOptions = [
  { value: "", label: "Todos" }, { value: "chest", label: "Pecho" }, { value: "upper_back", label: "Espalda alta" }, { value: "lower_back", label: "Espalda baja" }, { value: "lats", label: "Dorsales" },
  { value: "shoulders", label: "Hombros" }, { value: "biceps", label: "Bíceps" },
  { value: "triceps", label: "Tríceps" }, { value: "abs", label: "Abdomen" },
  { value: "quadriceps", label: "Cuádriceps" }, { value: "hamstrings", label: "Isquios" },
  { value: "glutes", label: "Glúteos" }, { value: "calves", label: "Gemelos" },
];
const equipmentFilterOptions = [
  { value: "", label: "Todos" }, { value: "none", label: "Sin equipo" }, { value: "barbell", label: "Barra" },
  { value: "dumbbell", label: "Mancuernas" }, { value: "machine", label: "Máquina" },
  { value: "kettlebell", label: "Pesa rusa" }, { value: "resistance_band", label: "Banda" },
  { value: "bench", label: "Banco" }, { value: "suspension", label: "TRX" },
];
const categories = [
  { value: "strength", label: "Fuerza" }, { value: "walking", label: "Andar" },
  { value: "running", label: "Correr" }, { value: "sport", label: "Deporte" },
  { value: "full_body", label: "Cuerpo entero" }, { value: "stretching", label: "Estirar" },
];
const emptySet = (): SetDraft => ({ reps: "10", weight_kg: "", reached_failure: "" });
const fmt = (value: number | null | undefined, digits = 0) => value == null ? "—" : value.toLocaleString("es-ES", { maximumFractionDigits: digits });

export default function TrainingScreen() {
  const { token } = useAuth();
  const [tab, setTab] = useState<Tab>("session");
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [workouts, setWorkouts] = useState<Workout[]>([]);
  const [catalog, setCatalog] = useState<Exercise[]>([]);
  const [muscles, setMuscles] = useState<MuscleSummary | null>(null);
  const [drafts, setDrafts] = useState<DraftExercise[]>([]);
  const [query, setQuery] = useState("");
  const [kindFilter, setKindFilter] = useState("");
  const [muscleFilter, setMuscleFilter] = useState("");
  const [equipmentFilter, setEquipmentFilter] = useState("");
  const [includeSecondary, setIncludeSecondary] = useState("true");
  const [selectedExercise, setSelectedExercise] = useState<Exercise | null>(null);
  const [exerciseContent, setExerciseContent] = useState<Content | null>(null);
  const [exerciseHistory, setExerciseHistory] = useState<ExerciseHistory>([]);
  const [exerciseProgress, setExerciseProgress] = useState<ExerciseProgress>([]);
  const [date, setDate] = useState(localDateISO());
  const [name, setName] = useState("Entrenamiento");
  const [category, setCategory] = useState("strength");
  const [duration, setDuration] = useState("60");
  const [distance, setDistance] = useState("");
  const [steps, setSteps] = useState("");
  const [elevation, setElevation] = useState("");
  const [heartRate, setHeartRate] = useState("");
  const [notes, setNotes] = useState("");
  const [period, setPeriod] = useState("30");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editingDay, setEditingDay] = useState<PlanDay | null>(null);
  const [dayLabel, setDayLabel] = useState("");
  const [dayDraft, setDayDraft] = useState<PlanExerciseDraft[]>([]);
  const [planQuery, setPlanQuery] = useState("");
  const [planResults, setPlanResults] = useState<Exercise[]>([]);
  const [newExerciseName, setNewExerciseName] = useState("");
  const [newExerciseKind, setNewExerciseKind] = useState("strength");
  const [newExerciseMuscle, setNewExerciseMuscle] = useState("chest");
  const [newExerciseEquipment, setNewExerciseEquipment] = useState("none");

  const loadAll = useCallback(async () => {
    if (!token) return;
    try {
      setError("");
      const [p, w, e, m] = await Promise.all([
        api<PlanResponse>("/plan", token),
        api<Workout[]>("/workouts?days=365", token),
        api<Exercise[]>("/exercises?include_secondary=true", token),
        api<MuscleSummary>("/training/muscles?days=" + period, token),
      ]);
      setPlan(p); setWorkouts(w); setCatalog(e); setMuscles(m);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo cargar tu entrenamiento.");
    } finally {
      setLoading(false);
    }
  }, [token, period]);

  useEffect(() => { void loadAll(); }, [loadAll]);

  async function refreshMuscles(nextPeriod: string) {
    if (!token) return;
    setPeriod(nextPeriod);
    try {
      setMuscles(await api<MuscleSummary>("/training/muscles?days=" + nextPeriod, token));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo cargar el resumen muscular.");
    }
  }

  async function refreshCatalog() {
    if (!token) return;
    try {
      const params = new URLSearchParams();
      params.set("include_secondary", includeSecondary);
      if (query.trim()) params.set("q", query.trim());
      if (kindFilter) params.set("kind", kindFilter);
      if (muscleFilter) params.set("muscles", muscleFilter);
      if (equipmentFilter) params.set("equipment", equipmentFilter);
      setCatalog(await api<Exercise[]>("/exercises?" + params.toString(), token));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo buscar en el catálogo.");
    }
  }

  async function showExercise(exercise: Exercise) {
    if (!token) return;
    setSelectedExercise(exercise);
    setExerciseContent(null);
    setExerciseHistory([]);
    setExerciseProgress([]);
    try {
      const [content, history, progress] = await Promise.all([
        api<Content>("/exercises/" + exercise.id + "/content", token),
        api<ExerciseHistory>("/exercises/" + exercise.id + "/history?limit=10", token),
        api<ExerciseProgress>("/exercises/" + exercise.id + "/progress", token),
      ]);
      setExerciseContent(content);
      setExerciseHistory(history);
      setExerciseProgress(progress);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo cargar el historial del ejercicio.");
    }
  }

  function addExercise(exercise: Exercise) {
    setDrafts(current => {
      const existing = current.find(item => item.exercise.id === exercise.id);
      if (existing) return current.map(item => item.exercise.id === exercise.id
        ? { ...item, sets: [...item.sets, emptySet()] } : item);
      return [...current, { exercise, sets: [emptySet()], duration_min: "" }];
    });
    setNotice(exercise.name + " añadido a la sesión.");
  }

  function updateSet(exerciseId: number, setIndex: number, patch: Partial<SetDraft>) {
    setDrafts(current => current.map(item => item.exercise.id === exerciseId
      ? { ...item, sets: item.sets.map((set, index) => index === setIndex ? { ...set, ...patch } : set) }
      : item));
  }

  async function saveSession() {
    if (!token) return;
    const exerciseMinutes = drafts.map(item => Number(item.duration_min));
    if (drafts.length && exerciseMinutes.some(value => !Number.isInteger(value) || value < 1 || value > 600)) {
      setError("Indica entre 1 y 600 minutos para cada ejercicio. La duración total se calculará sumándolos.");
      return;
    }
    const minutes = drafts.length ? exerciseMinutes.reduce((sum, value) => sum + value, 0) : Number(duration);
    if (!Number.isInteger(minutes) || minutes < 1 || minutes > 600) {
      setError("La duración total debe estar entre 1 y 600 minutos.");
      return;
    }
    const parsedSets = drafts.flatMap(item => item.sets.map(set => ({
      exercise_id: item.exercise.id,
      reps: Number(set.reps),
      weight_kg: set.weight_kg.trim() ? Number(set.weight_kg.replace(",", ".")) : null,
      reached_failure: set.reached_failure === "" ? null : set.reached_failure === "true",
    })));
    if (parsedSets.some(set => !Number.isInteger(set.reps) || set.reps < 1 || set.reps > 200 ||
      (set.weight_kg !== null && (!Number.isFinite(set.weight_kg) || set.weight_kg < 0 || set.weight_kg > 1000)))) {
      setError("Revisa las repeticiones y los pesos de las series.");
      return;
    }
    const km = distance.trim() ? Number(distance.replace(",", ".")) : null;
    const stepCount = steps.trim() ? Number(steps) : null;
    const climb = elevation.trim() ? Number(elevation) : null;
    const bpm = heartRate.trim() ? Number(heartRate) : null;
    if ((category === "walking" || category === "running") && km !== null && (!Number.isFinite(km) || km <= 0 || km > 500)) {
      setError("La distancia debe estar entre 0 y 500 km.");
      return;
    }
    if (stepCount !== null && (!Number.isInteger(stepCount) || stepCount < 0 || stepCount > 200000)) {
      setError("Introduce un número de pasos válido.");
      return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/workouts", token, { method: "POST", body: {
        performed_on: date, kind: name.trim() || "Entrenamiento", category, duration_min: minutes,
        exercise_durations_min: drafts.length ? Object.fromEntries(drafts.map(item => [String(item.exercise.id), Number(item.duration_min)])) : {},
        distance_km: category === "walking" || category === "running" ? km : null,
        elevation_gain_m: category === "walking" || category === "running" ? climb : null,
        steps: category === "walking" || category === "running" ? stepCount : null,
        avg_hr_bpm: bpm, notes: notes.trim() || null, sets: parsedSets, estimate_calories: true,
      } });
      setDrafts([]); setNotes(""); setDistance(""); setSteps(""); setElevation(""); setHeartRate("");
      setNotice("Sesión guardada. SmartFit intentará estimar las calorías automáticamente.");
      await loadAll();
      setTab("history");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo guardar la sesión.");
    } finally {
      setBusy(false);
    }
  }

  function startEditDay(day: PlanDay) {
    setEditingDay(day);
    setDayLabel(day.label);
    setDayDraft(day.exercises.map(item => ({
      exercise_id: item.exercise_id, exercise: item.exercise, sets: String(item.sets),
      reps_min: String(item.reps_min), reps_max: String(item.reps_max),
      rest_s: item.rest_s == null ? "" : String(item.rest_s), notes: item.notes ?? "",
    })));
    setPlanQuery("");
    setPlanResults([]);
  }

  async function searchPlanExercises() {
    if (!token || !planQuery.trim()) return;
    try {
      setPlanResults(await api<Exercise[]>("/exercises?kind=strength&q=" + encodeURIComponent(planQuery.trim()), token));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudieron buscar ejercicios para el plan.");
    }
  }

  function addPlanExercise(exercise: Exercise) {
    setDayDraft(current => current.some(item => item.exercise_id === exercise.id) ? current : [
      ...current,
      { exercise_id: exercise.id, exercise: exercise.name, sets: "3", reps_min: "8", reps_max: "12", rest_s: "90", notes: "" },
    ]);
    setPlanResults([]);
  }

  async function savePlanDay() {
    if (!token || !editingDay) return;
    const exercises = dayDraft.map(item => ({
      exercise_id: item.exercise_id, sets: Number(item.sets), reps_min: Number(item.reps_min),
      reps_max: Number(item.reps_max), rest_s: item.rest_s.trim() ? Number(item.rest_s) : null,
      notes: item.notes.trim() || null,
    }));
    if (!dayLabel.trim() || exercises.length === 0 || exercises.some(item =>
      !Number.isInteger(item.sets) || item.sets < 1 || item.sets > 8 ||
      !Number.isInteger(item.reps_min) || !Number.isInteger(item.reps_max) ||
      item.reps_min < 1 || item.reps_max > 50 || item.reps_min > item.reps_max ||
      (item.rest_s !== null && (!Number.isInteger(item.rest_s) || item.rest_s < 0 || item.rest_s > 600)))) {
      setError("Revisa el nombre del día, los ejercicios, las series, las repeticiones y los descansos.");
      return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      const updated = await api<PlanResponse>("/plan/days/" + editingDay.id, token, {
        method: "PUT", body: { label: dayLabel.trim(), exercises },
      });
      setPlan(updated);
      setEditingDay(null);
      setNotice("Día del plan actualizado.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo guardar el día del plan.");
    } finally { setBusy(false); }
  }

  async function createCustomExercise() {
    if (!token || !newExerciseName.trim()) {
      setError("Escribe el nombre del ejercicio.");
      return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      const exercise = await api<Exercise>("/exercises", token, { method: "POST", body: {
        name: newExerciseName.trim(), kind: newExerciseKind,
        primary_muscle: newExerciseMuscle, equipment: [newExerciseEquipment],
      } });
      setNewExerciseName("");
      await refreshCatalog();
      addExercise(exercise);
      setNotice("Ejercicio propio creado y añadido a la sesión.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo crear el ejercicio.");
    } finally { setBusy(false); }
  }

  async function generatePlan() {
    if (!token) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const updated = await api<PlanResponse>("/plan/generate", token, { method: "POST", body: { use_ai: true } });
      setPlan(updated);
      setNotice("Plan de entrenamiento regenerado.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo generar el plan.");
    } finally {
      setBusy(false);
    }
  }

  async function deleteWorkout(workout: Workout) {
    if (!token) return;
    Alert.alert("Eliminar sesión", "¿Quieres eliminar «" + workout.kind + "»? Esta acción no se puede deshacer.", [
      { text: "Cancelar", style: "cancel" },
      { text: "Eliminar", style: "destructive", onPress: () => {
        void (async () => {
          setBusy(true);
          try {
            await api("/workouts/" + workout.id, token, { method: "DELETE" });
            await loadAll();
          } catch (reason) {
            setError(reason instanceof Error ? reason.message : "No se pudo eliminar la sesión.");
          } finally { setBusy(false); }
        })();
      } },
    ]);
  }

  async function reestimate(workout: Workout) {
    if (!token) return;
    setBusy(true); setError("");
    try {
      await api("/workouts/" + workout.id + "/estimate-calories", token, { method: "POST", body: {} });
      await loadAll();
      setNotice("Calorías recalculadas.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudieron recalcular las calorías.");
    } finally { setBusy(false); }
  }

  const topMuscles = Object.entries(muscles?.muscles ?? {}).sort((a, b) => b[1].sets - a[1].sets).slice(0, 12);
  const isCardio = category === "walking" || category === "running";

  return <Screen>
    <PageTitle eyebrow="Entrenamiento" title="Entrena y registra tu evolución" subtitle="Plan personalizado, catálogo de ejercicios, sesiones e intensidad muscular." />
    <ChoiceRow value={tab} onChange={setTab} options={[
      { value: "session", label: "Sesión" }, { value: "plan", label: "Mi plan" },
      { value: "history", label: "Historial" }, { value: "muscles", label: "Músculos" }, { value: "gps", label: "GPS" },
    ]} />
    <ErrorMessage message={error} />
    {notice ? <Text style={{ color: colors.accent, fontSize: 13 }}>{notice}</Text> : null}
    {loading ? <ActivityIndicator color={colors.accent} /> : null}

    {tab === "session" ? <>
      <Panel>
        <SectionTitle title="Datos de la sesión" />
        <Field label="Nombre" value={name} onChangeText={setName} placeholder="Entrenamiento" />
        <Field label="Fecha (AAAA-MM-DD)" value={date} onChangeText={setDate} placeholder={localDateISO()} />
        <Text style={{ color: colors.text, fontWeight: "700" }}>Tipo de actividad</Text>
        <ChoiceRow value={category} onChange={setCategory} options={categories} />
        {drafts.length === 0 ? <Field label="Duración total (minutos)" value={duration} onChangeText={setDuration} keyboardType="number-pad" /> : <Muted>La duración total se calculará sumando los minutos de cada ejercicio.</Muted>}
        {isCardio ? <>
          <Field label="Distancia (km)" value={distance} onChangeText={setDistance} keyboardType="decimal-pad" placeholder="Ej. 5,2" />
          <Field label="Desnivel positivo (m)" value={elevation} onChangeText={setElevation} keyboardType="number-pad" />
          <Field label="Pasos" value={steps} onChangeText={setSteps} keyboardType="number-pad" />
        </> : null}
        <Field label="Frecuencia cardiaca media (ppm)" value={heartRate} onChangeText={setHeartRate} keyboardType="number-pad" placeholder="Opcional" />
        <Field label="Notas" value={notes} onChangeText={setNotes} multiline numberOfLines={3} maxLength={1000} placeholder="Sensaciones, intensidad o comentarios…" />
        {isCardio ? <Muted>En esta versión puedes introducir manualmente las métricas de la actividad. El seguimiento GPS en directo de la web aún requiere adaptación nativa.</Muted> : null}
      </Panel>
      <SectionTitle title="Añadir ejercicios" action={drafts.length + " ejercicios"} />
      <Panel>
        <Field label="Buscar en el catálogo" value={query} onChangeText={setQuery} placeholder="Press banca, sentadilla…" returnKeyType="search" onSubmitEditing={() => void refreshCatalog()} />
        <Text style={{ color: colors.text, fontWeight: "700" }}>Tipo de ejercicio</Text>
        <ChoiceRow value={kindFilter} onChange={setKindFilter} options={kindFilterOptions} />
        <Text style={{ color: colors.text, fontWeight: "700" }}>Grupo muscular</Text>
        <ChoiceRow value={muscleFilter} onChange={setMuscleFilter} options={muscleFilterOptions} />
        <Text style={{ color: colors.text, fontWeight: "700" }}>Equipamiento</Text>
        <ChoiceRow value={equipmentFilter} onChange={setEquipmentFilter} options={equipmentFilterOptions} />
        <Text style={{ color: colors.text, fontWeight: "700" }}>Coincidir con músculos secundarios</Text>
        <ChoiceRow value={includeSecondary} onChange={setIncludeSecondary} options={[{ value: "true", label: "Sí" }, { value: "false", label: "Solo principal" }]} />
        <AppButton title="Aplicar filtros" onPress={() => void refreshCatalog()} variant="secondary" />
        {catalog.slice(0, 30).map(exercise => <View key={exercise.id} style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 9 }}>
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={{ color: colors.text, fontWeight: "800" }}>{exercise.name}</Text>
            <Muted>{exercise.primary_muscle.replaceAll("_", " ")} · {exercise.equipment.join(", ")}</Muted>
          </View>
          <View style={{ gap: 6 }}>
            <AppButton title="＋ Añadir" onPress={() => addExercise(exercise)} variant="quiet" />
            <AppButton title="Ver ficha + animación 3D" onPress={() => void showExercise(exercise)} variant="quiet" />
          </View>
        </View>)}
        {catalog.length === 0 ? <Muted>No hay resultados. Prueba otra búsqueda.</Muted> : null}
      </Panel>
      <Panel>
        <SectionTitle title="Crear ejercicio propio" />
        <Field label="Nombre del ejercicio" value={newExerciseName} onChangeText={setNewExerciseName} placeholder="Ej. Press inclinado con mancuernas" />
        <Text style={{ color: colors.text, fontWeight: "700" }}>Tipo</Text>
        <ChoiceRow value={newExerciseKind} onChange={setNewExerciseKind} options={[
          { value: "strength", label: "Fuerza" }, { value: "full_body", label: "Cuerpo entero" }, { value: "stretching", label: "Estiramiento" },
        ]} />
        <Text style={{ color: colors.text, fontWeight: "700" }}>Músculo principal</Text>
        <ChoiceRow value={newExerciseMuscle} onChange={setNewExerciseMuscle} options={muscleOptions.map(value => ({ value, label: value.replaceAll("_", " ") }))} />
        <Text style={{ color: colors.text, fontWeight: "700" }}>Equipamiento</Text>
        <ChoiceRow value={newExerciseEquipment} onChange={setNewExerciseEquipment} options={equipmentOptions.map(value => ({ value, label: value.replaceAll("_", " ") }))} />
        <AppButton title="Crear ejercicio" onPress={() => void createCustomExercise()} loading={busy} disabled={!newExerciseName.trim()} variant="secondary" />
        <Muted>El ejercicio se guarda en tu catálogo privado.</Muted>
      </Panel>
      {selectedExercise ? <Panel>
        <SectionTitle title={selectedExercise.name} />
        <SectionTitle title="Animación interactiva 3D" />
        <ExerciseAnimation exerciseName={selectedExercise.name} />
        <Muted>Una repetición en bucle. Arrastra para girar el modelo; puedes pausar o activar el giro 360° desde los controles de la animación.</Muted>
        {exerciseContent?.description ? <Muted>{exerciseContent.description}</Muted> : <Muted>Ficha de ejercicio</Muted>}
        {exerciseContent?.start_position ? <Text style={{ color: colors.text, fontWeight: "700" }}>Posición inicial: {exerciseContent.start_position}</Text> : null}
        {exerciseContent?.instructions?.map((instruction, index) => <Muted key={index}>{index + 1}. {instruction}</Muted>)}
        {exerciseContent?.common_mistakes?.length ? <Muted>Errores frecuentes: {exerciseContent.common_mistakes.join(" · ")}</Muted> : null}
        {exerciseContent?.image_url ? <Text onPress={() => void Linking.openURL(exerciseContent.image_url!)} style={{ color: colors.accent, fontWeight: "800", paddingVertical: 5 }}>Abrir imagen demostrativa ↗</Text> : null}
        {exerciseContent?.video_url ? <Text onPress={() => void Linking.openURL(exerciseContent.video_url!)} style={{ color: colors.accent, fontWeight: "800", paddingVertical: 5 }}>Ver vídeo demostrativo ↗</Text> : null}
        {exerciseContent?.media_credit ? <Muted>Crédito: {exerciseContent.media_credit}</Muted> : null}
        <SectionTitle title="Evolución de cargas" action={exerciseProgress.length + " sesiones"} />
        {exerciseProgress.length ? exerciseProgress.slice().reverse().map((item, index) => <View key={item.date + index} style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 8 }}>
          <Text style={{ color: colors.text, fontWeight: "800" }}>{dateLabel(item.date)}</Text>
          <Muted>Mejor peso {fmt(item.best_weight_kg, 1)} kg · 1RM estimado {fmt(item.est_1rm_kg, 1)} kg</Muted>
          <Muted>{item.sets} series · volumen {fmt(item.volume_kg)} kg</Muted>
        </View>) : <Muted>Aún no hay suficientes sesiones para calcular la evolución.</Muted>}
        <SectionTitle title="Últimas sesiones del ejercicio" action={exerciseHistory.length + " registros"} />
        {exerciseHistory.map(item => <View key={item.workout_id} style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 8 }}>
          <Text style={{ color: colors.text, fontWeight: "800" }}>{dateLabel(item.date)}</Text>
          <Muted>{item.sets.map(set => "S" + set.set_number + ": " + set.reps + " reps" +
            (set.weight_kg == null ? "" : " × " + fmt(set.weight_kg, 1) + " kg") +
            (set.reached_failure ? " · fallo" : "")).join("  |  ")}</Muted>
        </View>)}
        <Text onPress={() => setSelectedExercise(null)} style={{ color: colors.accent, fontWeight: "800" }}>Cerrar ficha</Text>
      </Panel> : null}
      {drafts.map(item => <Panel key={item.exercise.id}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <Text style={{ color: colors.text, fontWeight: "900", flex: 1 }}>{item.exercise.name}</Text>
          <Text onPress={() => setDrafts(current => current.filter(x => x.exercise.id !== item.exercise.id))} style={{ color: colors.danger, fontWeight: "700", padding: 6 }}>Quitar</Text>
        </View>
        <Field label="Tiempo dedicado a este ejercicio (minutos)" value={item.duration_min} onChangeText={value => setDrafts(current => current.map(entry => entry.exercise.id === item.exercise.id ? { ...entry, duration_min: value } : entry))} keyboardType="number-pad" placeholder="Ej. 12" />
        {item.sets.map((set, index) => <View key={index} style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 9, gap: 8 }}>
          <Text style={{ color: colors.accent, fontWeight: "800" }}>Serie {index + 1}</Text>
          <View style={{ flexDirection: "row", gap: 8 }}>
            <View style={{ flex: 1 }}><Field label="Repeticiones" value={set.reps} onChangeText={value => updateSet(item.exercise.id, index, { reps: value })} keyboardType="number-pad" /></View>
            <View style={{ flex: 1 }}><Field label="Peso (kg)" value={set.weight_kg} onChangeText={value => updateSet(item.exercise.id, index, { weight_kg: value })} keyboardType="decimal-pad" placeholder="Opcional" /></View>
          </View>
          <Text style={{ color: colors.text, fontWeight: "700" }}>¿Llegaste al fallo?</Text>
          <ChoiceRow value={set.reached_failure} onChange={value => updateSet(item.exercise.id, index, { reached_failure: value })} options={[
            { value: "", label: "Sin indicar" }, { value: "true", label: "Sí" }, { value: "false", label: "No" },
          ]} />
          {item.sets.length > 1 ? <Text onPress={() => setDrafts(current => current.map(entry => entry.exercise.id === item.exercise.id ? { ...entry, sets: entry.sets.filter((_, n) => n !== index) } : entry))} style={{ color: colors.danger, fontSize: 12 }}>Eliminar serie</Text> : null}
        </View>)}
        <AppButton title="+ Añadir serie" onPress={() => setDrafts(current => current.map(entry => entry.exercise.id === item.exercise.id ? { ...entry, sets: [...entry.sets, emptySet()] } : entry))} variant="quiet" />
      </Panel>)}
      <AppButton title="Guardar sesión" onPress={() => void saveSession()} loading={busy} />
    </> : null}

    {tab === "plan" ? <>
      <Panel style={{ backgroundColor: colors.accentDark, borderColor: colors.accent }}>
        <Text style={{ color: colors.accent, fontWeight: "900", fontSize: 11 }}>PLAN PERSONALIZADO</Text>
        <Text style={{ color: colors.text, fontSize: 21, fontWeight: "900" }}>{plan?.plan?.name ?? (plan?.has_plan ? "Tu plan actual" : "Todavía no tienes un plan")}</Text>
        <Muted>{plan?.plan?.source === "ai" ? "Propuesto con IA y adaptado a tu perfil." : "Puedes generar un plan ajustado a tus objetivos y experiencia."}</Muted>
        <AppButton title={plan?.has_plan ? "Regenerar plan con IA" : "Generar mi plan"} onPress={() => void generatePlan()} loading={busy} />
      </Panel>
      {plan?.plan?.days?.length ? plan.plan.days.map(day => <Panel key={day.id}>
        <Text style={{ color: colors.text, fontSize: 17, fontWeight: "900" }}>{day.label}</Text>
        <Muted>{day.muscle_focus.join(" · ").replaceAll("_", " ")}</Muted>
        {day.exercises.map(exercise => <View key={exercise.id} style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 8 }}>
          <Text style={{ color: colors.text, fontWeight: "800" }}>{exercise.exercise}</Text>
          <Muted>{exercise.sets} series · {exercise.reps_min}–{exercise.reps_max} repeticiones · descanso {exercise.rest_s ?? "—"} s</Muted>
          {exercise.notes ? <Muted>{exercise.notes}</Muted> : null}
        </View>)}
        <AppButton title="Editar este día" onPress={() => startEditDay(day)} variant="secondary" />
      </Panel>) : plan?.legacy_markdown ? <Panel><Muted>{plan.legacy_markdown}</Muted></Panel> :
        <Muted>Aún no hay un plan guardado. Genera uno para empezar.</Muted>}
      {editingDay ? <Panel>
        <SectionTitle title={"Editar " + editingDay.label} />
        <Field label="Nombre del día" value={dayLabel} onChangeText={setDayLabel} />
        {dayDraft.map((item, index) => <View key={item.exercise_id} style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 10, gap: 7 }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <Text style={{ color: colors.text, fontWeight: "800", flex: 1 }}>{item.exercise}</Text>
            <Text onPress={() => setDayDraft(current => current.filter(x => x.exercise_id !== item.exercise_id))} style={{ color: colors.danger, padding: 5 }}>Quitar</Text>
          </View>
          <View style={{ flexDirection: "row", gap: 8 }}>
            <View style={{ flex: 1 }}><Field label="Series" value={item.sets} onChangeText={value => setDayDraft(current => current.map((x, i) => i === index ? { ...x, sets: value } : x))} keyboardType="number-pad" /></View>
            <View style={{ flex: 1 }}><Field label="Reps mín." value={item.reps_min} onChangeText={value => setDayDraft(current => current.map((x, i) => i === index ? { ...x, reps_min: value } : x))} keyboardType="number-pad" /></View>
            <View style={{ flex: 1 }}><Field label="Reps máx." value={item.reps_max} onChangeText={value => setDayDraft(current => current.map((x, i) => i === index ? { ...x, reps_max: value } : x))} keyboardType="number-pad" /></View>
          </View>
          <Field label="Descanso (segundos)" value={item.rest_s} onChangeText={value => setDayDraft(current => current.map((x, i) => i === index ? { ...x, rest_s: value } : x))} keyboardType="number-pad" />
          <Field label="Notas" value={item.notes} onChangeText={value => setDayDraft(current => current.map((x, i) => i === index ? { ...x, notes: value } : x))} />
        </View>)}
        <Field label="Buscar ejercicio para añadir" value={planQuery} onChangeText={setPlanQuery} returnKeyType="search" onSubmitEditing={() => void searchPlanExercises()} />
        <AppButton title="Buscar ejercicios" onPress={() => void searchPlanExercises()} variant="quiet" disabled={!planQuery.trim()} />
        {planResults.map(exercise => <Text key={exercise.id} onPress={() => addPlanExercise(exercise)} style={{ color: colors.accent, fontWeight: "800", paddingVertical: 7 }}>＋ {exercise.name}</Text>)}
        <AppButton title="Guardar día" onPress={() => void savePlanDay()} loading={busy} disabled={!dayDraft.length} />
        <AppButton title="Cancelar" onPress={() => setEditingDay(null)} variant="quiet" />
      </Panel> : null}
    </> : null}

    {tab === "history" ? <>
      <SectionTitle title="Historial de entrenamientos" action={workouts.length + " sesiones"} />
      {workouts.length === 0 ? <Panel><Muted>Aún no hay sesiones registradas.</Muted></Panel> :
        workouts.map(workout => <Panel key={workout.id}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <View style={{ flex: 1, gap: 3 }}>
              <Text style={{ color: colors.text, fontSize: 16, fontWeight: "900" }}>{workout.kind}</Text>
              <Muted>{dateLabel(workout.performed_on)} · {workout.category ?? "Entrenamiento"} · {workout.duration_min} min</Muted>
            </View>
            <Text style={{ color: colors.accent, fontWeight: "900" }}>{fmt(workout.kcal_burned)} kcal</Text>
          </View>
          {workout.distance_km != null ? <Muted>{fmt(workout.distance_km, 2)} km · {fmt(workout.steps)} pasos · desnivel {fmt(workout.elevation_gain_m)} m</Muted> : null}
          {workout.exercises.map(exercise => <View key={exercise.exercise_id} style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 8 }}>
            <Text style={{ color: colors.text, fontWeight: "800" }}>{exercise.exercise}</Text>
            <Muted>{exercise.duration_min != null ? "Tiempo: " + exercise.duration_min + " min · " : ""}{exercise.sets.map(set => set.reps + " reps" + (set.weight_kg == null ? "" : " × " + fmt(set.weight_kg, 1) + " kg") + (set.reached_failure ? " · fallo" : "")).join("  |  ")}</Muted>
          </View>)}
          {workout.feedback?.map((item, index) => <Muted key={index}>{item.exercise}: {item.message}</Muted>)}
          {workout.kcal_note ? <Muted>{workout.kcal_note}</Muted> : null}
          <View style={{ flexDirection: "row", gap: 8 }}>
            <View style={{ flex: 1 }}><AppButton title="Reestimar kcal" onPress={() => void reestimate(workout)} loading={busy} variant="quiet" /></View>
            <View style={{ flex: 1 }}><AppButton title="Eliminar" onPress={() => deleteWorkout(workout)} variant="quiet" /></View>
          </View>
        </Panel>)}
    </> : null}

    {token ? <CardioGpsTracker token={token} visible={tab === "gps"} onSaved={() => { void loadAll(); setTab("history"); }} /> : null}

    {tab === "muscles" ? <>
      <SectionTitle title="Carga muscular" action={muscles?.sessions + " sesiones"} />
      <ChoiceRow value={period} onChange={refreshMuscles} options={[
        { value: "7", label: "7 días" }, { value: "14", label: "14 días" }, { value: "30", label: "30 días" },
        { value: "90", label: "90 días" }, { value: "180", label: "180 días" },
      ]} />
      <Muted>{muscles?.start ?? "—"} a {muscles?.end ?? "—"} · Las series ponderadas priorizan los músculos principales.</Muted>
      {topMuscles.length === 0 ? <Panel><Muted>Registra sesiones para ver la distribución por grupos musculares.</Muted></Panel> :
        topMuscles.map(([key, value]) => <Panel key={key}>
          <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
            <Text style={{ color: colors.text, fontWeight: "800", textTransform: "capitalize" }}>{key.replaceAll("_", " ")}</Text>
            <Text style={{ color: colors.accent, fontWeight: "900" }}>{fmt(value.sets, 1)} series</Text>
          </View>
          <View style={{ height: 7, borderRadius: 8, backgroundColor: colors.surfaceRaised, overflow: "hidden" }}>
            <View style={{ height: 7, width: (Math.min(100, value.sets / Math.max(1, topMuscles[0][1].sets) * 100)) + "%", backgroundColor: colors.accent }} />
          </View>
          <Muted>Fuerza {fmt(value.strength_sets, 1)} · Cardio {fmt(value.cardio_sets, 1)} · Volumen {fmt(value.volume_kg)} kg</Muted>
        </Panel>)}
    </> : null}
  </Screen>;
}
