import React, { createElement, useMemo, useState } from "react";
import { Platform, Text, View } from "react-native";
import { WebView } from "react-native-webview";
import { MUSCLE_MAP_SVG } from "@/lib/muscle-map-svg";
import { colors } from "@/theme";

type MuscleValue = {
  sets: number; strength_sets: number; cardio_sets: number; volume_kg: number; exercises?: string[];
};
type Props = { muscles: Record<string, MuscleValue> };

const muscleMapTargets: Record<string, string[]> = {
  chest: ["pectoralis-major"],
  shoulders: ["deltoid-anterior", "deltoid-lateral", "deltoid-posterior"],
  biceps: ["biceps"],
  forearms: ["forearms"],
  abs: ["rectus-abdominis", "external-obliques"],
  quadriceps: ["quadriceps"],
  calves: ["gastrocnemius", "soleus"],
  traps: ["trapezius"],
  triceps: ["triceps"],
  lats: ["latissimus-dorsi"],
  lower_back: ["erector-spinae"],
  upper_back: ["trapezius", "latissimus-dorsi"],
  glutes: ["gluteus-maximus", "gluteus-medius"],
  hamstrings: ["hamstrings"],
  abductors: ["gluteus-medius"],
};

export function MuscleMap({ muscles }: Props) {
  const [active, setActive] = useState<{ name: string; sets: number; strength: number; cardio: number; volume: number } | null>(null);
  const payload = useMemo(() => {
    const values = Object.fromEntries(Object.entries(muscles).map(([key, value]) => [key, {
      sets: Number(value.sets) || 0,
      strength: Number(value.strength_sets) || 0,
      cardio: Number(value.cardio_sets) || 0,
      volume: Number(value.volume_kg) || 0,
    }]));
    const max = Math.max(1, ...Object.values(values).map(value => value.sets));
    const groups: Record<string, number> = {};
    for (const [svgId, keys] of Object.entries(muscleMapTargets)) {
      groups[svgId] = Math.max(0, ...keys.map(key => values[key]?.sets ?? 0));
    }
    return { values, max, groups };
  }, [muscles]);

  const html = useMemo(() => {
    const data = JSON.stringify(payload);
    const script = `
      (function(){
        const data=${data};
        const targets=${JSON.stringify(muscleMapTargets)};
        const root=document.querySelector('.smartfit-muscle-map');
        if(!root)return;
        const nodes=Array.from(root.querySelectorAll('.muscle[data-muscle]'));
        nodes.forEach(node=>{
          const id=node.getAttribute('data-muscle')||'';
          const load=Number(data.groups[id]||0);
          const level=load>0?Math.min(5,Math.max(1,Math.ceil(load/data.max*5))):0;
          node.classList.remove('level-0','level-1','level-2','level-3','level-4','level-5');
          node.classList.add('level-'+level);
          node.setAttribute('role','button');
          node.setAttribute('tabindex','0');
          const title=node.querySelector('title')?.textContent||id;
          const groupKey=Object.keys(targets).find(key=>(targets[key]||[]).includes(id));
          const detail=groupKey?data.values[groupKey]:null;
          const send=()=>window.ReactNativeWebView?.postMessage(JSON.stringify({
            name:title,sets:load,strength:detail?.strength||0,cardio:detail?.cardio||0,volume:detail?.volume||0
          }));
          node.addEventListener('click',send);
          node.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();send();}});
        });
      })();
    `;
    return `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"/>
      <style>
        html,body{margin:0;padding:0;background:#0e1612;width:100%;height:100%;overflow:hidden}
        body{display:flex;align-items:center;justify-content:center}
        .smartfit-muscle-map{width:100%;height:auto;max-height:100%;display:block}
        .smartfit-muscle-map .muscle{cursor:pointer}
      </style>
    </head><body>${MUSCLE_MAP_SVG}<script>${script}</script></body></html>`;
  }, [payload]);

  function handleMessage(raw: string) {
    try {
      const value = JSON.parse(raw) as { name: string; sets: number; strength: number; cardio: number; volume: number };
      setActive(value);
    } catch {
      setActive(null);
    }
  }

  return <View style={{ gap: 9 }}>
    <Text style={{ color: colors.muted, fontSize: 12 }}>
      Mapa frontal y posterior. Los músculos se colorean según las series ponderadas del periodo; toca uno para ver sus datos.
    </Text>
    <View style={{ height: 285, borderRadius: 14, overflow: "hidden", borderWidth: 1, borderColor: colors.border }}>
      {Platform.OS === "web"
        ? createElement("iframe", {
            title: "Mapa muscular SmartFit",
            srcDoc: html,
            scrolling: "no",
            style: { width: "100%", height: "100%", border: 0, display: "block" },
            onLoad: undefined,
          })
        : <WebView
            source={{ html, baseUrl: "https://smartfit.local" }}
            originWhitelist={["*"]}
            javaScriptEnabled
            scrollEnabled={false}
            nestedScrollEnabled={false}
            onMessage={event => handleMessage(event.nativeEvent.data)}
            style={{ flex: 1, backgroundColor: "#0e1612" }}
          />}
    </View>
    {active ? <View style={{ backgroundColor: colors.surfaceRaised, padding: 12, borderRadius: 12, gap: 4 }}>
      <Text style={{ color: colors.text, fontWeight: "900" }}>{active.name}</Text>
      <Text style={{ color: colors.accent, fontWeight: "800" }}>{active.sets.toLocaleString("es-ES",{maximumFractionDigits:1})} series ponderadas</Text>
      <Text style={{ color: colors.muted, fontSize: 12 }}>
        Fuerza {active.strength.toLocaleString("es-ES",{maximumFractionDigits:1})} · Cardio {active.cardio.toLocaleString("es-ES",{maximumFractionDigits:1})} · Volumen {Math.round(active.volume).toLocaleString("es-ES")} kg
      </Text>
    </View> : null}
    <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
      <Text style={{ color: colors.muted, fontSize: 10 }}>Menos carga</Text>
      <View style={{ flexDirection: "row", gap: 4 }}>
        {["#d9ddd0","#f7e27a","#f6bd45","#ee8b2f","#dc4a28","#a8141f"].map((color,index) => <View key={index} style={{ width: 17, height: 8, borderRadius: 3, backgroundColor: color }}/>)}
      </View>
      <Text style={{ color: colors.muted, fontSize: 10 }}>Más carga</Text>
    </View>
  </View>;
}
