import { Redirect, Stack } from "expo-router";
import { useAuth } from "@/auth/AuthProvider";
export default function AuthLayout() {
  const { user, loading } = useAuth();
  if (!loading && user?.onboarding_completed) return <Redirect href="/(tabs)" />;
  if (!loading && user && !user.onboarding_completed) return <Redirect href="/onboarding" />;
  return <Stack screenOptions={{headerShown:false,animation:"fade"}} />;
}