import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Text, View } from "react-native";
import { api, type WeightEntry } from "@/lib/api";
import { dateLabel, formatKcal } from "@/lib/format";
import { localDateISO } from "@/lib/format";
import { useAuth } from "@/auth/AuthProvider";
import { AppButton, ChoiceRow, ErrorMessage, Field, Muted, PageTitle, Panel, ProgressBar, Screen, SectionTitle } from "@/components/ui";
import { colors } from "@/theme";

type Day = { log_date: string; kcal: number; protein_g: number; carbs_g: number; fat_g: number; fiber_g: number };
type Targets = { kcal: number; protein_g: number; carbs_g: number; fat_g: number; fiber_g: number; workouts_per_week: number; water_ml?: number; steps_goal?: number };
type Workout = { id: number; performed_on: string; kind: string; category?: string | null; duration_min: number; kcal_burned?: number | null; distance_km?: number | null };
type Summary = { goal: number; today_steps: number | null; today_pct: number | null; avg_steps: number | null; days_recorded: number; days_goal_met: number };
type WaterSummary = { goal_ml: number; today_ml: number; avg_ml: number | null; days_goal_met: number };
type Checkin = { date: string; mood: number };
type Insights = {
  enough_data: boolean; summary: string; ai_summary?: string | null; achievements: string[]; pending: string[];
  note?: string | null; training?: { personal_records?: Array<{ exercise: string; weight_kg: number; previous_best_kg: number }> };
};
type Range = { targets: Targets; days: Day[] };
const fmt = (value: number | null | undefined, digits = 0) => value == null ? "—" : value.toLocaleString("es-ES", { maximumFractionDigits: digits });

export default function ProgressScreen() {
  const { token } = useAuth();
  const [period, setPeriod] = useState("30");
  const [ai, setAi] = useState("false");
  const [range, setRange] = useState<Range | null>(null);
  const [weights, setWeights] = useState<WeightEntry[]>([]);
  const [workouts, setWorkouts] = useState<Workout[]>([]);
  const [water, setWater] = useState<WaterSummary | null>(null);
  const [activity, setActivity] = useState<Summary | null>(null);
  const [checkins, setCheckins] = useState<Checkin[]>([]);
  const [insights, setInsights] = useState<Insights | null>(null);
  const [weight, setWeight] = useState("");
  const [bodyFat, setBodyFat] = useState("");
  const [weightDate, setWeightDate] = useState(localDateISO());
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true); setError("");
    const days = Number(period);
    try {
      const [r, w, ws, wa, ac, ci, ins] = await Promise.all([
        api<Range>("/dashboard/range?days=" + days, token),
        api<WeightEntry[]>("/metrics/weight?days=365", token),
        api<Workout[]>("/workouts?days=" + days, token),
        api<WaterSummary>("/water/summary?days=" + days, token),
        api<Summary>("/activity/summary?days=" + days, token),
        api<Checkin[]>("/checkins?days=" + days, token),
        api<Insights>("/progress/insights?days=" + days + "&ai=" + ai, token),
      ]);
      setRange(r); setWeights(w); setWorkouts(ws); setWater(wa); setActivity(ac); setCheckins(ci); setInsights(ins);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo cargar el análisis del progreso.");
    } finally { setLoading(false); }
  }, [token, period, ai]);

  useEffect(() => { void load(); }, [load]);

  async function saveWeight() {
    if (!token) return;
    const value = Number(weight.replace(",", "."));
    const fat = bodyFat.trim() ? Number(bodyFat.replace(",", ".")) : null;
    if (!Number.isFinite(value) || value <= 20 || value >= 400) {
      setError("Introduce un peso válido en kg.");
      return;
    }
    if (fat !== null && (!Number.isFinite(fat) || fat < 1 || fat > 70)) {
      setError("El porcentaje graso debe estar entre 1 y 70.");
      return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/metrics/weight", token, { method: "POST", body: {
        weight_kg: value, body_fat_pct: fat, measured_on: weightDate,
      } });
      setWeight(""); setBodyFat("");
      await load();
      setNotice("Medición guardada.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo guardar la medición.");
    } finally { setBusy(false); }
  }

  const days = range?.days ?? [];
  const targets = range?.targets;
  const average = (key: "kcal" | "protein_g" | "carbs_g" | "fat_g") =>
    days.length ? days.reduce((sum, item) => sum + item[key], 0) / days.length : null;
  const maxKcal = Math.max(targets?.kcal ?? 0, ...days.map(item => item.kcal), 1);
  const totalMinutes = workouts.reduce((sum, item) => sum + item.duration_min, 0);
  const totalDistance = workouts.reduce((sum, item) => sum + (item.distance_km ?? 0), 0);
  const totalCalories = workouts.reduce((sum, item) => sum + (item.kcal_burned ?? 0), 0);
  const latest = weights.length ? weights[weights.length - 1] : null;

  return <Screen>
    <PageTitle eyebrow="Progreso" title="Tu evolución, con perspectiva" subtitle="Nutrición, entrenamiento, peso y hábitos en un solo lugar." />
    <SectionTitle title="Periodo de análisis" />
    <ChoiceRow value={period} onChange={setPeriod} options={[
      { value: "7", label: "7 días" }, { value: "14", label: "14 días" },
      { value: "30", label: "30 días" }, { value: "90", label: "90 días" },
    ]} />
    {loading ? <ActivityIndicator color={colors.accent} /> : null}
    <ErrorMessage message={error} />
    {notice ? <Text style={{ color: colors.accent, fontSize: 13 }}>{notice}</Text> : null}
    <View style={{ flexDirection: "row", gap: 10 }}>
      <Panel style={{ flex: 1 }}>
        <Muted>Media de calorías</Muted>
        <Text style={{ color: colors.text, fontSize: 22, fontWeight: "900" }}>{fmt(average("kcal"))}</Text>
        <Muted>Objetivo {fmt(targets?.kcal)} kcal</Muted>
      </Panel>
      <Panel style={{ flex: 1 }}>
        <Muted>Proteína media</Muted>
        <Text style={{ color: colors.text, fontSize: 22, fontWeight: "900" }}>{fmt(average("protein_g"), 1)} g</Text>
        <Muted>Objetivo {fmt(targets?.protein_g)} g</Muted>
      </Panel>
    </View>
    <View style={{ flexDirection: "row", gap: 10 }}>
      <Panel style={{ flex: 1 }}>
        <Muted>Entrenamientos</Muted>
        <Text style={{ color: colors.text, fontSize: 22, fontWeight: "900" }}>{workouts.length}</Text>
        <Muted>Objetivo semanal {targets?.workouts_per_week ?? "—"}</Muted>
      </Panel>
      <Panel style={{ flex: 1 }}>
        <Muted>Peso actual</Muted>
        <Text style={{ color: colors.text, fontSize: 22, fontWeight: "900" }}>{latest ? fmt(latest.weight_kg, 1) + " kg" : "—"}</Text>
        <Muted>{latest ? latest.measured_on : "Sin mediciones"}</Muted>
      </Panel>
    </View>
    <Panel>
      <SectionTitle title="Calorías registradas" action={days.length + " días"} />
      <Muted>Solo aparecen días con registros. Un día vacío no equivale a cero calorías.</Muted>
      {days.slice(-14).map(item => <View key={item.log_date} style={{ gap: 4 }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
          <Muted>{item.log_date}</Muted><Text style={{ color: colors.text, fontWeight: "800" }}>{formatKcal(item.kcal)} kcal</Text>
        </View>
        <ProgressBar value={item.kcal / maxKcal * 100} />
      </View>)}
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 12 }}>
        <Muted>Carbohidratos: {fmt(average("carbs_g"), 1)} g</Muted>
        <Muted>Grasas: {fmt(average("fat_g"), 1)} g</Muted>
      </View>
    </Panel>
    <SectionTitle title="Composición corporal" />
    <Panel>
      <Field label="Fecha (AAAA-MM-DD)" value={weightDate} onChangeText={setWeightDate} placeholder={localDateISO()} />
      <Field label="Peso (kg)" value={weight} onChangeText={setWeight} keyboardType="decimal-pad" placeholder="Ej. 74,5" />
      <Field label="Grasa corporal (%)" value={bodyFat} onChangeText={setBodyFat} keyboardType="decimal-pad" placeholder="Opcional" />
      <AppButton title="Guardar medición" onPress={() => void saveWeight()} loading={busy} disabled={!weight.trim()} />
      <SectionTitle title="Historial de peso" action="Últimos registros" />
      {weights.slice().reverse().slice(0, 12).map(item => <View key={item.id} style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: 7, borderTopWidth: 1, borderTopColor: colors.border }}>
        <Muted>{dateLabel(item.measured_on)}</Muted>
        <View style={{ alignItems: "flex-end" }}>
          <Text style={{ color: colors.text, fontWeight: "800" }}>{fmt(item.weight_kg, 1)} kg</Text>
          <Muted>{item.body_fat_pct == null ? "Sin % graso" : fmt(item.body_fat_pct, 1) + "% grasa"}</Muted>
        </View>
      </View>)}
    </Panel>
    <Panel>
      <SectionTitle title="Entrenamiento en el periodo" />
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}><Muted>Tiempo total</Muted><Text style={{ color: colors.text, fontWeight: "800" }}>{fmt(totalMinutes / 60, 1)} h</Text></View>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}><Muted>Distancia</Muted><Text style={{ color: colors.text, fontWeight: "800" }}>{fmt(totalDistance, 1)} km</Text></View>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}><Muted>Calorías estimadas</Muted><Text style={{ color: colors.text, fontWeight: "800" }}>{fmt(totalCalories)} kcal</Text></View>
      {workouts.slice(0, 8).map(item => <View key={item.id} style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 8 }}>
        <Text style={{ color: colors.text, fontWeight: "800" }}>{item.kind}</Text>
        <Muted>{dateLabel(item.performed_on)} · {item.duration_min} min{item.distance_km ? " · " + fmt(item.distance_km, 1) + " km" : ""}</Muted>
      </View>)}
    </Panel>
    <Panel>
      <SectionTitle title="Análisis del progreso" />
      <Muted>Comparación con el periodo anterior equivalente.</Muted>
      <Text style={{ color: colors.text, fontWeight: "700" }}>Resumen con IA</Text>
      <ChoiceRow value={ai} onChange={setAi} options={[{ value: "false", label: "Cálculo SmartFit" }, { value: "true", label: "Redacción IA" }]} />
      <Text style={{ color: colors.text, fontSize: 14, lineHeight: 22 }}>{insights?.ai_summary || insights?.summary || "Cargando análisis…"}</Text>
      {insights?.enough_data === false ? <Muted>Aún no hay datos suficientes para conclusiones fiables.</Muted> : null}
      <SectionTitle title="Logros" />
      {insights?.achievements?.length ? insights.achievements.map((item, index) => <Text key={index} style={{ color: colors.accent }}>✓ {item}</Text>) : <Muted>Todavía no hay logros calculados.</Muted>}
      <SectionTitle title="Aspectos a mejorar" />
      {insights?.pending?.length ? insights.pending.map((item, index) => <Muted key={index}>• {item}</Muted>) : <Muted>Sin pendientes calculados.</Muted>}
      {insights?.training?.personal_records?.map((item, index) => <Muted key={index}>Récord · {item.exercise}: {fmt(item.weight_kg, 1)} kg (anterior {fmt(item.previous_best_kg, 1)} kg)</Muted>)}
      {insights?.note ? <Muted>{insights.note}</Muted> : null}
    </Panel>
    <View style={{ flexDirection: "row", gap: 10 }}>
      <Panel style={{ flex: 1 }}>
        <Muted>Hidratación media</Muted>
        <Text style={{ color: colors.text, fontSize: 20, fontWeight: "900" }}>{fmt(water?.avg_ml)} ml</Text>
        <Muted>Objetivo {fmt(water?.goal_ml)} · logrado {water?.days_goal_met ?? 0} días</Muted>
      </Panel>
      <Panel style={{ flex: 1 }}>
        <Muted>Actividad media</Muted>
        <Text style={{ color: colors.text, fontSize: 20, fontWeight: "900" }}>{fmt(activity?.avg_steps)} pasos</Text>
        <Muted>Objetivo {fmt(activity?.goal)}</Muted>
      </Panel>
    </View>
    <Panel>
      <SectionTitle title="Bienestar" />
      <Text style={{ color: colors.text, fontSize: 22, fontWeight: "900" }}>{checkins.length} check-ins</Text>
      <Muted>Ánimo medio: {checkins.length ? (checkins.reduce((sum, item) => sum + item.mood, 0) / checkins.length).toFixed(1) + "/5" : "—"}. Las notas privadas no se incluyen en los análisis.</Muted>
    </Panel>
  </Screen>;
}
