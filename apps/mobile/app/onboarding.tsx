import { Redirect, router } from "expo-router";
import React, { useState } from "react";
import { Text } from "react-native";
import { AppButton, ChoiceRow, ErrorMessage, Field, PageTitle, Panel, Screen } from "@/components/ui";
import { useAuth } from "@/auth/AuthProvider";
import { colors } from "@/theme";
export default function OnboardingScreen() {
  const {user,completeOnboarding} = useAuth();
  const [sex,setSex] = useState<"male"|"female">("male");
  const [birthDate,setBirthDate] = useState("1992-01-01");
  const [height,setHeight] = useState("175");
  const [weight,setWeight] = useState("75");
  const [activity,setActivity] = useState<"sedentary"|"light"|"moderate"|"high"|"very_high">("moderate");
  const [goal,setGoal] = useState<"gain_muscle"|"lose_fat"|"definition"|"recomposition"|"maintain">("recomposition");
  const [experience,setExperience] = useState<"beginner"|"intermediate"|"advanced">("beginner");
  const [days,setDays] = useState("4");
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  if (!user) return <Redirect href="/(auth)/login" />;
  if (user.onboarding_completed) return <Redirect href="/(tabs)" />;
  async function submit() {
    setError("");
    const h=Number(height), w=Number(weight), d=Number(days);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(birthDate)) { setError("Introduce tu fecha en formato AAAA-MM-DD."); return; }
    if (!Number.isFinite(h)||h<100||h>250||!Number.isFinite(w)||w<=30||w>=300||d<1||d>7) { setError("Revisa altura, peso y días de entrenamiento."); return; }
    setBusy(true);
    try {
      await completeOnboarding({sex,birth_date:birthDate,height_cm:h,weight_kg:w,activity_level:activity,goal,experience_level:experience,available_training_days:d});
      router.replace("/(tabs)");
    } catch(e) { setError(e instanceof Error?e.message:"No se pudo guardar tu perfil."); }
    finally { setBusy(false); }
  }
  return <Screen>
    <PageTitle eyebrow="Tu punto de partida" title="Vamos a conocerte" subtitle="Con estos datos SmartFit calculará tus objetivos iniciales. Podrás ajustarlos más adelante." />
    <Panel>
      <Text style={{color:colors.text,fontWeight:"800"}}>1. Datos básicos</Text>
      <Text style={{color:colors.muted,fontSize:12}}>Sexo</Text>
      <ChoiceRow value={sex} onChange={setSex} options={[{value:"male",label:"Hombre"},{value:"female",label:"Mujer"}]} />
      <Field label="Fecha de nacimiento" value={birthDate} onChangeText={setBirthDate} placeholder="AAAA-MM-DD" />
      <Field label="Altura (cm)" value={height} onChangeText={setHeight} keyboardType="decimal-pad" />
      <Field label="Peso actual (kg)" value={weight} onChangeText={setWeight} keyboardType="decimal-pad" />
    </Panel>
    <Panel>
      <Text style={{color:colors.text,fontWeight:"800"}}>2. Tu actividad</Text>
      <ChoiceRow value={activity} onChange={setActivity} options={[
        {value:"sedentary",label:"Baja"},{value:"light",label:"Ligera"},{value:"moderate",label:"Moderada"},{value:"high",label:"Alta"},{value:"very_high",label:"Muy alta"}
      ]} />
      <Field label="Días de entrenamiento por semana" value={days} onChangeText={setDays} keyboardType="number-pad" />
    </Panel>
    <Panel>
      <Text style={{color:colors.text,fontWeight:"800"}}>3. Tu objetivo</Text>
      <ChoiceRow value={goal} onChange={setGoal} options={[
        {value:"gain_muscle",label:"Ganar músculo"},{value:"lose_fat",label:"Perder grasa"},{value:"definition",label:"Definición"},
        {value:"recomposition",label:"Recomposición"},{value:"maintain",label:"Mantener"}
      ]} />
      <Text style={{color:colors.muted,fontSize:12}}>Experiencia entrenando</Text>
      <ChoiceRow value={experience} onChange={setExperience} options={[
        {value:"beginner",label:"Principiante"},{value:"intermediate",label:"Intermedio"},{value:"advanced",label:"Avanzado"}
      ]} />
    </Panel>
    <ErrorMessage message={error} />
    <AppButton title="Guardar y crear mi plan" onPress={() => void submit()} loading={busy} />
  </Screen>;
}