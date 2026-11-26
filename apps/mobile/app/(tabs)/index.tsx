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
  const mealDefinitions = [
    { key: "breakfast", label: "Desayuno", icon: "☀️", color: colors.blue },
    { key: "mid_morning", label: "Almuerzo", icon: "🍎", color: colors.orange },
    { key: "lunch", label: "Comida", icon: "🍽️", color: colors.accent },
    { key: "snack", label: "Merienda", icon: "☕", color: colors.danger },
    { key: "dinner", label: "Cena", icon: "🌙", color: colors.muted },
  ];
  const mealValues = mealDefinitions.map(meal => ({
    ...meal,
    kcal: data?.entries.filter(entry => entry.meal === meal.key).reduce((sum, entry) => sum + entry.kcal, 0) ?? 0,
    protein_g: data?.entries.filter(entry => entry.meal === meal.key).reduce((sum, entry) => sum + entry.protein_g, 0) ?? 0,
    carbs_g: data?.entries.filter(entry => entry.meal === meal.key).reduce((sum, entry) => sum + entry.carbs_g, 0) ?? 0,
    sugars_g: data?.entries.filter(entry => entry.meal === meal.key).reduce((sum, entry) => sum + entry.sugars_g, 0) ?? 0,
    fat_g: data?.entries.filter(entry => entry.meal === meal.key).reduce((sum, entry) => sum + entry.fat_g, 0) ?? 0,
    sat_fat_g: data?.entries.filter(entry => entry.meal === meal.key).reduce((sum, entry) => sum + entry.sat_fat_g, 0) ?? 0,
    fiber_g: data?.entries.filter(entry => entry.meal === meal.key).reduce((sum, entry) => sum + entry.fiber_g, 0) ?? 0,
    sodium_mg: data?.entries.filter(entry => entry.meal === meal.key).reduce((sum, entry) => sum + entry.sodium_mg, 0) ?? 0,
  }));
  const kcalGoal = Number(target?.kcal) > 0 ? Number(target?.kcal) : 2500;
  const contributionRows = [
    { key: "kcal" as const, label: "Energía", unit: "kcal", goal: kcalGoal, kind: "goal" as const, note: "Objetivo diario personalizado" },
    { key: "protein_g" as const, label: "Proteína", unit: "g", goal: Number(target?.protein_g) > 0 ? Number(target?.protein_g) : kcalGoal * .15 / 4, kind: "goal" as const, note: "Objetivo diario o referencia provisional del 15 % de la energía" },
    { key: "carbs_g" as const, label: "Hidratos", unit: "g", goal: Number(target?.carbs_g) > 0 ? Number(target?.carbs_g) : kcalGoal * .55 / 4, kind: "goal" as const, note: "Objetivo diario o referencia provisional del 55 % de la energía" },
    { key: "sugars_g" as const, label: "Azúcares", unit: "g", goal: kcalGoal * .1 / 4, kind: "limit" as const, note: "Referencia del 10 % de la energía; el diario registra azúcares totales, no distingue los libres" },
    { key: "fat_g" as const, label: "Grasas", unit: "g", goal: Number(target?.fat_g) > 0 ? Number(target?.fat_g) : kcalGoal * .3 / 9, kind: "goal" as const, note: "Objetivo diario o referencia provisional del 30 % de la energía" },
    { key: "sat_fat_g" as const, label: "Grasas saturadas", unit: "g", goal: kcalGoal * .1 / 9, kind: "limit" as const, note: "Límite orientativo inferior al 10 % de la energía" },
    { key: "fiber_g" as const, label: "Fibra", unit: "g", goal: Number(target?.fiber_g) > 0 ? Number(target?.fiber_g) : 25, kind: "minimum" as const, note: "Referencia mínima orientativa para adultos" },
    { key: "sodium_mg" as const, label: "Sodio", unit: "mg", goal: 2000, kind: "limit" as const, note: "Referencia de 2.000 mg al día" },
  ].map(row => {
    const valueForMeal = (meal: typeof mealValues[number]) => {
      const value = Math.max(0, Number(meal[row.key] || 0));
      return row.key === "sodium_mg" && value > 10000 ? value / 1000 : value;
    };
    const total = mealValues.reduce((sum, meal) => sum + valueForMeal(meal), 0);
    const visualMax = Math.max(row.goal * 1.18, total * 1.08, 1);
    const status = row.kind === "minimum"
      ? (total >= row.goal ? "Mínimo alcanzado" : "Faltan " + (row.goal-total).toLocaleString("es-ES",{maximumFractionDigits:1}) + " " + row.unit)
      : row.kind === "limit"
        ? (total > row.goal ? "Exceso de " + (total-row.goal).toLocaleString("es-ES",{maximumFractionDigits:1}) + " " + row.unit : "Dentro del límite · margen " + (row.goal-total).toLocaleString("es-ES",{maximumFractionDigits:1}) + " " + row.unit)
        : (total > row.goal ? "Por encima del objetivo · +" + (total-row.goal).toLocaleString("es-ES",{maximumFractionDigits:1}) + " " + row.unit : "Restan " + (row.goal-total).toLocaleString("es-ES",{maximumFractionDigits:1}) + " " + row.unit);
    return { ...row, total, visualMax, marker: Math.min(100, row.goal / visualMax * 100), status, valueForMeal };
  });
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
    <SectionTitle title="Contribución de cada comida"/>
    <Panel>
      <Muted>Cómo se reparte tu ingesta entre las comidas del día. La línea marca el objetivo nutricional.</Muted>
      <View style={{flexDirection:"row",flexWrap:"wrap",gap:10}}>
        {mealDefinitions.map(meal=><View key={meal.key} style={{flexDirection:"row",alignItems:"center",gap:5}}>
          <View style={{width:9,height:9,borderRadius:3,backgroundColor:meal.color}}/>
          <Muted>{meal.icon} {meal.label}</Muted>
        </View>)}
      </View>
      {contributionRows.map(row=><View key={row.key} style={{gap:5}}>
        <View style={{flexDirection:"row",justifyContent:"space-between",alignItems:"baseline"}}>
          <Text style={{color:colors.text,fontWeight:"800",fontSize:12}}>{row.label}</Text>
          <Muted>{row.total.toLocaleString("es-ES",{maximumFractionDigits:1})} / {row.goal.toLocaleString("es-ES",{maximumFractionDigits:1})} {row.unit} · {(row.total/row.goal*100).toLocaleString("es-ES",{maximumFractionDigits:0})}%</Muted>
        </View>
        <View style={{height:13,borderRadius:8,backgroundColor:colors.surfaceRaised,overflow:"hidden",flexDirection:"row",position:"relative"}}>
          {mealValues.map(meal=>row.valueForMeal(meal)>0?<View key={meal.key} style={{height:13,width:(row.valueForMeal(meal)/row.visualMax*100)+"%",backgroundColor:meal.color}}/>:null)}
          <View style={{position:"absolute",left:row.marker+"%",top:0,bottom:0,width:2,backgroundColor:colors.text}}/>
        </View>
        <Muted>{row.status} · {row.note}</Muted>
      </View>)}
      <Muted>Las referencias son orientativas, no sustituyen una pauta individual. SmartFit registra azúcares totales y no distingue los azúcares libres. Los límites de sodio y grasas saturadas son informativos.</Muted>
    </Panel>
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