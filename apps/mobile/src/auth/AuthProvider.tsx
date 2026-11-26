import { TokenStorage } from "@/lib/token-storage";
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, publicApi, type OnboardingPayload, type SmartFitUser, type TokenResponse } from "@/lib/api";

const TOKEN_KEY = "smartfit.access-token";
const REFRESH_KEY = "smartfit.refresh-token";
type AuthContextValue = {
  user: SmartFitUser | null; token: string | null; loading: boolean;
  signIn: (name: string, password: string) => Promise<void>;
  signUp: (name: string, password: string) => Promise<void>;
  completeOnboarding: (payload: OnboardingPayload) => Promise<void>;
  signOut: () => Promise<void>;
};
const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: React.PropsWithChildren) {
  const [user,setUser] = useState<SmartFitUser|null>(null);
  const [token,setToken] = useState<string|null>(null);
  const [loading,setLoading] = useState(true);

  useEffect(() => {
    let active=true;
    async function restore() {
      try {
        const saved=await TokenStorage.getItemAsync(TOKEN_KEY);
        if(saved) {
          const restored=await api<SmartFitUser>("/auth/me",saved);
          const currentToken=await TokenStorage.getItemAsync(TOKEN_KEY);
          if(active){setToken(currentToken??saved);setUser(restored);}
        }
      } catch {
        // Si falla la red se conserva la sesión guardada para poder reintentar al abrir de nuevo.
      } finally { if(active)setLoading(false); }
    }
    void restore();
    return () => {active=false;};
  }, []);

  const authenticate=useCallback(async(path:"/auth/session/login"|"/auth/session/register",name:string,password:string)=>{
    const result=await publicApi<TokenResponse>(path,{method:"POST",body:{name:name.trim(),password}});
    await TokenStorage.setItemAsync(TOKEN_KEY,result.access_token);
    await TokenStorage.setItemAsync(REFRESH_KEY,result.refresh_token);
    setToken(result.access_token);setUser(result.user);
  },[]);
  const signIn=useCallback((name:string,password:string)=>authenticate("/auth/session/login",name,password),[authenticate]);
  const signUp=useCallback((name:string,password:string)=>authenticate("/auth/session/register",name,password),[authenticate]);

  const completeOnboarding=useCallback(async(payload:OnboardingPayload)=>{
    if(!token)throw new Error("Inicia sesión para continuar.");
    await api("/onboarding",token,{method:"POST",body:payload});
    const refreshed=await api<SmartFitUser>("/auth/me",token);
    const activeToken=await TokenStorage.getItemAsync(TOKEN_KEY);
    setToken(activeToken??token);setUser(refreshed);
  },[token]);

  const signOut=useCallback(async()=>{
    const refreshToken=await TokenStorage.getItemAsync(REFRESH_KEY);
    try {
      if(token) await api("/auth/session/logout",token,{method:"POST",body:refreshToken?{refresh_token:refreshToken}:undefined});
    } catch {
      // La sesión local se elimina incluso si el backend no está disponible.
    } finally {
      await TokenStorage.deleteItemAsync(TOKEN_KEY);
      await TokenStorage.deleteItemAsync(REFRESH_KEY);
      setToken(null);setUser(null);
    }
  },[token]);

  const value=useMemo(()=>({user,token,loading,signIn,signUp,completeOnboarding,signOut}),
    [user,token,loading,signIn,signUp,completeOnboarding,signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
export function useAuth():AuthContextValue {
  const context=useContext(AuthContext);
  if(!context)throw new Error("useAuth debe usarse dentro de AuthProvider");
  return context;
}