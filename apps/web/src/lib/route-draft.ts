import type {RoutePoint} from "@/lib/route";
import {lastPointTime,mergePoints} from "@/lib/route";
export type StoredDraft={clientId:string;owner:string;kind:string;category:"walking"|"running";performedOn:string;startedAt:string;points:RoutePoint[]};
export type RemoteDraft={client_id:string;kind:string;category:"walking"|"running";performed_on?:string|null;started_at:string;points:RoutePoint[]};
const KEY="smartfit.activeRun.v1";
export function newClientId(){const id=typeof crypto!=="undefined"&&"randomUUID" in crypto?crypto.randomUUID():Math.random().toString(36).slice(2)+Date.now().toString(36);return"run-"+id;}
export function loadLocalDraft(owner:string):StoredDraft|null{try{const raw=window.localStorage.getItem(KEY);if(!raw)return null;const d=JSON.parse(raw) as StoredDraft;return d.owner===owner&&!!d.clientId&&Array.isArray(d.points)?d:null;}catch{return null;}}
export function saveLocalDraft(d:StoredDraft){try{window.localStorage.setItem(KEY,JSON.stringify(d));}catch{/* best effort; el backend conserva la otra copia */}}
export function clearLocalDraft(){try{window.localStorage.removeItem(KEY);}catch{/* best effort */}}
export function pickDraft(owner:string,local:StoredDraft|null,remote:RemoteDraft|null):StoredDraft|null{const r:StoredDraft|null=remote?{clientId:remote.client_id,owner,kind:remote.kind,category:remote.category,performedOn:remote.performed_on??new Date().toLocaleDateString("sv-SE"),startedAt:remote.started_at,points:remote.points}:null;if(local&&r&&local.clientId===r.clientId)return{...local,points:mergePoints(local.points,r.points)};if(local&&r)return(lastPointTime(local.points)??0)>=(lastPointTime(r.points)??0)?local:r;return local??r;}
