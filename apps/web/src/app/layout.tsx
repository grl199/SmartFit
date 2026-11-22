import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SmartFit — Tu progreso, con criterio",
  description: "Entrenamiento y nutrición conectados en un solo lugar.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
