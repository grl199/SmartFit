import { Link, router } from "expo-router";
import React, { useState } from "react";
import { Text, View } from "react-native";
import { AppButton, ErrorMessage, Field, Panel, Screen } from "@/components/ui";
import { useAuth } from "@/auth/AuthProvider";
import { colors } from "@/theme";
export default function LoginScreen() {
  const { signIn } = useAuth();
  const [name,setName] = useState("");
  const [password,setPassword] = useState("");
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  async function submit() {
    setError(""); setBusy(true);
    try { await signIn(name,password); router.replace("/"); }
    catch(e) { setError(e instanceof Error ? e.message : "No se pudo iniciar sesión."); }
    finally { setBusy(false); }
  }
  return <Screen>
    <View style={{gap:9,marginTop:46}}>
      <View style={{width:58,height:58,borderRadius:19,backgroundColor:colors.accent,alignItems:"center",justifyContent:"center"}}>
        <Text style={{color:colors.background,fontSize:28,fontWeight:"900"}}>S</Text>
      </View>
      <Text style={{color:colors.text,fontSize:34,fontWeight:"900",marginTop:14}}>Entrena con intención.</Text>
      <Text style={{color:colors.muted,fontSize:15,lineHeight:22}}>Tu nutrición, tus entrenamientos y tu progreso en un solo lugar.</Text>
    </View>
    <Panel style={{marginTop:25}}>
      <Text style={{color:colors.text,fontSize:20,fontWeight:"800",marginBottom:8}}>Bienvenido de nuevo</Text>
      <Field label="Usuario" value={name} onChangeText={setName} autoCapitalize="none" autoCorrect={false} placeholder="Tu usuario" />
      <Field label="Contraseña" value={password} onChangeText={setPassword} secureTextEntry placeholder="Tu contraseña" returnKeyType="go" onSubmitEditing={() => void submit()} />
      <ErrorMessage message={error} />
      <AppButton title="Iniciar sesión" onPress={() => void submit()} loading={busy} disabled={!name.trim() || password.length < 8} />
      <Text style={{color:colors.muted,textAlign:"center",fontSize:13}}>¿Aún no tienes cuenta? <Link href="/(auth)/register" style={{color:colors.accent,fontWeight:"800"}}>Regístrate</Link></Text>
    </Panel>
    <Text style={{color:colors.muted,fontSize:11,textAlign:"center"}}>SMARTFIT · HÁBITOS QUE SUMAN</Text>
  </Screen>;
}