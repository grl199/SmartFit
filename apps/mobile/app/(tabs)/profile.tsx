import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Alert, Text, View } from "react-native";
import { router } from "expo-router";
import { useAuth } from "@/auth/AuthProvider";
import { api } from "@/lib/api";
import { AppButton, ChoiceRow, ErrorMessage, Field, Muted, PageTitle, Panel, Screen, SectionTitle } from "@/components/ui";
import { colors } from "@/theme";

type Sex = "male" | "female";
type Activity = "sedentary" | "light" | "moderate" | "high" | "very_high";
type Goal = "gain_muscle" | "lose_fat" | "definition" | "recomposition" | "maintain";
type Experience = "beginner" | "intermediate" | "advanced";
type ProfileData = {
  sex: Sex; birth_date: string; height_cm: string; activity_level: Activity; goal: Goal;
  experience_level: Experience; available_training_days: string;
  dietary_restrictions: string; context_notes: string;
};
type TargetData = {
  kcal: string; protein_g: string; carbs_g: string; fat_g: string; fiber_g: string;
  workouts_per_week: string; water_ml: string; steps_goal: string;
  rationale?: string | null; source?: string;
};
type EnergyData = { age?: number | null; weight_kg?: number | null; bmr?: number | null; tdee?: number | null; missing?: string[] };
const initialProfile: ProfileData = {
  sex: "male", birth_date: "", height_cm: "", activity_level: "moderate",
  goal: "recomposition", experience_level: "beginner", available_training_days: "3",
  dietary_restrictions: "", context_notes: "",
};

export default function ProfileScreen() {
  const { user, token, signOut } = useAuth();
  const [profile, setProfile] = useState<ProfileData>(initialProfile);
  const [targets, setTargets] = useState<TargetData | null>(null);
  const [energy, setEnergy] = useState<EnergyData | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    if (!token) return;
    try {
      const [p, t, e] = await Promise.all([
        api<Partial<ProfileData>>("/profile", token),
        api<Record<string, unknown>>("/targets", token),
        api<EnergyData>("/profile/energy", token),
      ]);
      setProfile({
        sex: (p.sex as Sex) ?? "male",
        birth_date: p.birth_date ?? "",
        height_cm: p.height_cm == null ? "" : String(p.height_cm),
        activity_level: p.activity_level ?? "moderate",
        goal: p.goal ?? "recomposition",
        experience_level: p.experience_level ?? "beginner",
        available_training_days: p.available_training_days == null ? "3" : String(p.available_training_days),
        dietary_restrictions: p.dietary_restrictions ?? "",
        context_notes: p.context_notes ?? "",
      });
      setTargets({
        kcal: String(t.kcal ?? ""), protein_g: String(t.protein_g ?? ""), carbs_g: String(t.carbs_g ?? ""),
        fat_g: String(t.fat_g ?? ""), fiber_g: String(t.fiber_g ?? ""), workouts_per_week: String(t.workouts_per_week ?? ""),
        water_ml: String(t.water_ml ?? ""), steps_goal: String(t.steps_goal ?? ""),
        rationale: typeof t.rationale === "string" ? t.rationale : null,
        source: typeof t.source === "string" ? t.source : "manual",
      });
      setEnergy(e);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo cargar tu perfil.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { void load(); }, [load]);

  function updateProfile<K extends keyof ProfileData>(key: K, value: ProfileData[K]) {
    setProfile(current => ({ ...current, [key]: value }));
  }
  function updateTarget<K extends keyof TargetData>(key: K, value: TargetData[K]) {
    setTargets(current => current ? ({ ...current, [key]: value }) : current);
  }

  async function saveProfile() {
    if (!token) return;
    const height = profile.height_cm.trim() ? Number(profile.height_cm.replace(",", ".")) : null;
    const days = Number(profile.available_training_days);
    if (height !== null && (!Number.isFinite(height) || height < 100 || height > 250)) {
      setError("La altura debe estar entre 100 y 250 cm.");
      return;
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(profile.birth_date)) {
      setError("Introduce la fecha de nacimiento en formato AAAA-MM-DD.");
      return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/profile", token, { method: "PUT", body: {
        sex: profile.sex, birth_date: profile.birth_date, height_cm: height,
        activity_level: profile.activity_level, goal: profile.goal,
        experience_level: profile.experience_level, available_training_days: days,
        dietary_restrictions: profile.dietary_restrictions.trim() || null,
        context_notes: profile.context_notes.trim() || null,
      } });
      await load();
      setNotice("Perfil actualizado.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo guardar el perfil.");
    } finally {
      setBusy(false);
    }
  }

  async function saveTargets() {
    if (!token || !targets) return;
    const values = {
      kcal: Number(targets.kcal), protein_g: Number(targets.protein_g), carbs_g: Number(targets.carbs_g),
      fat_g: Number(targets.fat_g), fiber_g: Number(targets.fiber_g),
      workouts_per_week: Number(targets.workouts_per_week),
      water_ml: targets.water_ml.trim() ? Number(targets.water_ml) : null,
      steps_goal: targets.steps_goal.trim() ? Number(targets.steps_goal) : null,
    };
    if (Object.values(values).some(value => value !== null && !Number.isFinite(value))) {
      setError("Revisa los valores numéricos de tus objetivos.");
      return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/targets", token, { method: "PUT", body: values });
      await load();
      setNotice("Objetivos diarios y semanales actualizados.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudieron guardar los objetivos.");
    } finally {
      setBusy(false);
    }
  }

  async function regenerateTargets() {
    if (!token) return;
    Alert.alert("Regenerar objetivos", "SmartFit recalculará tus objetivos a partir de tus datos de perfil y tu peso actual. ¿Continuar?", [
      { text: "Cancelar", style: "cancel" },
      { text: "Regenerar", onPress: () => {
        void (async () => {
          setBusy(true); setError(""); setNotice("");
          try {
            await api("/targets/generate", token, { method: "POST" });
            await load();
            setNotice("Objetivos regenerados a partir de tu perfil.");
          } catch (reason) {
            setError(reason instanceof Error ? reason.message : "No se pudieron regenerar los objetivos.");
          } finally {
            setBusy(false);
          }
        })();
      } },
    ]);
  }

  function confirmSignOut() {
    Alert.alert("Cerrar sesión", "¿Quieres salir de tu cuenta en este dispositivo?", [
      { text: "Cancelar", style: "cancel" },
      { text: "Cerrar sesión", style: "destructive", onPress: () => {
        void (async () => {
          setBusy(true);
          try { await signOut(); router.replace("/(auth)/login"); }
          finally { setBusy(false); }
        })();
      } },
    ]);
  }

  return <Screen>
    <PageTitle eyebrow="Cuenta" title="Tu perfil y objetivos" subtitle="Edita tus datos, ajusta las metas de SmartFit y revisa cómo se calculan tus necesidades energéticas." />
    {loading ? <ActivityIndicator color={colors.accent} /> : null}
    <ErrorMessage message={error} />
    {notice ? <Text style={{ color: colors.accent, fontSize: 13 }}>{notice}</Text> : null}
    <Panel style={{ alignItems: "center", paddingVertical: 22 }}>
      <View style={{ width: 66, height: 66, borderRadius: 23, backgroundColor: colors.accentDark, borderWidth: 1, borderColor: colors.accent, alignItems: "center", justifyContent: "center" }}>
        <Text style={{ color: colors.accent, fontSize: 27, fontWeight: "900" }}>{(user?.name?.[0] ?? "S").toUpperCase()}</Text>
      </View>
      <Text style={{ color: colors.text, fontSize: 20, fontWeight: "900", marginTop: 10 }}>{user?.name}</Text>
      <Muted>Miembro SmartFit · Perfil {user?.onboarding_completed ? "configurado" : "pendiente"}</Muted>
    </Panel>
    <SectionTitle title="Datos personales" />
    <Panel>
      <Text style={{ color: colors.text, fontWeight: "700" }}>Sexo</Text>
      <ChoiceRow value={profile.sex} onChange={value => updateProfile("sex", value)} options={[{ value: "male", label: "Hombre" }, { value: "female", label: "Mujer" }]} />
      <Field label="Fecha de nacimiento (AAAA-MM-DD)" value={profile.birth_date} onChangeText={value => updateProfile("birth_date", value)} placeholder="1995-01-31" />
      <Field label="Altura (cm)" value={profile.height_cm} onChangeText={value => updateProfile("height_cm", value)} keyboardType="decimal-pad" placeholder="175" />
      <Text style={{ color: colors.text, fontWeight: "700" }}>Nivel de actividad</Text>
      <ChoiceRow value={profile.activity_level} onChange={value => updateProfile("activity_level", value)} options={[
        { value: "sedentary", label: "Sedentario" }, { value: "light", label: "Ligero" },
        { value: "moderate", label: "Moderado" }, { value: "high", label: "Alto" }, { value: "very_high", label: "Muy alto" },
      ]} />
      <Text style={{ color: colors.text, fontWeight: "700" }}>Objetivo</Text>
      <ChoiceRow value={profile.goal} onChange={value => updateProfile("goal", value)} options={[
        { value: "gain_muscle", label: "Ganar músculo" }, { value: "lose_fat", label: "Perder grasa" },
        { value: "definition", label: "Definición" }, { value: "recomposition", label: "Recomposición" },
        { value: "maintain", label: "Mantener" },
      ]} />
      <Text style={{ color: colors.text, fontWeight: "700" }}>Experiencia</Text>
      <ChoiceRow value={profile.experience_level} onChange={value => updateProfile("experience_level", value)} options={[
        { value: "beginner", label: "Principiante" }, { value: "intermediate", label: "Intermedio" }, { value: "advanced", label: "Avanzado" },
      ]} />
      <Text style={{ color: colors.text, fontWeight: "700" }}>Días disponibles para entrenar</Text>
      <ChoiceRow value={profile.available_training_days} onChange={value => updateProfile("available_training_days", value)} options={[1,2,3,4,5,6,7].map(value => ({ value: String(value), label: String(value) + " días" }))} />
      <Field label="Restricciones alimentarias" value={profile.dietary_restrictions} onChangeText={value => updateProfile("dietary_restrictions", value)} multiline numberOfLines={3} maxLength={500} placeholder="Alergias, intolerancias o preferencias…" />
      <Field label="Contexto adicional" value={profile.context_notes} onChangeText={value => updateProfile("context_notes", value)} multiline numberOfLines={4} maxLength={2000} placeholder="Información que ayude a personalizar tus recomendaciones…" />
      <AppButton title="Guardar perfil" onPress={() => void saveProfile()} loading={busy} />
    </Panel>
    <SectionTitle title="Necesidades energéticas" />
    <Panel>
      <View style={{ flexDirection: "row", gap: 10 }}>
        <View style={{ flex: 1 }}><Muted>Edad</Muted><Text style={{ color: colors.text, fontSize: 22, fontWeight: "900" }}>{energy?.age ?? "—"}</Text></View>
        <View style={{ flex: 1 }}><Muted>Peso actual</Muted><Text style={{ color: colors.text, fontSize: 22, fontWeight: "900" }}>{energy?.weight_kg == null ? "—" : energy.weight_kg.toFixed(1) + " kg"}</Text></View>
      </View>
      <View style={{ flexDirection: "row", gap: 10 }}>
        <View style={{ flex: 1 }}><Muted>Metabolismo basal</Muted><Text style={{ color: colors.text, fontSize: 22, fontWeight: "900" }}>{energy?.bmr == null ? "—" : Math.round(energy.bmr) + " kcal"}</Text></View>
        <View style={{ flex: 1 }}><Muted>Gasto diario estimado</Muted><Text style={{ color: colors.text, fontSize: 22, fontWeight: "900" }}>{energy?.tdee == null ? "—" : Math.round(energy.tdee) + " kcal"}</Text></View>
      </View>
      {energy?.missing?.length ? <Muted>Para completar el cálculo faltan: {energy.missing.join(", ")}.</Muted> : <Muted>Estimaciones calculadas a partir de tu perfil y tu último peso registrado.</Muted>}
    </Panel>
    <SectionTitle title="Objetivos diarios y semanales" />
    {targets ? <Panel>
      <Field label="Calorías (kcal)" value={targets.kcal} onChangeText={value => updateTarget("kcal", value)} keyboardType="decimal-pad" />
      <Field label="Proteína (g)" value={targets.protein_g} onChangeText={value => updateTarget("protein_g", value)} keyboardType="decimal-pad" />
      <Field label="Carbohidratos (g)" value={targets.carbs_g} onChangeText={value => updateTarget("carbs_g", value)} keyboardType="decimal-pad" />
      <Field label="Grasas (g)" value={targets.fat_g} onChangeText={value => updateTarget("fat_g", value)} keyboardType="decimal-pad" />
      <Field label="Fibra (g)" value={targets.fiber_g} onChangeText={value => updateTarget("fiber_g", value)} keyboardType="decimal-pad" />
      <Field label="Entrenamientos por semana" value={targets.workouts_per_week} onChangeText={value => updateTarget("workouts_per_week", value)} keyboardType="number-pad" />
      <Field label="Agua diaria (ml)" value={targets.water_ml} onChangeText={value => updateTarget("water_ml", value)} keyboardType="number-pad" />
      <Field label="Pasos diarios" value={targets.steps_goal} onChangeText={value => updateTarget("steps_goal", value)} keyboardType="number-pad" />
      <AppButton title="Guardar objetivos" onPress={() => void saveTargets()} loading={busy} variant="secondary" />
      <AppButton title="Regenerar objetivos con IA" onPress={regenerateTargets} loading={busy} variant="quiet" />
      {targets.rationale ? <Muted>{targets.rationale}</Muted> : null}
      <Muted>Origen de los objetivos: {targets.source === "manual" ? "ajuste manual" : targets.source ?? "SmartFit"}.</Muted>
    </Panel> : null}
    <SectionTitle title="Integraciones y próximas mejoras" />
    <Panel>
      <Text style={{ color: colors.text, fontWeight: "900" }}>Salud y dispositivos</Text>
      <View style={{ gap: 10 }}>
        <View><Text style={{ color: colors.text, fontWeight: "700" }}>Health Connect (Android)</Text><Muted>El backend acepta datos normalizados, pero falta la aplicación Android complementaria que lea los datos con permisos del usuario.</Muted></View>
        <View><Text style={{ color: colors.text, fontWeight: "700" }}>Samsung Health</Text><Muted>Requiere integrar Samsung Health Data SDK en una app Android complementaria.</Muted></View>
        <View><Text style={{ color: colors.text, fontWeight: "700" }}>Apple HealthKit</Text><Muted>Pendiente de desarrollo para iPhone y Apple Watch.</Muted></View>
        <View><Text style={{ color: colors.text, fontWeight: "700" }}>Garmin y Fitbit</Text><Muted>Integraciones previstas; todavía no importan datos.</Muted></View>
      </View>
      <Text style={{ color: colors.text, fontWeight: "900" }}>Automatizaciones previstas</Text>
      <Muted>Sincronización de pasos y entrenamientos, y registros de frecuencia cardiaca y sueño cuando las plataformas y permisos lo permitan.</Muted>
    </Panel>
    <Panel>
      <SectionTitle title="Sesión" />
      <Muted>ID de usuario · {user?.id}</Muted>
      <AppButton title="Cerrar sesión" onPress={confirmSignOut} variant="secondary" loading={busy} />
    </Panel>
  </Screen>;
}
