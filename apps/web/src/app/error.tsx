"use client";

import { useEffect } from "react";

type Props = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function ErrorPage({ error, reset }: Props) {
  useEffect(() => {
    console.error("SmartFit client route error:", error);
  }, [error]);

  return (
    <main className="shell auth-shell">
      <section className="auth-panel">
        <div className="form-card">
          <div className="eyebrow">SMARTFIT / RECUPERACIÓN</div>
          <h1>No se ha podido cargar tu espacio.</h1>
          <p className="intro">
            Tu cuenta y tus registros no se han borrado. Prueba a cargar de nuevo la pantalla.
          </p>
          {error.digest && (
            <p className="footnote">Referencia técnica: <code>{error.digest}</code></p>
          )}
          <button className="primary-button" type="button" onClick={reset}>
            Reintentar
          </button>
          <button className="quiet-button" type="button" onClick={() => window.location.reload()}>
            Recargar la aplicación
          </button>
        </div>
      </section>
    </main>
  );
}
