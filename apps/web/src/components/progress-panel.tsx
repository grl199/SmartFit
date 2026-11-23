"use client";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { apiRequest } from "@/lib/api";
type Props={token:string};
type Targets={kcal:number;protein_g:number;carbs_g:number;fat_g:number;fiber_g:number;workouts_per_week:number;water_ml?:number;steps_goal?:number};
type Day={log_date:string;kcal:number;protein_g:number;carbs_g:number;fat_g:number;fiber_g:number};
type Weight={id:number;measured_on:string;weight_kg:number;body_fat_pct?:number|null};
type Workout={id:number;performed_on:string;kind:string;category?:string|null;duration_min:number;kcal_burned?:number|null;distance_km?:number|null};
type Insights={period:{days:number;start:string;end:string;prev_start:string;prev_end:string};enough_data:boolean;nutrition:any;training:any;activity:any;wellbeing:any;achievements:string[];pending:string[];summary:string;ai_summary?:string|null;note:string};
const fmt=(n:number|null|undefined,d=0)=>n==null?"—":n.toLocaleString("es-ES",{maximumFractionDigits:d});
const err=(e:unknown)=>e instanceof Error?e.message:"No se pudo completar la operación.";

export function ProgressPanel({token}:Props){
 const [period,setPeriod]=useState("30"),[targets,setTargets]=useState<Targets|null>(null),[days,setDays]=useState<Day[]>([]),[weights,setWeights]=useState<Weight[]>([]),[workouts,setWorkouts]=useState<Workout[]>([]);
 const [water,setWater]=useState<any>(null),[activity,setActivity]=useState<any>(null),[checkins,setCheckins]=useState<any[]>([]),[insights,setInsights]=useState<Insights|null>(null),[ai,setAi]=useState(false);
 const [weight,setWeight]=useState(""),[bodyFat,setBodyFat]=useState(""),[weightDate,setWeightDate]=useState(new Date().toLocaleDateString("sv-SE"));
 const [busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
 async function load(){
  const d=Number(period);
  const [range,w,ws,wa,ac,ci,ins]=await Promise.all([
   apiRequest<{targets:Targets;days:Day[]}>("/dashboard/range?days="+d,{token}),
   apiRequest<Weight[]>("/metrics/weight?days=365",{token}),
   apiRequest<Workout[]>("/workouts?days="+d,{token}),
   apiRequest<any>("/water/summary?days="+d,{token}),
   apiRequest<any>("/activity/summary?days="+d,{token}),
   apiRequest<any[]>("/checkins?days="+d,{token}),
   apiRequest<Insights>("/progress/insights?days="+d+"&ai="+String(ai),{token}),
  ]);
  setTargets(range.targets);setDays(range.days);setWeights(w);setWorkouts(ws);setWater(wa);setActivity(ac);setCheckins(ci);setInsights(ins);
 }
 useEffect(()=>{setError("");load().catch(e=>setError(err(e)));},[token,period,ai]);
 async function analyze(){setBusy(true);setError("");try{setInsights(await apiRequest<Insights>("/progress/insights?days="+period+"&ai="+String(ai),{token}));}catch(e){setError(err(e));}finally{setBusy(false);}}
 async function saveWeight(e:FormEvent){e.preventDefault();setBusy(true);setError("");try{await apiRequest("/metrics/weight",{method:"POST",token,body:{weight_kg:Number(weight),body_fat_pct:bodyFat?Number(bodyFat):null,measured_on:weightDate}});setWeight("");setBodyFat("");await load();setNotice("Medición guardada.");}catch(x){setError(err(x));}finally{setBusy(false);}}
 const maxKcal=Math.max(targets?.kcal||0,...days.map(x=>x.kcal),1);
 const recentWeights=weights.slice(-12);
 const weightRange=recentWeights.length?Math.max(...recentWeights.map(x=>x.weight_kg))-Math.min(...recentWeights.map(x=>x.weight_kg)):1;
 return <div className="progress-workspace">
  <div className="module-heading"><div><span className="eyebrow">PROGRESO</span><h2>Tu evolución, con perspectiva</h2><p className="muted">Nutrición, entrenamiento, peso y hábitos en un solo lugar</p></div><label className="date-control">Periodo<select value={period} onChange={e=>setPeriod(e.target.value)}><option value="7">7 días</option><option value="14">14 días</option><option value="30">30 días</option><option value="90">90 días</option></select></label></div>
  {error&&<div className="dashboard-alert">{error}<button type="button" onClick={()=>setError("")}>Cerrar</button></div>}{notice&&<div className="nutrition-notice">{notice}<button type="button" onClick={()=>setNotice("")}>×</button></div>}
  <section className="progress-kpi-grid">
   <article className="panel"><span>Media de calorías</span><strong>{fmt(days.length?days.reduce((s,x)=>s+x.kcal,0)/days.length:null)} kcal</strong><small>Objetivo {fmt(targets?.kcal)} · {days.length} días registrados</small></article>
   <article className="panel"><span>Proteína media</span><strong>{fmt(days.length?days.reduce((s,x)=>s+x.protein_g,0)/days.length:null,1)} g</strong><small>Objetivo {fmt(targets?.protein_g)} g</small></article>
   <article className="panel"><span>Entrenamientos</span><strong>{workouts.length}</strong><small>Objetivo semanal {targets?.workouts_per_week??"—"}</small></article>
   <article className="panel"><span>Peso actual</span><strong>{weights.length?fmt(weights[weights.length-1].weight_kg,1)+" kg":"—"}</strong><small>{weights.length?weights[weights.length-1].measured_on:"Sin mediciones"}</small></article>
  </section>
  <section className="panel"><div className="list-heading"><div><h3>Calorías registradas</h3><p className="muted">Solo aparecen días con registros; un día vacío no equivale a 0 kcal.</p></div><span className="count-chip">Objetivo {fmt(targets?.kcal)} kcal</span></div>
   <div className="progress-bars">{days.map(item=><div key={item.log_date} title={item.log_date+": "+fmt(item.kcal)+" kcal"}><span style={{height:Math.max(3,Math.min(100,item.kcal/maxKcal*100))+"%"}}/><small>{item.log_date.slice(8)}</small></div>)}</div>
   {!!days.length&&<div className="progress-macro-totals"><span>Proteína media <strong>{fmt(days.reduce((s,x)=>s+x.protein_g,0)/days.length,1)} g</strong></span><span>Hidratos <strong>{fmt(days.reduce((s,x)=>s+x.carbs_g,0)/days.length,1)} g</strong></span><span>Grasas <strong>{fmt(days.reduce((s,x)=>s+x.fat_g,0)/days.length,1)} g</strong></span></div>}
  </section>
  <div className="progress-two-col">
   <section className="panel"><div className="list-heading"><div><h3>Composición corporal</h3><p className="muted">Historial de peso y porcentaje graso</p></div></div>
    <form className="stack-form" onSubmit={saveWeight}><div className="nutrition-log-controls"><label>Fecha<input type="date" max={new Date().toLocaleDateString("sv-SE")} value={weightDate} onChange={e=>setWeightDate(e.target.value)}/></label><label>Peso (kg)<input required type="number" min="20" max="400" step=".1" value={weight} onChange={e=>setWeight(e.target.value)}/></label></div><label>Grasa corporal (%)<input type="number" min="1" max="70" step=".1" value={bodyFat} onChange={e=>setBodyFat(e.target.value)}/></label><button className="primary-button compact" disabled={busy}>Guardar medición</button></form>
    {recentWeights.length>0&&<div className="progress-weight-list">{recentWeights.slice().reverse().map(item=><div key={item.id}><span>{item.measured_on}</span><strong>{fmt(item.weight_kg,1)} kg</strong><small>{item.body_fat_pct==null?"Sin % graso":fmt(item.body_fat_pct,1)+" % grasa"}</small></div>)}</div>}
   </section>
   <section className="panel"><h3>Entrenamiento en el periodo</h3><div className="progress-training-stats"><div><span>Tiempo total</span><strong>{fmt(workouts.reduce((s,x)=>s+x.duration_min,0)/60,1)} h</strong></div><div><span>Distancia</span><strong>{fmt(workouts.reduce((s,x)=>s+(x.distance_km||0),0),1)} km</strong></div><div><span>Kcal estimadas</span><strong>{fmt(workouts.reduce((s,x)=>s+(x.kcal_burned||0),0))}</strong></div></div>
    <div className="progress-workout-list">{workouts.slice(0,8).map(item=><div key={item.id}><strong>{item.kind}</strong><span>{item.performed_on} · {item.duration_min} min{item.distance_km?" · "+fmt(item.distance_km,1)+" km":""}</span></div>)}</div>
   </section>
  </div>
  <section className="panel"><div className="list-heading"><div><h3>Análisis del progreso</h3><p className="muted">Compara este periodo con los {period} días anteriores.</p></div><button type="button" className="primary-button compact" disabled={busy} onClick={()=>void analyze()}>{busy?"Analizando…":"Analizar"}</button></div>
   <label className="nutrition-toggle"><input type="checkbox" checked={ai} onChange={e=>setAi(e.target.checked)}/> Permitir que la IA redacte el resumen a partir de los indicadores calculados</label>
   <p className="progress-summary">{insights?.ai_summary||insights?.summary||"Cargando análisis…"}</p>{insights?.enough_data===false&&<p className="muted">Aún no hay datos suficientes para conclusiones fiables.</p>}
   <div className="progress-achievements-grid"><div><h4>Logros</h4>{insights?.achievements?.length?insights.achievements.map((x,i)=><p className="progress-good" key={i}>✓ {x}</p>):<p className="muted">Todavía no hay logros calculados.</p>}</div><div><h4>Aspectos a mejorar</h4>{insights?.pending?.length?insights.pending.map((x,i)=><p className="progress-pending" key={i}>• {x}</p>):<p className="muted">Sin pendientes calculados.</p>}</div></div>
   {insights?.training?.personal_records?.length>0&&<div className="progress-personal-records"><strong>Récords personales</strong>{insights.training.personal_records.map((x:any,i:number)=><span key={i}>{x.exercise}: {fmt(x.weight_kg,1)} kg (anterior {fmt(x.previous_best_kg,1)} kg)</span>)}</div>}
   <p className="muted">{insights?.note}</p>
  </section>
  <section className="progress-habits-strip"><article className="panel"><h3>Hidratación</h3><strong>{fmt(water?.avg_ml)} ml/día</strong><p className="muted">Objetivo {fmt(water?.goal_ml)} ml · cumplido {water?.days_goal_met??0} días</p></article><article className="panel"><h3>Actividad</h3><strong>{fmt(activity?.avg_steps)} pasos/día</strong><p className="muted">Objetivo {fmt(activity?.goal)} · alcanzado {activity?.days_goal_met??0} días</p></article><article className="panel"><h3>Bienestar</h3><strong>{checkins.length} check-ins</strong><p className="muted">Ánimo medio {fmt(checkins.length?checkins.reduce((s,x)=>s+x.mood,0)/checkins.length:null,1)}/5. Las notas privadas no se incluyen.</p></article></section>
 </div>;
}
