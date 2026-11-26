import React,{useCallback,useEffect,useState} from "react";
import {ActivityIndicator,Text,View} from "react-native";
import {api,type WorkoutSummary} from "@/lib/api";
import {dateLabel} from "@/lib/format";
import {useAuth} from "@/auth/AuthProvider";
import {AppButton,ErrorMessage,Muted,PageTitle,Panel,Screen,SectionTitle} from "@/components/ui";
import {colors} from "@/theme";
type PlanResponse={has_plan:boolean;legacy_markdown?:string|null;plan?:{name?:string|null;days?:unknown[]}|null};
export default function TrainingScreen(){
  const {token}=useAuth();
  const [plan,setPlan]=useState<PlanResponse|null>(null);
  const [workouts,setWorkouts]=useState<WorkoutSummary[]>([]);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const load=useCallback(async()=>{
    if(!token)return;
    try{
      setError("");
      const [p,w]=await Promise.all([api<PlanResponse>("/plan",token),api<WorkoutSummary[]>("/workouts?days=30",token)]);
      setPlan(p);setWorkouts(w);
    }catch(e){setError(e instanceof Error?e.message:"No se pudo cargar tu entrenamiento.");}
    finally{setLoading(false);}
  },[token]);
  useEffect(()=>{void load();},[load]);
  async function logWorkout(){
    if(!token)return;
    setBusy(true);setError("");
    try{
      await api("/workouts",token,{method:"POST",body:{kind:"Sesión rápida",category:"strength",duration_min:30,sets:[],estimate_calories:true}});
      await load();
    }catch(e){setError(e instanceof Error?e.message:"No se pudo registrar la sesión.");}
    finally{setBusy(false);}
  }
  return <Screen>
    <PageTitle eyebrow="Entrenamiento" title="Fuerte y constante" subtitle="Consulta tu plan y lleva el registro de cada sesión."/>
    <Panel style={{backgroundColor:colors.accentDark,borderColor:"#465D2C"}}>
      <Text style={{color:colors.accent,fontWeight:"800",fontSize:11}}>TU PLAN ACTUAL</Text>
      <Text style={{color:colors.text,fontSize:20,fontWeight:"900"}}>{plan?.has_plan?(plan.plan?.name??"Plan personalizado"):"Prepara tu plan"}</Text>
      <Muted>{plan?.has_plan?"Tu planificación está guardada en SmartFit.":"Genera un plan personalizado desde la versión web y aparecerá aquí."}</Muted>
      {plan?.legacy_markdown?<Text numberOfLines={5} style={{color:colors.muted,lineHeight:19,fontSize:12}}>{plan.legacy_markdown}</Text>:null}
    </Panel>
    <View style={{gap:9}}>
      <AppButton title="Registrar sesión rápida · 30 min" onPress={()=>void logWorkout()} loading={busy}/>
      <AppButton title="Actualizar entrenamientos" variant="quiet" onPress={()=>void load()}/>
    </View>
    <ErrorMessage message={error}/>
    <SectionTitle title="Últimas sesiones" action="Últimos 30 días"/>
    {loading?<ActivityIndicator color={colors.accent}/>:null}
    {workouts.length===0?<Panel><Muted>Aún no hay sesiones registradas. Cuando termines de entrenar, registra tu actividad.</Muted></Panel>:
      workouts.map(workout=><Panel key={workout.id}>
        <View style={{flexDirection:"row",justifyContent:"space-between",alignItems:"center"}}>
          <Text style={{color:colors.text,fontSize:16,fontWeight:"800",flex:1}}>{workout.kind}</Text>
          <Text style={{color:colors.accent,fontWeight:"800"}}>{workout.duration_min} min</Text>
        </View>
        <Muted>{dateLabel(workout.performed_on)} · {Math.round(workout.kcal_burned??0)} kcal</Muted>
      </Panel>)}
  </Screen>;
}