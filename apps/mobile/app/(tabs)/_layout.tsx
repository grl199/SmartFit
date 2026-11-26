import { Redirect, Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { ActivityIndicator, View } from "react-native";
import { useAuth } from "@/auth/AuthProvider";
import { colors } from "@/theme";
export default function TabsLayout() {
  const {user,loading}=useAuth();
  if (loading) return <View style={{flex:1,alignItems:"center",justifyContent:"center",backgroundColor:colors.background}}><ActivityIndicator color={colors.accent} /></View>;
  if (!user) return <Redirect href="/(auth)/login" />;
  if (!user.onboarding_completed) return <Redirect href="/onboarding" />;
  return <Tabs screenOptions={{
    headerShown:false,tabBarActiveTintColor:colors.accent,tabBarInactiveTintColor:colors.muted,
    tabBarStyle:{backgroundColor:colors.surface,borderTopColor:colors.border,height:66,paddingTop:7,paddingBottom:8},
    tabBarLabelStyle:{fontSize:10,fontWeight:"700"}
  }}>
    <Tabs.Screen name="index" options={{title:"Hoy",tabBarIcon:({color,size})=><Ionicons name="home-outline" color={String(color)} size={size}/>}} />
    <Tabs.Screen name="nutrition" options={{title:"Nutrición",tabBarIcon:({color,size})=><Ionicons name="restaurant-outline" color={String(color)} size={size}/>}} />
    <Tabs.Screen name="training" options={{title:"Entreno",tabBarIcon:({color,size})=><Ionicons name="barbell-outline" color={String(color)} size={size}/>}} />
    <Tabs.Screen name="progress" options={{title:"Progreso",tabBarIcon:({color,size})=><Ionicons name="trending-up-outline" color={String(color)} size={size}/>}} />
    <Tabs.Screen name="profile" options={{title:"Perfil",tabBarIcon:({color,size})=><Ionicons name="person-outline" color={String(color)} size={size}/>}} />
  </Tabs>;
}