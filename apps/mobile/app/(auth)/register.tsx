import { Link, router } from "expo-router";
import React, { useState } from "react";
import { Text, View } from "react-native";
import { AppButton, ErrorMessage, Field, Panel, Screen } from "@/components/ui";
import { useAuth } from "@/auth/AuthProvider";
import { colors } from "@/theme";
export default function RegisterScreen() {
  const { signUp } = useAuth();
  const [name,setName] = useState("");
  const [password,setPassword] = useState("");
  const [repeat,setRepeat] = useState("");
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  async function submit() {
    setError("");
    if (password !== repeat) { setError("Las contraseñas no coinciden."); return; }
    setBusy(true);
    try { await signUp(name,password); router.replace("/onboarding"); }
    catch(e) { setError(e instanceof Error ? e.message : "No se pudo crear la cuenta."); }
    finally { setBusy(false); }
  }
  return <Screen>
    <View style={{gap:8,marginTop:28}}>
      <Text style={{color:colors.accent,fontWeight:"800",fontSize:11,letterSpacing:1.5}}>EMPIEZA HOY</Text>
      <Text style={{color:colors.text,fontSize:31,fontWeight:"900"}}>Crea tu cuenta</Text>
      <Text style={{color:colors.muted,fontSize:14,lineHeight:21}}>Prepararemos tu espacio de entrenamiento y nutrición.</Text>
    </View>
    <Panel>
      <Field label="Nombre de usuario" value={name} onChangeText={setName} autoCapitalize="none" placeholder="Mínimo 3 caracteres" />
      <Field label="Contraseña" value={password} onChangeText={setPassword} secureTextEntry placeholder="Mínimo 8 caracteres" />
      <Field label="Repite la contraseña" value={repeat} onChangeText={setRepeat} secureTextEntry placeholder="Confirma tu contraseña" />
      <ErrorMessage message={error} />
      <AppButton title="Crear cuenta" onPress={() => void submit()} loading={busy} disabled={name.trim().length<3 || password.length<8 || repeat.length<8} />
      <Text style={{color:colors.muted,textAlign:"center",fontSize:13}}>¿Ya tienes cuenta? <Link href="/(auth)/login" style={{color:colors.accent,fontWeight:"800"}}>Inicia sesión</Link></Text>
    </Panel>
  </Screen>;
}