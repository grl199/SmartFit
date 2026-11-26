import React, { createElement, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Platform, Pressable, Text, View, useWindowDimensions } from "react-native";
import { WebView } from "react-native-webview";
import { EXERCISE_ANIMATION_HTML } from "@/lib/exercise-animation-html";
import { colors } from "@/theme";

type Props = { exerciseName: string };

const REQUESTED_EXERCISE_LINE =
  "const requestedExercise=new URLSearchParams(window.location.search).get('exercise')?.trim()||'';";

export function ExerciseAnimation({ exerciseName }: Props) {
  const { height: windowHeight } = useWindowDimensions();
  const animationHeight = Math.max(440, Math.min(640, Math.round(windowHeight * 0.64)));
  const [failed, setFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  useEffect(() => { setFailed(false); setReloadKey(value => value + 1); }, [exerciseName]);
  const html = useMemo(() => {
    const selectedName = JSON.stringify(exerciseName.trim());
    const replacement =
      "const requestedExercise=" + selectedName +
      "||new URLSearchParams(window.location.search).get('exercise')?.trim()||'';";
    return EXERCISE_ANIMATION_HTML.replace(REQUESTED_EXERCISE_LINE, replacement);
  }, [exerciseName]);

  if (failed) {
    return <View style={{
      height: animationHeight, borderRadius: 14, borderWidth: 1, borderColor: colors.border,
      backgroundColor: colors.surfaceRaised, alignItems: "center", justifyContent: "center",
      padding: 18, gap: 8,
    }}>
      <Text style={{ color: colors.text, fontWeight: "800", textAlign: "center" }}>No se pudo cargar la animación 3D</Text>
      <Text style={{ color: colors.muted, fontSize: 12, textAlign: "center" }}>
        Comprueba tu conexión a internet. El motor 3D carga Three.js desde una CDN.
      </Text>
      <Pressable onPress={() => { setFailed(false); setReloadKey(value => value + 1); }} accessibilityRole="button" style={{ paddingVertical: 8, paddingHorizontal: 14 }}>
        <Text style={{ color: colors.accent, fontWeight: "800" }}>Reintentar animación</Text>
      </Pressable>
    </View>;
  }

  if (Platform.OS === "web") {
    return <View style={{
      height: animationHeight, overflow: "hidden", borderRadius: 14,
      borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
    }}>
      {createElement("iframe", {
        title: "Animación 3D: " + exerciseName,
        srcDoc: html,
        allowFullScreen: true,
        scrolling: "no",
        style: { width: "100%", height: "100%", border: 0, display: "block" },
      })}
    </View>;
  }

  return <View style={{
    height: animationHeight, overflow: "hidden", borderRadius: 14,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  }}>
    <WebView
      key={exerciseName + ":" + reloadKey}
      source={{ html, baseUrl: "https://smartfit.local" }}
      originWhitelist={["*"]}
      javaScriptEnabled
      domStorageEnabled
      scrollEnabled={false}
      bounces={false}
      nestedScrollEnabled={false}
      startInLoadingState
      renderLoading={() => <View style={{
        flex: 1, alignItems: "center", justifyContent: "center",
        backgroundColor: colors.surface, gap: 8,
      }}>
        <ActivityIndicator color={colors.accent} />
        <Text style={{ color: colors.muted, fontSize: 12 }}>Preparando animación 3D…</Text>
      </View>}
      onError={() => setFailed(true)}
      style={{ flex: 1, backgroundColor: colors.surface }}
    />
  </View>;
}
