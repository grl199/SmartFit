import React, { createElement, useMemo, useState } from "react";
import { ActivityIndicator, Platform, Text, View } from "react-native";
import { WebView } from "react-native-webview";
import { EXERCISE_ANIMATION_HTML } from "@/lib/exercise-animation-html";
import { colors } from "@/theme";

type Props = { exerciseName: string };

const REQUESTED_EXERCISE_LINE =
  "const requestedExercise=new URLSearchParams(window.location.search).get('exercise')?.trim()||'';";

export function ExerciseAnimation({ exerciseName }: Props) {
  const [failed, setFailed] = useState(false);
  const html = useMemo(() => {
    const selectedName = JSON.stringify(exerciseName.trim());
    const replacement =
      "const requestedExercise=" + selectedName +
      "||new URLSearchParams(window.location.search).get('exercise')?.trim()||'';";
    return EXERCISE_ANIMATION_HTML.replace(REQUESTED_EXERCISE_LINE, replacement);
  }, [exerciseName]);

  if (failed) {
    return <View style={{
      height: 280, borderRadius: 14, borderWidth: 1, borderColor: colors.border,
      backgroundColor: colors.surfaceRaised, alignItems: "center", justifyContent: "center",
      padding: 18, gap: 8,
    }}>
      <Text style={{ color: colors.text, fontWeight: "800", textAlign: "center" }}>No se pudo cargar la animación 3D</Text>
      <Text style={{ color: colors.muted, fontSize: 12, textAlign: "center" }}>
        Comprueba tu conexión a internet y vuelve a abrir la ficha. El motor 3D carga Three.js desde una CDN.
      </Text>
    </View>;
  }

  if (Platform.OS === "web") {
    return <View style={{
      height: 340, overflow: "hidden", borderRadius: 14,
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
    height: 340, overflow: "hidden", borderRadius: 14,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  }}>
    <WebView
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
