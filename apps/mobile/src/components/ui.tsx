import React, { type PropsWithChildren } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View, type TextInputProps, type ViewStyle } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors, spacing } from "@/theme";

export function Screen({ children, padded = true }: PropsWithChildren<{ padded?: boolean }>) {
  return <SafeAreaView style={styles.safe} edges={["top", "left", "right"]}>
    <ScrollView contentContainerStyle={[styles.scroll, !padded && styles.noPadding]} keyboardShouldPersistTaps="handled">{children}</ScrollView>
  </SafeAreaView>;
}
export function PageTitle({ eyebrow, title, subtitle }: { eyebrow?: string; title: string; subtitle?: string }) {
  return <View style={styles.pageTitle}>
    {eyebrow ? <Text style={styles.eyebrow}>{eyebrow.toUpperCase()}</Text> : null}
    <Text style={styles.title}>{title}</Text>
    {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
  </View>;
}
export function Panel({ children, style }: PropsWithChildren<{ style?: ViewStyle }>) {
  return <View style={[styles.panel, style]}>{children}</View>;
}
export function SectionTitle({ title, action }: { title: string; action?: string }) {
  return <View style={styles.sectionTitle}><Text style={styles.sectionText}>{title}</Text>{action ? <Text style={styles.sectionAction}>{action}</Text> : null}</View>;
}
export function AppButton({ title, onPress, loading = false, disabled = false, variant = "primary" }: {
  title: string; onPress: () => void; loading?: boolean; disabled?: boolean; variant?: "primary" | "secondary" | "quiet";
}) {
  return <Pressable onPress={onPress} disabled={disabled || loading} style={({ pressed }) => [
    styles.button, variant === "secondary" && styles.buttonSecondary, variant === "quiet" && styles.buttonQuiet,
    (disabled || loading) && styles.buttonDisabled, pressed && styles.buttonPressed
  ]}>
    {loading ? <ActivityIndicator color={variant === "primary" ? colors.background : colors.text} /> :
      <Text style={[styles.buttonText, variant !== "primary" && styles.buttonTextSecondary]}>{title}</Text>}
  </Pressable>;
}
export function Field({ label, hint, style, ...props }: TextInputProps & { label: string; hint?: string }) {
  return <View style={styles.field}>
    <Text style={styles.fieldLabel}>{label}</Text>
    <TextInput placeholderTextColor={colors.muted} selectionColor={colors.accent} style={[styles.input, style]} {...props} />
    {hint ? <Text style={styles.hint}>{hint}</Text> : null}
  </View>;
}
export function ChoiceRow<T extends string>({ value, options, onChange }: {
  value: T; options: Array<{ value: T; label: string }>; onChange: (value: T) => void;
}) {
  return <View style={styles.choiceRow}>{options.map((option) => <Pressable key={option.value} onPress={() => onChange(option.value)}
    style={[styles.choice, value === option.value && styles.choiceActive]}>
    <Text style={[styles.choiceText, value === option.value && styles.choiceTextActive]}>{option.label}</Text>
  </Pressable>)}</View>;
}
export function ProgressBar({ value, color = colors.accent }: { value: number; color?: string }) {
  return <View style={styles.progressTrack}><View style={[styles.progressFill, { width: Math.max(0, Math.min(100, value)) + "%", backgroundColor: color }]} /></View>;
}
export function ErrorMessage({ message }: { message: string }) {
  return message ? <Text accessibilityRole="alert" style={styles.error}>{message}</Text> : null;
}
export function Muted({ children }: PropsWithChildren) { return <Text style={styles.muted}>{children}</Text>; }

export const styles = StyleSheet.create({
  safe:{flex:1,backgroundColor:colors.background}, scroll:{padding:spacing.lg,paddingBottom:46,gap:spacing.lg}, noPadding:{padding:0},
  pageTitle:{gap:7,marginTop:spacing.sm}, eyebrow:{color:colors.accent,fontSize:11,fontWeight:"800",letterSpacing:1.6},
  title:{color:colors.text,fontSize:30,fontWeight:"800",letterSpacing:-0.7}, subtitle:{color:colors.muted,fontSize:14,lineHeight:21},
  panel:{backgroundColor:colors.surface,borderColor:colors.border,borderWidth:1,borderRadius:22,padding:spacing.md,gap:spacing.sm},
  sectionTitle:{flexDirection:"row",alignItems:"center",justifyContent:"space-between",marginTop:3},
  sectionText:{color:colors.text,fontSize:17,fontWeight:"700"}, sectionAction:{color:colors.accent,fontSize:12,fontWeight:"700"},
  button:{minHeight:52,borderRadius:16,backgroundColor:colors.accent,alignItems:"center",justifyContent:"center",paddingHorizontal:18},
  buttonSecondary:{backgroundColor:colors.surfaceRaised,borderWidth:1,borderColor:colors.border},buttonQuiet:{backgroundColor:"transparent",borderWidth:1,borderColor:colors.border},
  buttonDisabled:{opacity:0.55},buttonPressed:{opacity:0.84,transform:[{scale:0.99}]},buttonText:{color:colors.background,fontWeight:"800",fontSize:15},
  buttonTextSecondary:{color:colors.text},field:{gap:8},fieldLabel:{color:colors.text,fontWeight:"700",fontSize:13},
  input:{color:colors.text,backgroundColor:colors.surfaceRaised,borderWidth:1,borderColor:colors.border,borderRadius:14,paddingHorizontal:15,minHeight:50,fontSize:15},
  hint:{color:colors.muted,fontSize:12},choiceRow:{flexDirection:"row",flexWrap:"wrap",gap:8},
  choice:{borderWidth:1,borderColor:colors.border,backgroundColor:colors.surfaceRaised,borderRadius:13,paddingHorizontal:13,paddingVertical:11},
  choiceActive:{borderColor:colors.accent,backgroundColor:colors.accentDark},choiceText:{color:colors.muted,fontSize:12,fontWeight:"600"},
  choiceTextActive:{color:colors.accent,fontWeight:"800"},progressTrack:{height:8,borderRadius:8,backgroundColor:colors.surfaceRaised,overflow:"hidden"},
  progressFill:{height:8,borderRadius:8},error:{color:colors.danger,fontSize:13,lineHeight:19},muted:{color:colors.muted,fontSize:13,lineHeight:19}
});