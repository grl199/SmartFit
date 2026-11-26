import React,{useCallback,useEffect,useState} from "react";
import {Text,View} from "react-native";
import {api,type WeightEntry} from "@/lib/api";
import {dateLabel} from "@/lib/format";
import {useAuth} from "@/auth/AuthProvider";
import {AppButton,ErrorMessage,Field,Muted,PageTitle,Panel,Screen,SectionTitle} from "@/components/ui";
import {colors} from "@/theme";
export default function ProgressScreen(){
  const {token}=useAuth();
  const [weights,setWeights]=useState<WeightEntry[]>([]);
  const [weight,setWeight]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const load=useCallback(async()=>{
    if(!token)return;
    try{setWeights(await api<WeightEntry[]>("/metrics/weight?days=180",token));setError("");}
    catch(e){setError(e instanceof Error?e.message:"No se pudo cargar tu progreso.");}
  },[token]);
  useEffect(()=>{void load();},[load]);
  async function addWeight(){
    if(!token)return;
    const value=Number(weight.replace(",",".")); 
    if(!Number.isFinite(value)||value<=20||value>=400){setError("Introduce un peso válido en kg.");return;}
    setBusy(true);setError("");
    try{await api("/metrics/weight",token,{method:"POST",body:{weight_kg:value}});setWeight("");await load();}
    catch(e){setError(e instanceof Error?e.message:"No se pudo guardar el peso.");}
    finally{setBusy(false);}
  }
  const latest=weights.length?weights[weights.length-1]:null;
  const previous=weights.length>1?weights[weights.length-2]:null;
  const delta=latest&&previous?latest.weight_kg-previous.weight_kg:null;
  return <Screen>
    <PageTitle eyebrow="Progreso" title="Mira lo que avanzas" subtitle="El progreso se construye con datos y constancia, no con un único día."/>
    <View style={{flexDirection:"row",gap:10}}>
      <Panel style={{flex:1}}><Muted>Último peso</Muted><Text style={{color:colors.text,fontSize:27,fontWeight:"900"}}>{latest?latest.weight_kg.toFixed(1)+" kg":"—"}</Text><Muted>{latest?dateLabel(latest.measured_on):"Registra tu primer dato"}</Muted></Panel>
      <Panel style={{flex:1}}><Muted>Variación</Muted><Text style={{color:delta===null?colors.text:delta<=0?colors.accent:colors.orange,fontSize:27,fontWeight:"900"}}>{delta===null?"—":(delta>0?"+":"")+delta.toFixed(1)+" kg"}</Text><Muted>Vs. registro anterior</Muted></Panel>
    </View>
    <SectionTitle title="Registrar peso"/>
    <Panel><Field label="Peso de hoy (kg)" value={weight} onChangeText={setWeight} keyboardType="decimal-pad" placeholder="Ej. 74,5"/>
      <ErrorMessage message={error}/><AppButton title="Guardar peso" onPress={()=>void addWeight()} loading={busy} disabled={!weight.trim()}/></Panel>
    <SectionTitle title="Historial de peso" action="Últimos 180 días"/>
    <Panel>{weights.length?[...weights].reverse().map(entry=><View key={entry.id} style={{flexDirection:"row",justifyContent:"space-between",paddingVertical:10,borderBottomWidth:1,borderBottomColor:colors.border}}>
      <Muted>{dateLabel(entry.measured_on)}</Muted><Text style={{color:colors.text,fontWeight:"800"}}>{entry.weight_kg.toFixed(1)} kg</Text>
    </View>):<Muted>Cuando registres tu peso, aquí tendrás un historial para observar tendencias.</Muted>}</Panel>
    <AppButton title="Actualizar historial" onPress={()=>void load()} variant="quiet"/>
  </Screen>;
}