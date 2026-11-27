import "@/lib/cardio-location-task";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { AuthProvider } from "@/auth/AuthProvider";
import { colors } from "@/theme";
export default function RootLayout() {
  return <AuthProvider>
    <StatusBar style="light" />
    <Stack screenOptions={{ headerShown:false, contentStyle:{backgroundColor:colors.background} }} />
  </AuthProvider>;
}