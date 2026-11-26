import { Redirect } from "expo-router";
import { ActivityIndicator, View } from "react-native";
import { useAuth } from "@/auth/AuthProvider";
import { colors } from "@/theme";
export default function Index() {
  const { user, loading } = useAuth();
  if (loading) return <View style={{flex:1,alignItems:"center",justifyContent:"center",backgroundColor:colors.background}}><ActivityIndicator color={colors.accent} size="large" /></View>;
  if (!user) return <Redirect href="/(auth)/login" />;
  if (!user.onboarding_completed) return <Redirect href="/onboarding" />;
  return <Redirect href="/(tabs)" />;
}