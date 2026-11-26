import React, { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Modal, Pressable, Text, View } from "react-native";
import { CameraView, useCameraPermissions, type BarcodeScanningResult } from "expo-camera";
import { colors } from "@/theme";

type Props = {
  visible: boolean;
  onClose: () => void;
  onScanned: (code: string) => void;
};

const BARCODE_TYPES = [
  "ean13", "ean8", "upc_a", "upc_e", "code128", "code39", "code93", "itf14", "codabar",
] as const;

export function BarcodeScanner({ visible, onClose, onScanned }: Props) {
  const [permission, requestPermission] = useCameraPermissions();
  const [cameraError, setCameraError] = useState("");
  const scanned = useRef(false);

  useEffect(() => {
    if (visible) {
      scanned.current = false;
      setCameraError("");
    }
  }, [visible]);

  function handleScanned(result: BarcodeScanningResult) {
    if (scanned.current) return;
    const code = result.data.trim();
    if (!code) return;
    scanned.current = true;
    onScanned(code);
  }

  return <Modal visible={visible} animationType="slide" presentationStyle="fullScreen" onRequestClose={onClose}>
    <View style={{ flex: 1, backgroundColor: "#050807" }}>
      {!permission ? <View style={{ flex: 1, alignItems: "center", justifyContent: "center", gap: 12 }}>
        <ActivityIndicator color={colors.accent} />
        <Text style={{ color: "#fff" }}>Comprobando permiso de cámara…</Text>
      </View> : !permission.granted ? <View style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: 28, gap: 14 }}>
        <Text style={{ color: "#fff", fontSize: 20, fontWeight: "900", textAlign: "center" }}>Necesitamos la cámara</Text>
        <Text style={{ color: "#d5ddd8", textAlign: "center", lineHeight: 21 }}>
          SmartFit usa la cámara únicamente para detectar el código de barras del envase.
        </Text>
        <Pressable onPress={() => void requestPermission()} style={{ backgroundColor: colors.accent, borderRadius: 14, paddingHorizontal: 20, paddingVertical: 12 }}>
          <Text style={{ color: "#07120c", fontWeight: "900" }}>Permitir cámara</Text>
        </Pressable>
        <Pressable onPress={onClose} hitSlop={10} style={{ padding: 10 }}>
          <Text style={{ color: "#fff", fontWeight: "700" }}>Cancelar</Text>
        </Pressable>
      </View> : <>
        <CameraView
          style={{ flex: 1 }}
          facing="back"
          barcodeScannerSettings={{ barcodeTypes: [...BARCODE_TYPES] }}
          onBarcodeScanned={handleScanned}
          onMountError={event => setCameraError(event.message || "No se pudo iniciar la cámara.")}
        />
        <View pointerEvents="box-none" style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0, justifyContent: "space-between", padding: 22, paddingTop: 58 }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <Text style={{ color: "#fff", fontSize: 17, fontWeight: "900" }}>Escanear código</Text>
            <Pressable onPress={onClose} hitSlop={12} style={{ backgroundColor: "#101914dd", borderRadius: 24, paddingHorizontal: 15, paddingVertical: 10 }}>
              <Text style={{ color: "#fff", fontWeight: "800" }}>Cerrar ✕</Text>
            </Pressable>
          </View>
          <View style={{ alignItems: "center", gap: 10 }}>
            <View style={{ width: "90%", height: 150, borderWidth: 2, borderColor: colors.accent, borderRadius: 18, backgroundColor: "transparent" }} />
            <Text style={{ color: "#fff", textAlign: "center", fontWeight: "700", backgroundColor: "#101914dd", padding: 10, borderRadius: 10 }}>
              Centra el código de barras dentro del marco
            </Text>
            {cameraError ? <Text style={{ color: "#fff", backgroundColor: "#8c2525dd", padding: 10, borderRadius: 10, textAlign: "center" }}>{cameraError}</Text> : null}
          </View>
        </View>
      </>}
    </View>
  </Modal>;
}
