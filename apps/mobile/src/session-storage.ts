import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

function browserStorage(): Storage {
  if (typeof window === "undefined") {
    throw new Error("El almacenamiento del navegador no está disponible fuera del cliente");
  }
  return window.localStorage;
}

/**
 * SecureStore is available on native platforms only.
 * Expo Web uses localStorage as a development convenience; it is not encrypted
 * and must not be treated as equivalent to the iOS Keychain / Android Keystore.
 */
export async function getSessionItem(key: string): Promise<string | null> {
  if (Platform.OS === "web") return browserStorage().getItem(key);
  return SecureStore.getItemAsync(key);
}

export async function setSessionItem(key: string, value: string): Promise<void> {
  if (Platform.OS === "web") {
    browserStorage().setItem(key, value);
    return;
  }
  await SecureStore.setItemAsync(key, value);
}

export async function deleteSessionItem(key: string): Promise<void> {
  if (Platform.OS === "web") {
    browserStorage().removeItem(key);
    return;
  }
  await SecureStore.deleteItemAsync(key);
}
