"use client";
import { FormEvent, useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";

type Props={token:string;date:string;onDateChange:(value:string)=>void};
type Targets={kcal:number;protein_g:number;carbs_g:number;fat_g:number;fiber_g:number;workouts_per_week:number;water_ml?:number;steps_goal?:number};
type WaterLog={id:number;logged_at:string;quantity_ml:number;source:string};
type WaterSummary={goal_ml:number;today_ml:number;today_pct:number;avg_ml:number|null;days_logged:number;days_goal_met:number;days:Array<{date:string;ml:number;pct:number}>};
type ActivitySummary={goal:number;today_steps:number|null;today_pct:number|null;avg_steps:number|null;days_recorded:number;days_goal_met:number;days:Array<{date:string;steps:number|null}>};
type ActivityDay={date:string;steps:number|null;distance_km?:number|null;active_calories?:number|null;source?:string;sources?:string[]};
type Checkin={date:string;mood:number;energy_level?:number|null;stress_level?:number|null;sleep_quality?:number|null;notes?:string|null};
type Connection={provider:string;label:string;mode:"pull"|"push";configured:boolean;note:string;connected:boolean;consented_at?:string|null};
const fmt=(n:number|null|undefined,d=0)=>n==null?"—":n.toLocaleString("es-ES",{maximumFractionDigits:d});
const errorText=(e:unknown)=>e instanceof Error?e.message:"No se pudo completar la operación.";
const scores=["Muy bajo","Bajo","Normal","Bien","Muy bien"];

export function HabitsPanel({token,date,onDateChange}:Props){
 const [targets,setTargets]=useState<Targets|null>(null),[water,setWater]=useState<WaterSummary|null>(null),[waterLogs,setWaterLogs]=useState<WaterLog[]>([]),[waterAmount,setWaterAmount]=useState("250"),[waterGoal,setWaterGoal]=useState("2000");
 const [activity,setActivity]=useState<ActivitySummary|null>(null),[activityDays,setActivityDays]=useState<ActivityDay[]>([]),[steps,setSteps]=useState(""),[distance,setDistance]=useState("");
 const [checkins,setCheckins]=useState<Checkin[]>([]),[mood,setMood]=useState("3"),[energy,setEnergy]=useState("3"),[stress,setStress]=useState("3"),[sleep,setSleep]=useState("3"),[notes,setNotes]=useState("");
 const [connections,setConnections]=useState<Connection[]>([]),[deleteImported,setDeleteImported]=useState<Record<string,boolean>>({});
 const [busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");

 async function loadAll(){
  const [t,w,a,ad,c,co]=await Promise.all([
   apiRequest<Targets>("/targets",{token}),apiRequest<WaterSummary>("/water/summary?days=14",{token}),
   apiRequest<ActivitySummary>("/activity/summary?days=14",{token}),apiRequest<ActivityDay[]>("/activity?days=30",{token}),
   apiRequest<Checkin[]>("/checkins?days=120",{token}),apiRequest<Connection[]>("/activity/connections",{token}),
  ]);
  setTargets(t);setWater(w);setWaterGoal(String(t.water_ml||w.goal_ml||2000));setActivity(a);setActivityDays(ad);setCheckins(c);setConnections(co);
 }
 async function loadDate(){const [logs,c]=await Promise.all([apiRequest<WaterLog[]>("/water?date="+date,{token}),apiRequest<Checkin[]>("/checkins?days=120",{token})]);setWaterLogs(logs);const current=c.find(x=>x.date===date);setMood(String(current?.mood??3));setEnergy(String(current?.energy_level??3));setStress(String(current?.stress_level??3));setSleep(String(current?.sleep_quality??3));setNotes(current?.notes??"");setCheckins(c);}
 useEffect(()=>{loadAll().catch(e=>setError(errorText(e)));},[token]);
 useEffect(()=>{loadDate().catch(e=>setError(errorText(e)));},[token,date]);
 async function addWater(e:FormEvent){e.preventDefault();setBusy(true);setError("");try{await apiRequest("/water",{method:"POST",token,body:{quantity_ml:Number(waterAmount),log_date:date,source:"manual"}});setNotice("Agua registrada.");await Promise.all([loadAll(),loadDate()]);}catch(x){setError(errorText(x));}finally{setBusy(false);}}
 async function deleteWater(item:WaterLog){try{await apiRequest("/water/"+item.id,{method:"DELETE",token});await Promise.all([loadAll(),loadDate()]);}catch(x){setError(errorText(x));}}
 async function saveWaterGoal(e:FormEvent){e.preventDefault();if(!targets)return;setBusy(true);try{await apiRequest("/targets",{method:"PUT",token,body:{...targets,water_ml:Number(waterGoal)}});await loadAll();setNotice("Objetivo de hidratación actualizado.");}catch(x){setError(errorText(x));}finally{setBusy(false);}}
 async function saveCheckin(e:FormEvent){e.preventDefault();setBusy(true);setError("");try{await apiRequest("/checkins/"+date,{method:"PUT",token,body:{mood:Number(mood),energy_level:Number(energy),stress_level:Number(stress),sleep_quality:Number(sleep),notes:notes.trim()||null}});await loadDate();setNotice("Check-in guardado. Tus notas permanecen privadas.");}catch(x){setError(errorText(x));}finally{setBusy(false);}}
 async function deleteCheckin(){if(!window.confirm("¿Eliminar el check-in de este día?"))return;try{await apiRequest("/checkins/"+date,{method:"DELETE",token});await loadDate();setNotice("Check-in eliminado.");}catch(x){setError(errorText(x));}}
 async function saveActivity(e:FormEvent){e.preventDefault();setBusy(true);setError("");try{await apiRequest("/activity",{method:"PUT",token,body:{activity_date:date,steps:Number(steps),distance_km:distance?Number(distance):null}});setSteps("");setDistance("");await loadAll();setNotice("Actividad registrada para el día seleccionado.");}catch(x){setError(errorText(x));}finally{setBusy(false);}}
 async function connect(provider:string){setBusy(true);try{await apiRequest("/activity/connections",{method:"POST",token,body:{provider}});await loadAll();setNotice("Consentimiento registrado. La sincronización depende de la app compatible.");}catch(x){setError(errorText(x));}finally{setBusy(false);}}
 async function disconnect(item:Connection){if(!window.confirm("¿Revocar el consentimiento para "+item.label+"?"))return;setBusy(true);try{await apiRequest("/activity/connections/"+item.provider+"?delete_data="+String(Boolean(deleteImported[item.provider])),{method:"DELETE",token});await loadAll();setNotice("Conexión revocada.");}catch(x){setError(errorText(x));}finally{setBusy(false);}}

 const checkin=checkins.find(x=>x.date===date);
 return <div className="habits-workspace">
  <div className="module-heading"><div><span className="eyebrow">HÁBITOS Y BIENESTAR</span><h2>Cuida lo que sostiene tu progreso</h2><p className="muted">Hidratación, actividad física y estado de ánimo</p></div><label className="date-control">Día seleccionado<input type="date" max={new Date().toLocaleDateString("sv-SE")} value={date} onChange={e=>onDateChange(e.target.value)}/></label></div>
  {error&&<div className="dashboard-alert">{error}<button type="button" onClick={()=>setError("")}>Cerrar</button></div>}{notice&&<div className="nutrition-notice">{notice}<button type="button" onClick={()=>setNotice("")}>×</button></div>}
  <section className="habits-summary-grid">
   <article className="panel"><span className="eyebrow">HIDRATACIÓN · HOY</span><strong className="habits-big-number">{fmt(water?.today_ml)} <small>/ {fmt(water?.goal_ml)} ml</small></strong><div className="habits-meter"><span style={{width:Math.min(100,water?.today_pct||0)+"%"}}/></div><p className="muted">Media de días registrados: {fmt(water?.avg_ml)} ml · objetivo alcanzado {water?.days_goal_met??0}/14 días</p><form className="inline-form" onSubmit={addWater}><select value={waterAmount} onChange={e=>setWaterAmount(e.target.value)}><option value="150">150 ml</option><option value="250">250 ml</option><option value="330">330 ml</option><option value="500">500 ml</option><option value="750">750 ml</option></select><button className="primary-button compact" disabled={busy}>Añadir agua</button></form></article>
   <article className="panel"><span className="eyebrow">ACTIVIDAD · HOY</span><strong className="habits-big-number">{fmt(activity?.today_steps)} <small>/ {fmt(activity?.goal)} pasos</small></strong><div className="habits-meter activity"><span style={{width:Math.min(100,activity?.today_pct||0)+"%"}}/></div><p className="muted">Media: {fmt(activity?.avg_steps)} pasos · objetivo alcanzado {activity?.days_goal_met??0}/{activity?.days_recorded??0} días</p><form className="stack-form" onSubmit={saveActivity}><div className="nutrition-log-controls"><label>Pasos del día<input required type="number" min="0" max="200000" value={steps} onChange={e=>setSteps(e.target.value)} placeholder="Ej. 8500"/></label><label>Distancia (km)<input type="number" min="0" max="500" step=".1" value={distance} onChange={e=>setDistance(e.target.value)}/></label></div><button className="secondary-button">Guardar actividad</button></form></article>
   <article className="panel"><span className="eyebrow">CONSTANCIA</span><strong className="habits-big-number">{checkins.length} <small>check-ins recientes</small></strong><p className="muted">Los valores numéricos pueden aparecer en los análisis de progreso; tus notas privadas nunca se envían a la IA.</p><div className="habits-checkin-average"><span>Ánimo medio</span><strong>{fmt(checkins.length?checkins.reduce((a,x)=>a+x.mood,0)/checkins.length:null,1)}/5</strong></div></article>
  </section>
  <div className="habits-two-col">
   <section className="panel"><div className="list-heading"><div><h3>Objetivo de agua</h3><p className="muted">Personaliza tu hidratación diaria</p></div></div><form className="inline-form" onSubmit={saveWaterGoal}><label>Objetivo (ml)<input type="number" min="500" max="10000" step="250" value={waterGoal} onChange={e=>setWaterGoal(e.target.value)}/></label><button className="secondary-button" disabled={busy}>Guardar objetivo</button></form><div className="habits-bars">{water?.days.map(item=><div key={item.date} title={item.date+": "+fmt(item.ml)+" ml"}><span style={{height:Math.max(3,Math.min(100,item.pct))+"%"}}/><small>{item.date.slice(8)}</small></div>)}</div><p className="muted">Registros del día {date}</p>{waterLogs.map(item=><div className="nutrition-entry" key={item.id}><div><strong>{fmt(item.quantity_ml)} ml</strong><span>{new Date(item.logged_at).toLocaleTimeString("es-ES",{hour:"2-digit",minute:"2-digit"})} · {item.source}</span></div><button type="button" className="danger-link" onClick={()=>void deleteWater(item)}>Eliminar</button></div>)}{!waterLogs.length&&<p className="muted">No hay tomas registradas para esta fecha.</p>}</section>
   <section className="panel"><h3>Check-in diario</h3><p className="muted">Escala de 1 a 5. Las notas son privadas y no forman parte de los resúmenes.</p><form className="stack-form" onSubmit={saveCheckin}>
    <div className="habits-score-grid">{[["Ánimo",mood,setMood],["Energía",energy,setEnergy],["Estrés",stress,setStress],["Sueño",sleep,setSleep]].map(([label,value,setter]:any)=><label key={label}>{label}<select value={value} onChange={e=>setter(e.target.value)}>{[1,2,3,4,5].map(n=><option key={n} value={n}>{n} · {scores[n-1]}</option>)}</select></label>)}</div>
    <label>Nota personal<textarea rows={3} maxLength={2000} value={notes} onChange={e=>setNotes(e.target.value)} placeholder="¿Cómo te has encontrado hoy?"/></label>
    <div className="inline-form"><button className="primary-button compact" disabled={busy}>{checkin?"Actualizar check-in":"Guardar check-in"}</button>{checkin&&<button type="button" className="secondary-button" onClick={()=>void deleteCheckin()}>Eliminar</button>}</div>
   </form>
   <div className="habits-checkin-list"><strong>Últimos registros</strong>{checkins.slice().reverse().slice(0,8).map(item=><div key={item.date}><span>{item.date}</span><small>Ánimo {item.mood}/5 · Energía {item.energy_level??"—"}/5 · Sueño {item.sleep_quality??"—"}/5</small></div>)}</div></section>
  </div>
  <section className="panel"><div className="list-heading"><div><h3>Fuentes de actividad</h3><p className="muted">Puedes conceder y revocar el consentimiento en cualquier momento. Las fuentes del mismo día no se suman para evitar duplicar pasos.</p></div></div>
   <div className="habits-connections">{connections.map(item=><article key={item.provider} className="habits-connection"><div><strong>{item.label} {item.connected&&<span className="connection-status">Conectado</span>}</strong><p>{item.note}</p>{item.mode==="push"&&<small>La conexión registra tu consentimiento; para importar actividad hace falta la aplicación móvil compatible.</small>}</div>
    <div>{item.connected?<><label className="nutrition-toggle"><input type="checkbox" checked={Boolean(deleteImported[item.provider])} onChange={e=>setDeleteImported(a=>({...a,[item.provider]:e.target.checked}))}/> Borrar datos importados</label><button type="button" className="secondary-button" disabled={busy} onClick={()=>void disconnect(item)}>Desconectar</button></>:item.configured?<button type="button" className="secondary-button" disabled={busy} onClick={()=>void connect(item.provider)}>Dar consentimiento</button>:<span className="muted">Pendiente de configurar</span>}</div>
   </article>)}</div>
  </section>
 </div>;
}
