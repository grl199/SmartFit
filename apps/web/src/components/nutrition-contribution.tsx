"use client";

type NutrientKey = "kcal" | "protein_g" | "carbs_g" | "sugars_g" | "fat_g" | "sat_fat_g" | "fiber_g" | "sodium_mg";
type MealTotals = Record<NutrientKey, number>;
type Meal = { key: string; label: string; icon?: string; totals: MealTotals };
type Targets = Partial<Record<"kcal" | "protein_g" | "carbs_g" | "fat_g" | "fiber_g", number>>;
type Props = { meals: Meal[]; targets?: Targets };

const mealLegend = [
  { key: "breakfast", label: "Desayuno", icon: "☀️" },
  { key: "mid_morning", label: "Almuerzo", icon: "🍎" },
  { key: "lunch", label: "Comida", icon: "🍽️" },
  { key: "snack", label: "Merienda", icon: "☕" },
  { key: "dinner", label: "Cena", icon: "🌙" },
] as const;

const format = (value: number) => value.toLocaleString("es-ES", { maximumFractionDigits: 1 });

export function NutritionContribution({ meals, targets = {} }: Props) {
  const energyTarget = Number(targets.kcal) > 0 ? Number(targets.kcal) : 2500;
  const target = (value: number | undefined, fallback: number) => Number(value) > 0 ? Number(value) : fallback;
  const rows: Array<{ key: NutrientKey; label: string; unit: string; goal: number; kind: "goal" | "limit" | "minimum"; note: string }> = [
    { key: "kcal", label: "Energía", unit: "kcal", goal: energyTarget, kind: "goal", note: "Objetivo diario personalizado" },
    { key: "protein_g", label: "Proteína", unit: "g", goal: target(targets.protein_g, energyTarget * 0.2 / 4), kind: "goal", note: "Objetivo diario personalizado" },
    { key: "carbs_g", label: "Hidratos", unit: "g", goal: target(targets.carbs_g, energyTarget * 0.5 / 4), kind: "goal", note: "Objetivo diario personalizado" },
    { key: "sugars_g", label: "Azúcares", unit: "g", goal: energyTarget * 0.1 / 4, kind: "limit", note: "Referencia orientativa: 10 % de la energía, para azúcares libres" },
    { key: "fat_g", label: "Grasas", unit: "g", goal: target(targets.fat_g, energyTarget * 0.3 / 9), kind: "goal", note: "Objetivo diario personalizado" },
    { key: "sat_fat_g", label: "Grasas saturadas", unit: "g", goal: energyTarget * 0.1 / 9, kind: "limit", note: "Límite orientativo: menos del 10 % de la energía" },
    { key: "fiber_g", label: "Fibra", unit: "g", goal: target(targets.fiber_g, 25), kind: "minimum", note: "Referencia mínima orientativa para adultos" },
    { key: "sodium_mg", label: "Sodio", unit: "mg", goal: 2000, kind: "limit", note: "Referencia OMS: menos de 2.000 mg al día" },
  ];

  return (
    <section className="nutrition-meal-contribution">
      <h3>Contribución de cada comida</h3>
      <p className="muted">Los colores muestran qué aporta cada comida. La línea blanca marca el objetivo o límite de referencia.</p>
      <div className="nutrition-contribution-legend" aria-label="Leyenda de comidas">
        {mealLegend.map(meal => (
          <span key={meal.key}><i data-meal={meal.key} />{meal.icon} {meal.label}</span>
        ))}
      </div>
      {rows.map(row => {
        const total = meals.reduce((sum, meal) => sum + Math.max(0, Number(meal.totals[row.key] || 0)), 0);
        const visualMax = Math.max(row.goal * 1.18, total * 1.08, 1);
        const markerPosition = Math.min(100, row.goal / visualMax * 100);
        const percentage = total / row.goal * 100;
        const difference = Math.abs(total - row.goal);
        const status = row.kind === "minimum"
          ? (total >= row.goal ? "Mínimo alcanzado" : "Faltan " + format(difference) + " " + row.unit)
          : row.kind === "limit"
            ? (total > row.goal ? "Exceso de " + format(difference) + " " + row.unit : "Dentro del límite · margen " + format(difference) + " " + row.unit)
            : (total > row.goal ? "Por encima del objetivo · +" + format(difference) + " " + row.unit : "Restan " + format(difference) + " " + row.unit);
        const statusClass = row.kind === "minimum" && total < row.goal ? "is-pending" : total > row.goal && row.kind !== "minimum" ? "is-over" : "is-ok";
        return (
          <div className="nutrition-contribution-row" key={row.key}>
            <div className="nutrition-contribution-heading">
              <strong>{row.label}</strong>
              <span>{format(total)} / {format(row.goal)} {row.unit} · {format(percentage)}%</span>
            </div>
            <div className="nutrition-contribution-track" role="img" aria-label={row.label + ": " + format(total) + " de " + format(row.goal) + " " + row.unit}>
              {meals.map(meal => (
                <span key={meal.key} data-meal={meal.key} title={meal.label + " · " + format(Number(meal.totals[row.key] || 0)) + " " + row.unit}
                  style={{ width: (Math.max(0, Number(meal.totals[row.key] || 0)) / visualMax * 100) + "%" }} />
              ))}
              <i className="nutrition-contribution-target" style={{ left: markerPosition + "%" }} />
            </div>
            <div className={"nutrition-contribution-status " + statusClass}>
              <span>{status}</span>
              <small>{row.note}</small>
            </div>
          </div>
        );
      })}
      <p className="nutrition-contribution-disclaimer">Las referencias son orientativas, no sustituyen una pauta individual. SmartFit registra azúcares totales y no distingue los azúcares libres de los alimentos.</p>
    </section>
  );
}
