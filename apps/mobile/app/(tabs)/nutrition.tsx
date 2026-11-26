import React,{useCallback,useEffect,useState} from "react";
import {Pressable,Text,View} from "react-native";
import {api,type DashboardDay,type FoodSearchResult} from "@/lib/api";
import {localDateISO,formatKcal,clampPercent} from "@/lib/format";
import {useAuth} from "@/auth/AuthProvider";
import {AppButton,ErrorMessage,Field,Muted,PageTitle,Panel,ProgressBar,Screen,SectionTitle} from "@/components/ui";
import {colors} from "@/theme";
export default function NutritionScreen(){
  const {token}=useAuth();
  const [data,setData]=useState<DashboardDay|null>(null);
  const [query,setQuery]=useState("");
  const [results,setResults]=useState<FoodSearchResult[]>([]);
  const [grams,setGrams]=useState("100");
  const [meal,setMeal]=useState<"breakfast"|"mid_morning"|"lunch"|"snack"|"dinner">("lunch");
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState("");
  const load=useCallback(async()=>{
    if(!token)return;
    try{setData(await api<DashboardDay>("/dashboard/day?date="+localDateISO(),token));}
    catch(e){setError(e instanceof Error?e.message:"No se pudo cargar la nutrición.");}
  },[token]);
  useEffect(()=>{void load();},[load]);
  async function search(){
    if(!token||!query.trim())return;
    setLoading(true);setError("");
    try{
      const found=await api<FoodSearchResult[]>("/foods/search?q="+encodeURIComponent(query.trim())+"&limit=8&online=false",token);
      setResults(found);if(found.length===0)setError("No encontramos alimentos con ese nombre.");
    }catch(e){setError(e instanceof Error?e.message:"Falló la búsqueda.");}
    finally{setLoading(false);}
  }
  async function addFood(food:FoodSearchResult){
    if(!token)return;
    const quantity=Number(grams.replace(",",".")); 
    if(!Number.isFinite(quantity)||quantity<=0||quantity>5000){setError("Introduce una cantidad entre 1 y 5000 gramos.");return;}
    setLoading(true);setError("");
    try{
      await api("/logs",token,{method:"POST",body:{food_id:food.id,grams:quantity,meal}});
      setResults([]);setQuery("");await load();
    }catch(e){setError(e instanceof Error?e.message:"No se pudo guardar la ingesta.");}
    finally{setLoading(false);}
  }
  const totals=data?.totals,target=data?.targets;
  const meals=[{value:"breakfast",label:"Desayuno"},{value:"mid_morning",label:"Media mañana"},{value:"lunch",label:"Comida"},{value:"snack",label:"Merienda"},{value:"dinner",label:"Cena"}] as const;
  return <Screen>
    <PageTitle eyebrow="Nutrición" title="Alimenta tu progreso" subtitle="Registra lo que comes y mantén tus objetivos a la vista."/>
    <Panel>
      <View style={{flexDirection:"row",justifyContent:"space-between",alignItems:"baseline"}}>
        <Text style={{color:colors.text,fontSize:26,fontWeight:"900"}}>{formatKcal(totals?.kcal)} kcal</Text><Muted>de {formatKcal(target?.kcal)} kcal</Muted>
      </View>
      <ProgressBar value={clampPercent(totals?.kcal??0,target?.kcal??0)}/>
      <View style={{flexDirection:"row",justifyContent:"space-between",marginTop:5}}>
        <Muted>Proteína {Math.round(totals?.protein_g??0)} g</Muted><Muted>Carbos {Math.round(totals?.carbs_g??0)} g</Muted><Muted>Grasas {Math.round(totals?.fat_g??0)} g</Muted>
      </View>
    </Panel>
    <SectionTitle title="Añadir alimento"/>
    <Panel>
      <Field label="Buscar en el catálogo" value={query} onChangeText={setQuery} placeholder="Ej. avena, plátano, yogur..." returnKeyType="search" onSubmitEditing={()=>void search()}/>
      <Field label="Cantidad (g)" value={grams} onChangeText={setGrams} keyboardType="decimal-pad"/>
      <View style={{flexDirection:"row",flexWrap:"wrap",gap:7}}>
        {meals.map(item=><Pressable key={item.value} onPress={()=>setMeal(item.value)} style={{borderRadius:12,paddingVertical:9,paddingHorizontal:11,backgroundColor:meal===item.value?colors.accentDark:colors.surfaceRaised,borderWidth:1,borderColor:meal===item.value?colors.accent:colors.border}}>
          <Text style={{color:meal===item.value?colors.accent:colors.muted,fontWeight:"700",fontSize:11}}>{item.label}</Text>
        </Pressable>)}
      </View>
      <AppButton title="Buscar alimentos" onPress={()=>void search()} loading={loading} disabled={!query.trim()}/>
      <ErrorMessage message={error}/>
      {results.map(food=><Pressable key={food.id} onPress={()=>void addFood(food)} style={{borderTopWidth:1,borderColor:colors.border,paddingTop:12,gap:4}}>
        <Text style={{color:colors.text,fontWeight:"800"}}>{food.name}</Text>
        <Muted>{food.brand?food.brand+" · ":""}{Math.round(food.kcal)} kcal / 100 g · {Math.round(food.protein_g)} g proteína</Muted>
        <Text style={{color:colors.accent,fontWeight:"800",fontSize:12}}>Añadir {grams} g</Text>
      </Pressable>)}
    </Panel>
    <SectionTitle title="Comidas registradas" action={(data?.entries?.length??0)+" registros"}/>
    <Panel>{data?.entries?.length?data.entries.map(entry=><View key={entry.id} style={{paddingVertical:7,borderBottomWidth:1,borderBottomColor:colors.border,gap:3}}>
      <View style={{flexDirection:"row",justifyContent:"space-between"}}><Text style={{color:colors.text,fontWeight:"700",flex:1}}>{entry.food}</Text><Text style={{color:colors.accent,fontWeight:"800"}}>{Math.round(entry.kcal)} kcal</Text></View>
      <Muted>{entry.time} · {entry.grams} g · {entry.meal}</Muted>
    </View>):<Muted>Todavía no has registrado ninguna comida hoy.</Muted>}</Panel>
    <AppButton title="Actualizar resumen" variant="quiet" onPress={()=>void load()}/>
  </Screen>;
}