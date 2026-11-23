import React, { useEffect, useState } from "react";
import {
  ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, SafeAreaView,
  ScrollView, StatusBar, StyleSheet, Text, TextInput, View,
} from "react-native";
import type { components } from "@smartfit/contracts";
import {
  authenticateMobile, clearSession, completeMobileOnboarding,
  logoutMobile, restoreMobileSession,
} from "./src/api";

type User = components["schemas"]["UserOut"];
type Mode = "login" | "register";
type Profile = {
  sex: "male" | "female";
  birth_date: string;
  height_cm: string;
  weight_kg: string;
  activity_level: "sedentary" | "light" | "moderate" | "high" | "very_high";
  goal: "gain_muscle" | "lose_fat" | "definition" | "recomposition" | "maintain";
  experience_level: "beginner" | "intermediate" | "advanced";
  available_training_days: string;
};

const initialProfile: Profile = {
  sex: "male", birth_date: "1995-01-01", height_cm: "175", weight_kg: "75",
  activity_level: "moderate", goal: "recomposition", experience_level: "beginner",
  available_training_days: "3",
};

function Field({ label, value, onChangeText, placeholder, keyboardType = "default" }: {
  label: string; value: string; onChangeText: (value: string) => void;
  placeholder?: string; keyboardType?: "default" | "numeric";
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        style={styles.input}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor="#7c8580"
        keyboardType={keyboardType}
        autoCapitalize="none"
      />
    </View>
  );
}

function Choices<T extends string>({ label, value, options, onChange }: {
  label: string; value: T; options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.choices}>
        {options.map(option => (
          <Pressable key={option.value} onPress={() => onChange(option.value)}
            style={[styles.choice, value === option.value && styles.choiceActive]}>
            <Text style={[styles.choiceText, value === option.value && styles.choiceTextActive]}>{option.label}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [mode, setMode] = useState<Mode>("login");
  const [profile, setProfile] = useState(initialProfile);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    restoreMobileSession()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setBusy(false));
  }, []);

  async function authenticate() {
    setBusy(true); setError(""); setNotice("");
    try {
      const nextUser = await authenticateMobile(mode, { name: username.trim(), password });
      setUser(nextUser);
      setPassword("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo iniciar sesión.");
    } finally { setBusy(false); }
  }

  async function submitOnboarding() {
    setBusy(true); setError(""); setNotice("");
    try {
      await completeMobileOnboarding({
        ...profile,
        height_cm: Number(profile.height_cm),
        weight_kg: Number(profile.weight_kg),
        available_training_days: Number(profile.available_training_days),
      } as components["schemas"]["OnboardingIn"]);
      setUser(current => current ? { ...current, onboarding_completed: true } : current);
      setNotice("Tu perfil está configurado. Ya puedes empezar.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar el perfil.");
    } finally { setBusy(false); }
  }

  async function signOut() {
    setBusy(true);
    try { await logoutMobile(); } catch { await clearSession(); }
    setUser(null); setNotice(""); setError(""); setBusy(false);
  }

  if (busy && !user) {
    return <SafeAreaView style={styles.center}><StatusBar barStyle="light-content" /><ActivityIndicator size="large" color="#c6f36b" /><Text style={styles.muted}>Preparando SmartFit…</Text></SafeAreaView>;
  }

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar barStyle="light-content" />
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
          <View style={styles.header}>
            <View style={styles.brandMark}><Text style={styles.brandLetter}>S</Text></View>
            <Text style={styles.brand}>SMARTFIT</Text>
            <Text style={styles.version}>MOBILE PREVIEW · 0.1</Text>
          </View>

          {!user ? (
            <View style={styles.card}>
              <Text style={styles.kicker}>ENTRENAMIENTO · NUTRICIÓN · HÁBITOS</Text>
              <Text style={styles.heading}>{mode === "login" ? "Tu progreso,\ncon criterio." : "Empieza por\naquí."}</Text>
              <Text style={styles.description}>{mode === "login" ? "Accede a tu espacio personal." : "Crea tu cuenta SmartFit y configura tu punto de partida."}</Text>
              <Field label="Nombre de usuario" value={username} onChangeText={setUsername} placeholder="Tu usuario" />
              <View style={styles.field}>
                <Text style={styles.label}>Contraseña</Text>
                <TextInput style={styles.input} value={password} onChangeText={setPassword}
                  placeholder="Mínimo 8 caracteres" placeholderTextColor="#7c8580"
                  secureTextEntry autoCapitalize="none" />
              </View>
              <Pressable disabled={busy || username.trim().length < 3 || password.length < 8}
                onPress={authenticate} style={[styles.primary, (busy || username.trim().length < 3 || password.length < 8) && styles.disabled]}>
                {busy ? <ActivityIndicator color="#172019" /> : <Text style={styles.primaryText}>{mode === "login" ? "Iniciar sesión  ↗" : "Crear cuenta  ↗"}</Text>}
              </Pressable>
              <Pressable onPress={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>
                <Text style={styles.switch}>{mode === "login" ? "¿No tienes cuenta?  Regístrate" : "¿Ya tienes cuenta?  Inicia sesión"}</Text>
              </Pressable>
            </View>
          ) : !user.onboarding_completed ? (
            <View style={styles.card}>
              <Text style={styles.kicker}>01 / CONFIGURACIÓN INICIAL</Text>
              <Text style={styles.heading}>Tu punto de partida.</Text>
              <Text style={styles.description}>Hola, {user.name}. Completa tu perfil para calcular tus objetivos.</Text>
              <Choices label="Sexo biológico" value={profile.sex} onChange={sex => setProfile(p => ({ ...p, sex }))}
                options={[{value:"male",label:"Hombre"},{value:"female",label:"Mujer"}]} />
              <Field label="Fecha de nacimiento (AAAA-MM-DD)" value={profile.birth_date} onChangeText={birth_date => setProfile(p => ({...p,birth_date}))} />
              <View style={styles.twoColumns}>
                <View style={styles.column}><Field label="Altura (cm)" value={profile.height_cm} onChangeText={height_cm => setProfile(p => ({...p,height_cm}))} keyboardType="numeric" /></View>
                <View style={styles.column}><Field label="Peso (kg)" value={profile.weight_kg} onChangeText={weight_kg => setProfile(p => ({...p,weight_kg}))} keyboardType="numeric" /></View>
              </View>
              <Choices label="Actividad" value={profile.activity_level} onChange={activity_level => setProfile(p => ({...p,activity_level}))}
                options={[{value:"sedentary",label:"Baja"},{value:"light",label:"Ligera"},{value:"moderate",label:"Moderada"},{value:"high",label:"Alta"},{value:"very_high",label:"Muy alta"}]} />
              <Choices label="Objetivo" value={profile.goal} onChange={goal => setProfile(p => ({...p,goal}))}
                options={[{value:"gain_muscle",label:"Ganar músculo"},{value:"lose_fat",label:"Perder grasa"},{value:"definition",label:"Definición"},{value:"recomposition",label:"Recomposición"},{value:"maintain",label:"Mantener"}]} />
              <Choices label="Experiencia" value={profile.experience_level} onChange={experience_level => setProfile(p => ({...p,experience_level}))}
                options={[{value:"beginner",label:"Inicial"},{value:"intermediate",label:"Media"},{value:"advanced",label:"Avanzada"}]} />
              <Choices label="Días de entrenamiento" value={profile.available_training_days} onChange={available_training_days => setProfile(p => ({...p,available_training_days}))}
                options={[1,2,3,4,5,6,7].map(n => ({value:String(n),label:String(n)}))} />
              <Pressable disabled={busy} onPress={submitOnboarding} style={[styles.primary,busy && styles.disabled]}>
                {busy ? <ActivityIndicator color="#172019" /> : <Text style={styles.primaryText}>Guardar y calcular objetivos  ↗</Text>}
              </Pressable>
              <Pressable onPress={signOut}><Text style={styles.switch}>Cerrar sesión</Text></Pressable>
            </View>
          ) : (
            <View style={styles.card}>
              <Text style={styles.kicker}>ESPACIO PERSONAL</Text>
              <Text style={styles.heading}>Hola, {user.name}.</Text>
              <Text style={styles.description}>Tu cuenta móvil ya está conectada con SmartFit. Esta primera entrega establece la base nativa; los módulos funcionales se incorporarán por etapas.</Text>
              <View style={styles.feature}><Text style={styles.featureTitle}>01  Nutrición</Text><Text style={styles.featureText}>Próxima integración</Text></View>
              <View style={styles.feature}><Text style={styles.featureTitle}>02  Entrenamiento</Text><Text style={styles.featureText}>Próxima integración</Text></View>
              <View style={styles.feature}><Text style={styles.featureTitle}>03  Hábitos y progreso</Text><Text style={styles.featureText}>Próxima integración</Text></View>
              <Pressable disabled={busy} onPress={signOut} style={styles.secondary}><Text style={styles.secondaryText}>Cerrar sesión</Text></Pressable>
            </View>
          )}

          {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
          {!!notice && <Text style={styles.notice}>{notice}</Text>}
          <Text style={styles.footer}>TUS DATOS SE PROTEGEN EN EL DISPOSITIVO Y EN LA API</Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  safe: { flex: 1, backgroundColor: "#101612" },
  center: { flex: 1, backgroundColor: "#101612", alignItems: "center", justifyContent: "center", gap: 16 },
  container: { flexGrow: 1, paddingHorizontal: 22, paddingTop: 24, paddingBottom: 40, maxWidth: 560, width: "100%", alignSelf: "center" },
  header: { flexDirection: "row", alignItems: "center", marginBottom: 34 },
  brandMark: { width: 34, height: 34, borderRadius: 10, backgroundColor: "#c6f36b", alignItems: "center", justifyContent: "center", marginRight: 10 },
  brandLetter: { color: "#172019", fontWeight: "900", fontSize: 21 },
  brand: { color: "#f0f4ed", fontSize: 14, letterSpacing: 3, fontWeight: "800" },
  version: { color: "#829087", fontSize: 9, letterSpacing: 1.4, marginLeft: "auto" },
  card: { backgroundColor: "#19211b", borderColor: "#303b32", borderWidth: 1, borderRadius: 22, padding: 22 },
  kicker: { color: "#c6f36b", fontSize: 10, letterSpacing: 2, fontWeight: "700", marginBottom: 18 },
  heading: { color: "#f1f5ee", fontSize: 34, lineHeight: 39, fontWeight: "700", letterSpacing: -1.2, marginBottom: 12 },
  description: { color: "#a9b4aa", fontSize: 14, lineHeight: 21, marginBottom: 24 },
  field: { marginBottom: 17, flex: 1 },
  label: { color: "#d7dfd6", fontSize: 12, fontWeight: "600", marginBottom: 8 },
  input: { backgroundColor: "#111813", borderColor: "#39443b", borderWidth: 1, borderRadius: 11, paddingHorizontal: 13, paddingVertical: 13, color: "#f2f5ef", fontSize: 15 },
  primary: { backgroundColor: "#c6f36b", borderRadius: 12, minHeight: 50, alignItems: "center", justifyContent: "center", marginTop: 8 },
  primaryText: { color: "#182018", fontSize: 14, fontWeight: "800" },
  disabled: { opacity: 0.55 },
  switch: { color: "#c6f36b", textAlign: "center", fontSize: 13, marginTop: 20, marginBottom: 2 },
  muted: { color: "#a9b4aa" },
  error: { color: "#ff9e91", marginTop: 16, lineHeight: 20, textAlign: "center" },
  notice: { color: "#c6f36b", marginTop: 16, textAlign: "center" },
  footer: { color: "#738077", fontSize: 9, letterSpacing: 1.2, textAlign: "center", marginTop: 28 },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  choice: { borderWidth: 1, borderColor: "#39443b", borderRadius: 18, paddingHorizontal: 12, paddingVertical: 9 },
  choiceActive: { borderColor: "#c6f36b", backgroundColor: "#2a3825" },
  choiceText: { color: "#a9b4aa", fontSize: 12 },
  choiceTextActive: { color: "#d8f5a5", fontWeight: "700" },
  twoColumns: { flexDirection: "row", gap: 12 },
  column: { flex: 1 },
  feature: { borderTopWidth: 1, borderTopColor: "#344036", paddingVertical: 16 },
  featureTitle: { color: "#eaf0e6", fontWeight: "700", fontSize: 15 },
  featureText: { color: "#87948a", fontSize: 12, marginTop: 4 },
  secondary: { borderWidth: 1, borderColor: "#56634f", borderRadius: 12, alignItems: "center", padding: 14, marginTop: 22 },
  secondaryText: { color: "#d5e0d1", fontWeight: "700" },
});
