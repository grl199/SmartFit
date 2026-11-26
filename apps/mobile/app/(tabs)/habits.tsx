import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Alert, Text, View } from "react-native";
import { api } from "@/lib/api";
import { localDateISO } from "@/lib/format";
import { useAuth } from "@/auth/AuthProvider";
import { AppButton, ChoiceRow, ErrorMessage, Field, Muted, PageTitle, Panel, ProgressBar, Screen, SectionTitle } from "@/components/ui";
import { colors } from "@/theme";

type Targets = {
  kcal: number; protein_g: number; carbs_g: number; fat_g: number; fiber_g: number;
  workouts_per_week: number; water_ml?: number | null; steps_goal?: number | null;
};
type WaterLog = { id: number; logged_at: string; quantity_ml: number; source: string };
type WaterSummary = {
  goal_ml: number; today_ml: number; today_pct: number; avg_ml: number | null;
  days_logged: number; days_goal_met: number; days: Array<{ date: string; ml: number; pct: number }>;
};
type ActivitySummary = {
  goal: number; today_steps: number | null; today_pct: number | null; avg_steps: number | null;
  days_recorded: number; days_goal_met: number; days: Array<{ date: string; steps: number | null }>;
};
type Checkin = {
  date: string; mood: number; energy_level?: number | null; stress_level?: number | null;
  sleep_quality?: number | null; notes?: string | null;
};
type Connection = {
  provider: string; label: string; mode: "pull" | "push"; configured: boolean;
  note: string; connected: boolean;
};
const fmt = (value: number | null | undefined) => value == null ? "—" : Math.round(value).toLocaleString("es-ES");
const scoreOptions = ["1", "2", "3", "4", "5"].map(value => ({ value, label: value }));

export default function HabitsScreen() {
  const { token } = useAuth();
  const [date, setDate] = useState(localDateISO());
  const [targets, setTargets] = useState<Targets | null>(null);
  const [water, setWater] = useState<WaterSummary | null>(null);
  const [activity, setActivity] = useState<ActivitySummary | null>(null);
  const [waterLogs, setWaterLogs] = useState<WaterLog[]>([]);
  const [checkins, setCheckins] = useState<Checkin[]>([]);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [waterAmount, setWaterAmount] = useState("250");
  const [waterGoal, setWaterGoal] = useState("2000");
  const [stepsGoal, setStepsGoal] = useState("8000");
  const [steps, setSteps] = useState("");
  const [distance, setDistance] = useState("");
  const [mood, setMood] = useState("3");
  const [energy, setEnergy] = useState("3");
  const [stress, setStress] = useState("3");
  const [sleep, setSleep] = useState("3");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setError("");
      const [t, w, a, logs, c, co] = await Promise.all([
        api<Targets>("/targets", token),
        api<WaterSummary>("/water/summary?days=14", token),
        api<ActivitySummary>("/activity/summary?days=14", token),
        api<WaterLog[]>("/water?date=" + encodeURIComponent(date), token),
        api<Checkin[]>("/checkins?days=120", token),
        api<Connection[]>("/activity/connections", token),
      ]);
      setTargets(t);
      setWater(w);
      setActivity(a);
      setWaterLogs(logs);
      setCheckins(c);
      setConnections(co);
      setWaterGoal(String(t.water_ml ?? w.goal_ml ?? 2000));
      setStepsGoal(String(t.steps_goal ?? a.goal ?? 8000));
      const current = c.find(item => item.date === date);
      setMood(String(current?.mood ?? 3));
      setEnergy(String(current?.energy_level ?? 3));
      setStress(String(current?.stress_level ?? 3));
      setSleep(String(current?.sleep_quality ?? 3));
      setNotes(current?.notes ?? "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudieron cargar tus hábitos.");
    } finally {
      setLoading(false);
    }
  }, [token, date]);

  useEffect(() => { void load(); }, [load]);

  async function runAction(action: () => Promise<void>, success: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      await load();
      setNotice(success);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo completar la operación.");
    } finally {
      setBusy(false);
    }
  }

  function addWater() {
    const amount = Number(waterAmount);
    if (!Number.isInteger(amount) || amount < 1 || amount > 5000) {
      setError("Introduce una cantidad de agua válida (1–5000 ml).");
      return;
    }
    void runAction(async () => {
      await api("/water", token!, { method: "POST", body: { quantity_ml: amount, log_date: date, source: "manual" } });
    }, "Agua registrada.");
  }

  function deleteWater(item: WaterLog) {
    Alert.alert("Eliminar registro", "¿Quieres eliminar esta toma de agua?", [
      { text: "Cancelar", style: "cancel" },
      { text: "Eliminar", style: "destructive", onPress: () => void runAction(async () => {
        await api("/water/" + item.id, token!, { method: "DELETE" });
      }, "Registro eliminado.") },
    ]);
  }

  function saveActivity() {
    const count = Number(steps);
    const km = distance.trim() ? Number(distance.replace(",", ".")) : null;
    if (!Number.isInteger(count) || count < 0 || count > 200000 || (km !== null && (!Number.isFinite(km) || km < 0 || km > 500))) {
      setError("Revisa los pasos y la distancia introducidos.");
      return;
    }
    void runAction(async () => {
      await api("/activity", token!, { method: "PUT", body: { activity_date: date, steps: count, distance_km: km } });
      setSteps("");
      setDistance("");
    }, "Actividad registrada.");
  }

  function saveCheckin() {
    void runAction(async () => {
      await api("/checkins/" + date, token!, { method: "PUT", body: {
        mood: Number(mood), energy_level: Number(energy), stress_level: Number(stress),
        sleep_quality: Number(sleep), notes: notes.trim() || null,
      } });
    }, "Check-in guardado. Tus notas son privadas y no se envían al asistente.");
  }

  function saveGoals() {
    if (!targets) return;
    const waterValue = Number(waterGoal);
    const stepsValue = Number(stepsGoal);
    if (!Number.isInteger(waterValue) || waterValue < 500 || waterValue > 10000 ||
        !Number.isInteger(stepsValue) || stepsValue < 1000 || stepsValue > 50000) {
      setError("El objetivo de agua debe estar entre 500 y 10000 ml y el de pasos entre 1000 y 50000.");
      return;
    }
    void runAction(async () => {
      await api("/targets", token!, { method: "PUT", body: {
        kcal: targets.kcal, protein_g: targets.protein_g, carbs_g: targets.carbs_g,
        fat_g: targets.fat_g, fiber_g: targets.fiber_g, workouts_per_week: targets.workouts_per_week,
        water_ml: waterValue, steps_goal: stepsValue,
      } });
    }, "Objetivos actualizados.");
  }

  function changeConnection(item: Connection) {
    if (item.connected) {
      Alert.alert("Desconectar " + item.label, "Se revocará el consentimiento de esta fuente. Los datos ya importados se conservarán.", [
        { text: "Cancelar", style: "cancel" },
        { text: "Desconectar", style: "destructive", onPress: () => void runAction(async () => {
          await api("/activity/connections/" + item.provider, token!, { method: "DELETE" });
        }, "Consentimiento revocado.") },
      ]);
      return;
    }
    if (!item.configured) {
      setNotice(item.note);
      return;
    }
    Alert.alert("Dar consentimiento", item.note + " Dar consentimiento no instala ni activa por sí solo la integración.", [
      { text: "Cancelar", style: "cancel" },
      { text: "Continuar", onPress: () => void runAction(async () => {
        await api("/activity/connections", token!, { method: "POST", body: { provider: item.provider } });
      }, "Consentimiento registrado. La sincronización requiere la app Android complementaria.") },
    ]);
  }

  const today = localDateISO();
  const checkin = checkins.find(item => item.date === date);
  const moodAverage = checkins.length ? checkins.reduce((sum, item) => sum + item.mood, 0) / checkins.length : null;

  return <Screen>
    <PageTitle eyebrow="Hábitos y bienestar" title="Cuida lo que sostiene tu progreso" subtitle="Hidratación, pasos y estado de ánimo. Los registros se sincronizan con tu cuenta." />
    <Panel>
      <Field label="Día seleccionado (AAAA-MM-DD)" value={date} onChangeText={setDate} placeholder="2026-11-26" />
      <Muted>Los registros futuros no están permitidos. Hoy es {today}.</Muted>
    </Panel>
    {loading ? <ActivityIndicator color={colors.accent} /> : null}
    <ErrorMessage message={error} />
    {notice ? <Text style={{ color: colors.accent, fontSize: 13 }}>{notice}</Text> : null}
    <SectionTitle title="Resumen de hoy" action="Últimos 14 días" />
    <View style={{ flexDirection: "row", gap: 10 }}>
      <Panel style={{ flex: 1 }}>
        <Muted>Agua</Muted>
        <Text style={{ color: colors.text, fontSize: 23, fontWeight: "900" }}>{fmt(water?.today_ml)} ml</Text>
        <Muted>Objetivo {fmt(water?.goal_ml)} ml</Muted>
        <ProgressBar value={water?.today_pct ?? 0} color={colors.blue} />
        <Muted>Media: {fmt(water?.avg_ml)} ml</Muted>
      </Panel>
      <Panel style={{ flex: 1 }}>
        <Muted>Pasos</Muted>
        <Text style={{ color: colors.text, fontSize: 23, fontWeight: "900" }}>{fmt(activity?.today_steps)}</Text>
        <Muted>Objetivo {fmt(activity?.goal)}</Muted>
        <ProgressBar value={activity?.today_pct ?? 0} />
        <Muted>Media: {fmt(activity?.avg_steps)}</Muted>
      </Panel>
    </View>
    <Panel>
      <SectionTitle title="Registrar agua" />
      <ChoiceRow value={waterAmount} onChange={setWaterAmount} options={["150","250","330","500","750"].map(value => ({ value, label: value + " ml" }))} />
      <AppButton title="Añadir " + waterAmount + " ml" onPress={addWater} loading={busy} />
      {waterLogs.length ? waterLogs.map(item => <View key={item.id} style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 9 }}>
        <View><Text style={{ color: colors.text, fontWeight: "700" }}>{fmt(item.quantity_ml)} ml</Text><Muted>{new Date(item.logged_at).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" })}</Muted></View>
        <Text onPress={() => deleteWater(item)} style={{ color: colors.danger, fontWeight: "700", padding: 8 }}>Eliminar</Text>
      </View>) : <Muted>No hay tomas registradas para este día.</Muted>}
    </Panel>
    <Panel>
      <SectionTitle title="Registrar actividad" />
      <Field label="Pasos" value={steps} onChangeText={setSteps} keyboardType="number-pad" placeholder="Ej. 8500" />
      <Field label="Distancia (km), opcional" value={distance} onChangeText={setDistance} keyboardType="decimal-pad" placeholder="Ej. 6,2" />
      <AppButton title="Guardar actividad" onPress={saveActivity} loading={busy} disabled={!steps.trim()} variant="secondary" />
      <Muted>Los pasos se registran manualmente. La sincronización automática con Health Connect/Samsung Health requiere una integración Android adicional.</Muted>
    </Panel>
    <Panel>
      <SectionTitle title="Check-in diario" action={checkin ? "Ya registrado" : "Pendiente"} />
      <Muted>Valora tu día del 1 (muy bajo) al 5 (muy bien). Las notas son privadas y no se envían a la IA.</Muted>
      <Text style={{ color: colors.text, fontWeight: "700" }}>Ánimo</Text>
      <ChoiceRow value={mood} onChange={setMood} options={scoreOptions} />
      <Text style={{ color: colors.text, fontWeight: "700" }}>Energía</Text>
      <ChoiceRow value={energy} onChange={setEnergy} options={scoreOptions} />
      <Text style={{ color: colors.text, fontWeight: "700" }}>Estrés</Text>
      <ChoiceRow value={stress} onChange={setStress} options={scoreOptions} />
      <Text style={{ color: colors.text, fontWeight: "700" }}>Calidad del sueño</Text>
      <ChoiceRow value={sleep} onChange={setSleep} options={scoreOptions} />
      <Field label="Nota personal (opcional)" value={notes} onChangeText={setNotes} multiline numberOfLines={4} maxLength={2000} />
      <AppButton title={checkin ? "Actualizar check-in" : "Guardar check-in"} onPress={saveCheckin} loading={busy} />
    </Panel>
    <Panel>
      <SectionTitle title="Objetivos de bienestar" />
      <Field label="Agua diaria (ml)" value={waterGoal} onChangeText={setWaterGoal} keyboardType="number-pad" />
      <Field label="Pasos diarios" value={stepsGoal} onChangeText={setStepsGoal} keyboardType="number-pad" />
      <AppButton title="Guardar objetivos" onPress={saveGoals} loading={busy} variant="secondary" />
    </Panel>
    <Panel>
      <SectionTitle title="Constancia" />
      <Text style={{ color: colors.text, fontSize: 24, fontWeight: "900" }}>{checkins.length} check-ins</Text>
      <Muted>Ánimo medio de los registros recientes: {moodAverage === null ? "—" : moodAverage.toFixed(1) + "/5"}</Muted>
      {checkins.slice().reverse().slice(0, 8).map(item => <View key={item.date} style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 8 }}>
        <Text style={{ color: colors.text, fontWeight: "700" }}>{item.date}</Text>
        <Muted>Ánimo {item.mood}/5 · Energía {item.energy_level ?? "—"}/5 · Sueño {item.sleep_quality ?? "—"}/5</Muted>
      </View>)}
    </Panel>
    <Panel>
      <SectionTitle title="Fuentes de actividad" />
      <Muted>Puedes conceder o revocar el consentimiento. El consentimiento no equivale a una sincronización automática; las fuentes móviles requieren que la app complementaria esté instalada y conectada.</Muted>
      {connections.map(item => <View key={item.provider} style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 10, gap: 6 }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <Text style={{ color: colors.text, fontWeight: "800", flex: 1 }}>{item.label}</Text>
          <Text style={{ color: item.connected ? colors.accent : colors.muted, fontSize: 11, fontWeight: "800" }}>{item.connected ? "CONECTADO" : item.configured ? "DISPONIBLE" : "PENDIENTE"}</Text>
        </View>
        <Muted>{item.note}</Muted>
        <AppButton title={item.connected ? "Revocar consentimiento" : item.configured ? "Dar consentimiento" : "Ver estado"} variant="quiet" onPress={() => changeConnection(item)} loading={busy} />
      </View>)}
    </Panel>
  </Screen>;
}
