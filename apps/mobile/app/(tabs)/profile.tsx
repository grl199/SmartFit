import React,{useState} from "react";
import {Alert,Text,View} from "react-native";
import {router} from "expo-router";
import {useAuth} from "@/auth/AuthProvider";
import {AppButton,Muted,PageTitle,Panel,Screen,SectionTitle} from "@/components/ui";
import {colors} from "@/theme";
export default function ProfileScreen(){
  const {user,signOut}=useAuth();
  const [busy,setBusy]=useState(false);
  function confirmSignOut(){
    Alert.alert("Cerrar sesión","¿Quieres salir de tu cuenta en este dispositivo?",[
      {text:"Cancelar",style:"cancel"},
      {text:"Cerrar sesión",style:"destructive",onPress:()=>{void runSignOut();}}
    ]);
  }
  async function runSignOut(){
    setBusy(true);
    try{await signOut();router.replace("/(auth)/login");}
    finally{setBusy(false);}
  }
  return <Screen>
    <PageTitle eyebrow="Cuenta" title="Tu espacio" subtitle="Gestiona tu sesión y consulta la información básica de tu cuenta."/>
    <Panel style={{alignItems:"center",paddingVertical:26}}>
      <View style={{width:72,height:72,borderRadius:25,backgroundColor:colors.accentDark,borderWidth:1,borderColor:colors.accent,alignItems:"center",justifyContent:"center"}}>
        <Text style={{color:colors.accent,fontSize:29,fontWeight:"900"}}>{(user?.name?.[0]??"S").toUpperCase()}</Text>
      </View>
      <Text style={{color:colors.text,fontSize:21,fontWeight:"900",marginTop:12}}>{user?.name}</Text>
      <Muted>Miembro SmartFit</Muted>
      <Text style={{color:colors.muted,fontSize:11}}>ID de usuario · {user?.id}</Text>
    </Panel>
    <SectionTitle title="Cuenta"/>
    <Panel>
      <View style={{flexDirection:"row",justifyContent:"space-between"}}><Muted>Estado del perfil</Muted><Text style={{color:colors.accent,fontWeight:"800"}}>Configurado</Text></View>
      <View style={{flexDirection:"row",justifyContent:"space-between"}}><Muted>Onboarding</Muted><Text style={{color:colors.text,fontWeight:"700"}}>{user?.onboarding_completed?"Completado":"Pendiente"}</Text></View>
    </Panel>
    <AppButton title="Cerrar sesión" onPress={confirmSignOut} variant="secondary" loading={busy}/>
    <Muted>SmartFit Mobile · 0.1.0</Muted>
  </Screen>;
}