import React,{useCallback,useEffect,useState} from "react";
import {ActivityIndicator,Text,View} from "react-native";
import {api,type DashboardDay} from "@/lib/api";
import {localDateISO,formatKcal,clampPercent} from "@/lib/format";
import {useAuth} from "@/auth/AuthProvider";
import {AppButton,Muted,PageTitle,Panel,ProgressBar,Screen,SectionTitle} from "@/components/ui";
import {colors} from "@/theme";
export default function DashboardScreen() {
  const {user,token}=useAuth();
  const [data,setData]=useState<DashboardDay|null>(null);
  const [loading,setLoading]=useState(true);
  const [refreshing,setRefreshing]=useState(false);
  const [error,setError]=useState("");
  const load=useCallback(async()=>{
    if(!token)return;
    try { setError(""); setData(await api<DashboardDay>("/dashboard/day?date="+localDateISO(),token)); }
    catch(e){setError(e instanceof Error?e.message:"No se pudo cargar tu resumen.");}
    finally{setLoading(false);setRefreshing(false);}
  },[token]);
  useEffect(()=>{void load();},[load]);
  async function addWater(){
    if(!token)return;
    try{await api("/habits/water",token,{method:"POST",body:{quantity_ml:250,source:"quick"}});await load();}
    catch(e){setError(e instanceof Error?e.message:"No se pudo registrar el agua.");}
  }
  const totals=data?.totals,target=data?.targets;
  return <Screen>
    <View style={{flexDirection:"row",justifyContent:"space-between",alignItems:"center"}}>
      <View><Text style={{color:colors.accent,fontSize:11,fontWeight:"900",letterSpacing:1.4}}>SMARTFIT</Text><Text style={{color:colors.text,fontSize:14,fontWeight:"700",marginTop:4}}>Hola, {user?.name}</Text></View>
      <View style={{backgroundColor:colors.accentDark,paddingHorizontal:13,paddingVertical:8,borderRadius:20}}><Text style={{color:colors.accent,fontSize:12,fontWeight:"800"}}>TU DÍA</Text></View>
    </View>
    <PageTitle title="Hoy cuenta." subtitle="Pequeñas decisiones, progreso que se acumula." />
    {loading?<ActivityIndicator color={colors.accent}/>:null}
    {error?<Text style={{color:colors.danger}}>{error}</Text>:null}
    <Panel style={{backgroundColor:colors.accentDark,borderColor:"#465D2C",padding:20}}>
      <Text style={{color:colors.accent,fontSize:12,fontWeight:"800"}}>ENERGÍA CONSUMIDA</Text>
      <View style={{flexDirection:"row",alignItems:"baseline",gap:7,marginTop:5}}>
        <Text style={{color:colors.text,fontSize:39,fontWeight:"900"}}>{formatKcal(totals?.kcal)}</Text>
        <Text style={{color:colors.muted,fontSize:13}}>/ {formatKcal(target?.kcal)} kcal</Text>
      </View>
      <ProgressBar value={clampPercent(totals?.kcal??0,target?.kcal??0)}/>
      <Text style={{color:colors.muted,fontSize:12}}>{Math.max(0,Math.round((target?.kcal??0)-(totals?.kcal??0))).toLocaleString("es-ES")} kcal para tu objetivo diario</Text>
    </Panel>
    <SectionTitle title="Macros de hoy"/>
    <View style={{flexDirection:"row",gap:9}}>
      {[
        {label:"Proteína",amount:totals?.protein_g,target:target?.protein_g,color:colors.blue},
        {label:"Carbohidratos",amount:totals?.carbs_g,target:target?.carbs_g,color:colors.orange},
        {label:"Grasas",amount:totals?.fat_g,target:target?.fat_g,color:colors.accent}
      ].map(item=><Panel key={item.label} style={{flex:1,padding:12}}>
        <Text style={{color:colors.muted,fontSize:10,fontWeight:"700"}}>{item.label}</Text>
        <Text style={{color:colors.text,fontSize:20,fontWeight:"900",marginTop:5}}>{Math.round(item.amount??0)}g</Text>
        <Muted>/ {Math.round(item.target??0)}g</Muted>
        <ProgressBar value={clampPercent(item.amount??0,item.target??0)} color={item.color}/>
      </Panel>)}
    </View>
    <SectionTitle title="Hidratación"/>
    <Panel>
      <View style={{flexDirection:"row",justifyContent:"space-between",alignItems:"baseline"}}>
        <Text style={{color:colors.text,fontSize:24,fontWeight:"900"}}>{((data?.water_ml??0)/1000).toFixed(2)} L</Text>
        <Muted>Objetivo {((target?.water_ml??2000)/1000).toFixed(1)} L</Muted>
      </View>
      <ProgressBar value={clampPercent(data?.water_ml??0,target?.water_ml??2000)} color={colors.blue}/>
      <AppButton title="+ 250 ml de agua" variant="secondary" onPress={()=>void addWater()}/>
    </Panel>
    <SectionTitle title="Actividad de hoy" action={(data?.workouts?.length??0)+" sesiones"}/>
    <Panel>{(data?.workouts?.length??0)===0?<Muted>Aún no hay entrenamientos registrados hoy. Tu siguiente sesión puede ser un buen comienzo.</Muted>:
      data?.workouts.map((workout,index)=><View key={workout.id??index} style={{gap:4}}>
        <Text style={{color:colors.text,fontWeight:"800"}}>{workout.kind}</Text><Muted>{workout.duration_min} min · {Math.round(workout.kcal_burned??0)} kcal</Muted>
      </View>)}</Panel>
    <AppButton title="Actualizar resumen" variant="quiet" onPress={()=>{setRefreshing(true);void load();}} loading={refreshing}/>
  </Screen>;
}