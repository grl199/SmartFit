import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Alert, Pressable, Text, View } from "react-native";
import { api, type DashboardDay, type FoodSearchResult } from "@/lib/api";
import { localDateISO, formatKcal, clampPercent } from "@/lib/format";
import { useAuth } from "@/auth/AuthProvider";
import { AppButton, ChoiceRow, ErrorMessage, Field, Muted, PageTitle, Panel, ProgressBar, Screen, SectionTitle } from "@/components/ui";
import { colors } from "@/theme";

type Meal = "breakfast" | "mid_morning" | "lunch" | "snack" | "dinner";
type RecipeSummary = {
  id: number; name: string; description?: string | null; is_system: boolean; food_id: number;
  serving_count: number; serving_g: number; per_serving: { kcal: number; protein_g: number; carbs_g: number; fat_g: number; fiber_g?: number };
  steps: string[];
};
type RecipeIngredient = {
  id: number; food_id: number; food: string; brand?: string | null; quantity_g: number;
  unit_name: string; quantity: number; grams_per_unit: number; kcal: number;
};
type RecipeDetail = RecipeSummary & {
  editable: boolean; ingredients: RecipeIngredient[]; totals?: { kcal: number; protein_g: number; carbs_g: number; fat_g: number };
};
type RecipeDraftIngredient = { food: FoodSearchResult; grams: string };
type BarcodeResult = { status: string; food?: FoodSearchResult | null; name?: string | null; brand?: string | null };

const meals: Array<{ value: Meal; label: string }> = [
  { value: "breakfast", label: "Desayuno" }, { value: "mid_morning", label: "Media mañana" },
  { value: "lunch", label: "Comida" }, { value: "snack", label: "Merienda" }, { value: "dinner", label: "Cena" },
];
function shiftDay(value: string, amount: number) {
  const parts = value.split("-").map(Number);
  const day = new Date(parts[0], parts[1] - 1, parts[2], 12);
  day.setDate(day.getDate() + amount);
  return [day.getFullYear(), String(day.getMonth() + 1).padStart(2, "0"), String(day.getDate()).padStart(2, "0")].join("-");
}
const fmt = (value: number | null | undefined) => value == null ? "—" : Math.round(value).toLocaleString("es-ES");

export default function NutritionScreen() {
  const { token } = useAuth();
  const [section, setSection] = useState<"diary" | "recipes">("diary");
  const [date, setDate] = useState(localDateISO());
  const [data, setData] = useState<DashboardDay | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<FoodSearchResult[]>([]);
  const [grams, setGrams] = useState("100");
  const [meal, setMeal] = useState<Meal>("lunch");
  const [barcode, setBarcode] = useState("");
  const [barcodeResult, setBarcodeResult] = useState<BarcodeResult | null>(null);
  const [recipes, setRecipes] = useState<RecipeSummary[]>([]);
  const [selectedRecipe, setSelectedRecipe] = useState<RecipeDetail | null>(null);
  const [recipeEditName, setRecipeEditName] = useState("");
  const [recipeEditDescription, setRecipeEditDescription] = useState("");
  const [recipeEditServings, setRecipeEditServings] = useState("1");
  const [recipeEditSteps, setRecipeEditSteps] = useState("");
  const [recipeEditAmounts, setRecipeEditAmounts] = useState<Record<number, string>>({});
  const [editingLog, setEditingLog] = useState<{ id: number; grams: string; meal: Meal } | null>(null);
  const [recipeName, setRecipeName] = useState("");
  const [servings, setServings] = useState("1");
  const [recipeFoodQuery, setRecipeFoodQuery] = useState("");
  const [recipeFoodResults, setRecipeFoodResults] = useState<FoodSearchResult[]>([]);
  const [recipeIngredients, setRecipeIngredients] = useState<RecipeDraftIngredient[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setError("");
      setData(await api<DashboardDay>("/dashboard/day?date=" + encodeURIComponent(date), token));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo cargar el diario nutricional.");
    }
  }, [token, date]);

  useEffect(() => { void load(); }, [load]);

  async function loadRecipes() {
    if (!token) return;
    setLoading(true); setError("");
    try {
      const items = await api<RecipeSummary[]>("/recipes?limit=50", token);
      setRecipes(items);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudieron cargar las recetas.");
    } finally { setLoading(false); }
  }

  async function searchFoods() {
    if (!token || !query.trim()) return;
    setLoading(true); setError("");
    try {
      const found = await api<FoodSearchResult[]>("/foods/search?q=" + encodeURIComponent(query.trim()) + "&limit=8&online=false", token);
      setResults(found);
      if (found.length === 0) setError("No encontramos alimentos con ese nombre.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falló la búsqueda.");
    } finally { setLoading(false); }
  }

  async function addFood(food: FoodSearchResult) {
    if (!token) return;
    const quantity = Number(grams.replace(",", "."));
    if (!Number.isFinite(quantity) || quantity <= 0 || quantity > 5000) {
      setError("Introduce una cantidad entre 1 y 5000 gramos.");
      return;
    }
    setLoading(true); setError(""); setNotice("");
    try {
      await api("/logs", token, { method: "POST", body: { food_id: food.id, grams: quantity, meal, log_date: date } });
      setResults([]); setQuery("");
      await load();
      setNotice("Alimento registrado.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo guardar la ingesta.");
    } finally { setLoading(false); }
  }

  async function saveLogEdit() {
    if (!token || !editingLog) return;
    const quantity = Number(editingLog.grams.replace(",", "."));
    if (!Number.isFinite(quantity) || quantity <= 0 || quantity > 5000) {
      setError("Introduce una cantidad entre 1 y 5000 gramos.");
      return;
    }
    setLoading(true); setError("");
    try {
      await api("/logs/" + editingLog.id, token, { method: "PUT", body: { grams: quantity, meal: editingLog.meal } });
      setEditingLog(null);
      await load();
      setNotice("Registro actualizado.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo actualizar el registro.");
    } finally { setLoading(false); }
  }

  async function deleteLog(id: number) {
    if (!token) return;
    Alert.alert("Eliminar alimento", "¿Quieres eliminar este registro del diario?", [
      { text: "Cancelar", style: "cancel" },
      { text: "Eliminar", style: "destructive", onPress: () => {
        void (async () => {
          setLoading(true);
          try { await api("/logs/" + id, token, { method: "DELETE" }); await load(); }
          catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo eliminar el registro."); }
          finally { setLoading(false); }
        })();
      } },
    ]);
  }

  async function findBarcode() {
    if (!token || !barcode.trim()) return;
    setLoading(true); setError(""); setBarcodeResult(null);
    try {
      const result = await api<BarcodeResult>("/foods/barcode/" + encodeURIComponent(barcode.trim()), token);
      setBarcodeResult(result);
      if (!result.food) setError("No se encontró un alimento asociado a ese código.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo consultar el código de barras.");
    } finally { setLoading(false); }
  }

  async function searchRecipeFoods() {
    if (!token || !recipeFoodQuery.trim()) return;
    setLoading(true); setError("");
    try {
      setRecipeFoodResults(await api<FoodSearchResult[]>("/foods/search?q=" + encodeURIComponent(recipeFoodQuery.trim()) + "&limit=8&online=false", token));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudieron buscar ingredientes.");
    } finally { setLoading(false); }
  }

  function addRecipeIngredient(food: FoodSearchResult) {
    setRecipeIngredients(current => current.some(item => item.food.id === food.id)
      ? current : [...current, { food, grams: "100" }]);
  }

  async function createRecipe() {
    if (!token) return;
    if (!recipeName.trim() || recipeIngredients.length === 0) {
      setError("Indica un nombre y al menos un ingrediente.");
      return;
    }
    const ingredients = recipeIngredients.map(item => ({ food_id: item.food.id, quantity_g: Number(item.grams), unit_name: "g" }));
    if (ingredients.some(item => !Number.isFinite(item.quantity_g) || item.quantity_g <= 0 || item.quantity_g > 5000)) {
      setError("Cada ingrediente debe tener una cantidad entre 1 y 5000 gramos.");
      return;
    }
    const count = Number(servings);
    if (!Number.isFinite(count) || count <= 0 || count > 100) {
      setError("El número de raciones debe estar entre 0 y 100.");
      return;
    }
    setLoading(true); setError(""); setNotice("");
    try {
      const created = await api<RecipeDetail>("/recipes", token, { method: "POST", body: {
        name: recipeName.trim(), description: null, serving_count: count, steps: [], ingredients,
      } });
      setRecipeName(""); setRecipeIngredients([]); setRecipeFoodQuery(""); setRecipeFoodResults([]);
      await loadRecipes();
      setSelectedRecipe(created); setRecipeEditName(created.name); setRecipeEditDescription(created.description ?? "");
      setRecipeEditServings(String(created.serving_count)); setRecipeEditSteps(created.steps.join("\n"));
      setRecipeEditAmounts(Object.fromEntries(created.ingredients.map(item => [item.id, String(item.quantity_g)])));
      setNotice("Receta creada y disponible en tu cuenta.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo crear la receta.");
    } finally { setLoading(false); }
  }

  async function openRecipe(recipe: RecipeSummary) {
    if (!token) return;
    setLoading(true); setError("");
    try {
      const detail = await api<RecipeDetail>("/recipes/" + recipe.id, token);
      setSelectedRecipe(detail);
      setRecipeEditName(detail.name);
      setRecipeEditDescription(detail.description ?? "");
      setRecipeEditServings(String(detail.serving_count));
      setRecipeEditSteps(detail.steps.join("\n"));
      setRecipeEditAmounts(Object.fromEntries(detail.ingredients.map(item => [item.id, String(item.quantity_g)])));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo abrir la receta."); }
    finally { setLoading(false); }
  }

  async function saveRecipeEdits() {
    if (!token || !selectedRecipe?.editable) return;
    const count = Number(recipeEditServings);
    const ingredients = selectedRecipe.ingredients.map(item => ({
      food_id: item.food_id,
      quantity_g: Number(recipeEditAmounts[item.id] ?? item.quantity_g),
      unit_name: "g",
    }));
    if (!recipeEditName.trim() || !Number.isFinite(count) || count <= 0 || count > 100 ||
        ingredients.some(item => !Number.isFinite(item.quantity_g) || item.quantity_g <= 0 || item.quantity_g > 5000)) {
      setError("Revisa el nombre, las raciones y las cantidades de los ingredientes.");
      return;
    }
    setLoading(true); setError(""); setNotice("");
    try {
      const updated = await api<RecipeDetail>("/recipes/" + selectedRecipe.id, token, { method: "PUT", body: {
        name: recipeEditName.trim(), description: recipeEditDescription.trim() || null,
        serving_count: count, steps: recipeEditSteps.split("\n").map(step => step.trim()).filter(Boolean),
        ingredients,
      } });
      setSelectedRecipe(updated);
      setRecipeEditAmounts(Object.fromEntries(updated.ingredients.map(item => [item.id, String(item.quantity_g)])));
      await loadRecipes();
      setNotice("Receta actualizada.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo guardar la receta.");
    } finally { setLoading(false); }
  }

  async function logRecipe(recipe: RecipeSummary) {
    if (!token) return;
    const count = Number(servings);
    if (!Number.isFinite(count) || count <= 0 || count > 50) {
      setError("Indica entre 0 y 50 raciones para registrar.");
      return;
    }
    setLoading(true); setError(""); setNotice("");
    try {
      await api("/recipes/" + recipe.id + "/log", token, { method: "POST", body: { servings: count, meal, log_date: date } });
      setSection("diary");
      await load();
      setNotice("Ración registrada en tu diario.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo registrar la receta.");
    } finally { setLoading(false); }
  }

  async function copyRecipe(recipe: RecipeSummary) {
    if (!token) return;
    setLoading(true); setError("");
    try {
      const copy = await api<RecipeDetail>("/recipes/" + recipe.id + "/copy", token, { method: "POST" });
      await loadRecipes();
      setSelectedRecipe(copy); setRecipeEditName(copy.name); setRecipeEditDescription(copy.description ?? "");
      setRecipeEditServings(String(copy.serving_count)); setRecipeEditSteps(copy.steps.join("\n"));
      setRecipeEditAmounts(Object.fromEntries(copy.ingredients.map(item => [item.id, String(item.quantity_g)])));
      setNotice("Copia personal creada. Ya puedes editarla.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo copiar la receta.");
    } finally { setLoading(false); }
  }

  async function deleteRecipe(recipe: RecipeSummary) {
    if (!token) return;
    Alert.alert("Eliminar receta", "¿Quieres eliminar «" + recipe.name + "»?", [
      { text: "Cancelar", style: "cancel" },
      { text: "Eliminar", style: "destructive", onPress: () => {
        void (async () => {
          setLoading(true);
          try {
            await api("/recipes/" + recipe.id, token, { method: "DELETE" });
            if (selectedRecipe?.id === recipe.id) setSelectedRecipe(null);
            await loadRecipes();
          } catch (reason) {
            setError(reason instanceof Error ? reason.message : "No se pudo eliminar la receta.");
          } finally { setLoading(false); }
        })();
      } },
    ]);
  }

  const totals = data?.totals;
  const target = data?.targets;
  const recipePreview = recipeIngredients.reduce((sum, item) => {
    const gramsValue = Number(item.grams) || 0;
    return {
      kcal: sum.kcal + item.food.kcal * gramsValue / 100,
      protein_g: sum.protein_g + item.food.protein_g * gramsValue / 100,
      carbs_g: sum.carbs_g + item.food.carbs_g * gramsValue / 100,
      fat_g: sum.fat_g + item.food.fat_g * gramsValue / 100,
    };
  }, { kcal: 0, protein_g: 0, carbs_g: 0, fat_g: 0 });

  return <Screen>
    <PageTitle eyebrow="Nutrición" title="Alimenta tu progreso" subtitle="Diario de alimentos y recetas, sincronizados con tu cuenta." />
    <ChoiceRow value={section} onChange={value => { setSection(value); setError(""); if (value === "recipes") void loadRecipes(); }} options={[
      { value: "diary", label: "Diario" }, { value: "recipes", label: "Recetas" },
    ]} />
    <ErrorMessage message={error} />
    {notice ? <Text style={{ color: colors.accent, fontSize: 13 }}>{notice}</Text> : null}
    <Panel>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "baseline" }}>
        <Text style={{ color: colors.text, fontSize: 26, fontWeight: "900" }}>{formatKcal(totals?.kcal)} kcal</Text>
        <Muted>de {formatKcal(target?.kcal)} kcal</Muted>
      </View>
      <ProgressBar value={clampPercent(totals?.kcal ?? 0, target?.kcal ?? 0)} />
      <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 5 }}>
        <Muted>Proteína {Math.round(totals?.protein_g ?? 0)} g</Muted>
        <Muted>Carbos {Math.round(totals?.carbs_g ?? 0)} g</Muted>
        <Muted>Grasas {Math.round(totals?.fat_g ?? 0)} g</Muted>
      </View>
    </Panel>

    {section === "diary" ? <>
      <Panel>
        <Text style={{ color: colors.text, fontWeight: "800", fontSize: 16 }}>Día seleccionado · {date}</Text>
        <View style={{ flexDirection: "row", gap: 8 }}>
          <View style={{ flex: 1 }}><AppButton title="← Día anterior" variant="secondary" onPress={() => setDate(value => shiftDay(value, -1))} /></View>
          <View style={{ flex: 1 }}><AppButton title="Volver a hoy" variant="quiet" onPress={() => setDate(localDateISO())} disabled={date === localDateISO()} /></View>
        </View>
      </Panel>
      <SectionTitle title="Añadir alimento" />
      <Panel>
        <Field label="Buscar en el catálogo" value={query} onChangeText={setQuery} placeholder="Ej. avena, plátano, yogur…" returnKeyType="search" onSubmitEditing={() => void searchFoods()} />
        <Field label="Cantidad (g)" value={grams} onChangeText={setGrams} keyboardType="decimal-pad" />
        <ChoiceRow value={meal} onChange={setMeal} options={meals} />
        <AppButton title="Buscar alimentos" onPress={() => void searchFoods()} loading={loading} disabled={!query.trim()} />
        {results.map(food => <Pressable key={food.id} onPress={() => void addFood(food)} style={{ borderTopWidth: 1, borderColor: colors.border, paddingTop: 12, gap: 4 }}>
          <Text style={{ color: colors.text, fontWeight: "800" }}>{food.name}</Text>
          <Muted>{food.brand ? food.brand + " · " : ""}{Math.round(food.kcal)} kcal / 100 g · {Math.round(food.protein_g)} g proteína</Muted>
          <Text style={{ color: colors.accent, fontWeight: "800", fontSize: 12 }}>Añadir {grams} g</Text>
        </Pressable>)}
      </Panel>
      <SectionTitle title="Buscar código de barras" />
      <Panel>
        <Field label="Código EAN/UPC" value={barcode} onChangeText={setBarcode} keyboardType="number-pad" placeholder="Introduce el código del envase" />
        <AppButton title="Consultar código" onPress={() => void findBarcode()} loading={loading} disabled={!barcode.trim()} variant="secondary" />
        {barcodeResult ? <View style={{ gap: 6 }}>
          <Text style={{ color: colors.text, fontWeight: "800" }}>{barcodeResult.food?.name ?? barcodeResult.name ?? "Producto encontrado"}</Text>
          {barcodeResult.food ? <AppButton title={"Añadir " + barcodeResult.food.name} onPress={() => void addFood(barcodeResult.food!)} /> : null}
        </View> : null}
        <Muted>La consulta manual está disponible. El escaneo directo con la cámara requiere integrar el módulo de cámara nativo.</Muted>
      </Panel>
      <SectionTitle title="Comidas registradas" action={(data?.entries?.length ?? 0) + " registros"} />
      <Panel>
        {data?.entries?.length ? data.entries.map(entry => <View key={entry.id} style={{ paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.border, gap: 4 }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 8 }}>
            <Text style={{ color: colors.text, fontWeight: "700", flex: 1 }}>{entry.food}</Text>
            <Text style={{ color: colors.accent, fontWeight: "800" }}>{Math.round(entry.kcal)} kcal</Text>
          </View>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <Muted>{entry.time} · {entry.grams} g · {entry.meal}</Muted>
            <View style={{ flexDirection: "row", gap: 12 }}>
              <Text onPress={() => setEditingLog({ id: entry.id, grams: String(entry.grams), meal: meals.some(item => item.value === entry.meal) ? entry.meal as Meal : "lunch" })} style={{ color: colors.accent, fontWeight: "700", padding: 5 }}>Editar</Text>
              <Text onPress={() => deleteLog(entry.id)} style={{ color: colors.danger, fontWeight: "700", padding: 5 }}>Eliminar</Text>
            </View>
          </View>
        </View>) : <Muted>Todavía no has registrado ninguna comida este día.</Muted>}
        {editingLog ? <View style={{ gap: 9, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12 }}>
          <SectionTitle title="Editar registro" />
          <Field label="Cantidad (g)" value={editingLog.grams} onChangeText={value => setEditingLog(current => current ? { ...current, grams: value } : current)} keyboardType="decimal-pad" />
          <ChoiceRow value={editingLog.meal} onChange={value => setEditingLog(current => current ? { ...current, meal: value } : current)} options={meals} />
          <AppButton title="Guardar cambios" onPress={() => void saveLogEdit()} loading={loading} />
          <AppButton title="Cancelar" onPress={() => setEditingLog(null)} variant="quiet" />
        </View> : null}
      </Panel>
      <AppButton title="Actualizar resumen" variant="quiet" onPress={() => void load()} />
    </> : null}

    {section === "recipes" ? <>
      <SectionTitle title="Tus recetas" action={recipes.length + " recetas"} />
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {recipes.map(recipe => <Panel key={recipe.id}>
        <Pressable onPress={() => void openRecipe(recipe)} style={{ gap: 5 }}>
          <Text style={{ color: colors.text, fontWeight: "900", fontSize: 16 }}>{recipe.name}</Text>
          <Muted>{recipe.description || (recipe.is_system ? "Receta del catálogo SmartFit" : "Receta personal")} · {recipe.serving_count} raciones</Muted>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
            <Text style={{ color: colors.accent, fontWeight: "800" }}>{fmt(recipe.per_serving?.kcal)} kcal/ración</Text>
            <Muted>P {fmt(recipe.per_serving?.protein_g)} g · C {fmt(recipe.per_serving?.carbs_g)} g · G {fmt(recipe.per_serving?.fat_g)} g</Muted>
          </View>
        </Pressable>
        <View style={{ flexDirection: "row", gap: 7 }}>
          <View style={{ flex: 1 }}><AppButton title="Ver receta" variant="secondary" onPress={() => void openRecipe(recipe)} /></View>
          <View style={{ flex: 1 }}><AppButton title="Registrar" onPress={() => void logRecipe(recipe)} loading={loading} /></View>
        </View>
        {recipe.is_system ? <AppButton title="Crear mi copia" variant="quiet" onPress={() => void copyRecipe(recipe)} loading={loading} /> : <Text onPress={() => deleteRecipe(recipe)} style={{ color: colors.danger, fontWeight: "700", padding: 6 }}>Eliminar receta</Text>}
      </Panel>)}
      {selectedRecipe ? <Panel>
        <SectionTitle title={selectedRecipe.name} action={selectedRecipe.editable ? "Receta personal" : "Catálogo"} />
        {selectedRecipe.description ? <Muted>{selectedRecipe.description}</Muted> : null}
        <Muted>{selectedRecipe.serving_count} raciones · {fmt(selectedRecipe.per_serving?.kcal)} kcal por ración</Muted>
        {selectedRecipe.editable ? <>
          <Field label="Nombre" value={recipeEditName} onChangeText={setRecipeEditName} />
          <Field label="Descripción" value={recipeEditDescription} onChangeText={setRecipeEditDescription} multiline numberOfLines={2} />
          <Field label="Número de raciones" value={recipeEditServings} onChangeText={setRecipeEditServings} keyboardType="decimal-pad" />
          <Field label="Pasos (uno por línea)" value={recipeEditSteps} onChangeText={setRecipeEditSteps} multiline numberOfLines={4} />
        </> : null}
        {selectedRecipe.ingredients.map(item => <View key={item.id} style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 7 }}>
          <Text style={{ color: colors.text, fontWeight: "700", flex: 1 }}>{item.food}</Text>
          {selectedRecipe.editable
            ? <Field label="Cantidad (g)" value={recipeEditAmounts[item.id] ?? String(item.quantity_g)} onChangeText={value => setRecipeEditAmounts(current => ({ ...current, [item.id]: value }))} keyboardType="decimal-pad" />
            : <Muted>{fmt(item.quantity_g)} g</Muted>}
        </View>)}
        {selectedRecipe.steps.map((step, index) => !selectedRecipe.editable ? <Muted key={index}>{index + 1}. {step}</Muted> : null)}
        {selectedRecipe.editable ? <AppButton title="Guardar cambios de receta" onPress={() => void saveRecipeEdits()} loading={loading} /> : null}
        <Text onPress={() => setSelectedRecipe(null)} style={{ color: colors.accent, fontWeight: "800" }}>Cerrar detalle</Text>
      </Panel> : null}
      <SectionTitle title="Crear receta" />
      <Panel>
        <Field label="Nombre de la receta" value={recipeName} onChangeText={setRecipeName} placeholder="Ej. Bowl de yogur y avena" />
        <Field label="Número de raciones" value={servings} onChangeText={setServings} keyboardType="decimal-pad" />
        <Field label="Buscar ingrediente" value={recipeFoodQuery} onChangeText={setRecipeFoodQuery} placeholder="Busca un alimento…" returnKeyType="search" onSubmitEditing={() => void searchRecipeFoods()} />
        <AppButton title="Buscar ingredientes" variant="secondary" onPress={() => void searchRecipeFoods()} loading={loading} disabled={!recipeFoodQuery.trim()} />
        {recipeFoodResults.map(food => <Pressable key={food.id} onPress={() => addRecipeIngredient(food)} style={{ borderTopWidth: 1, borderColor: colors.border, paddingTop: 9 }}>
          <Text style={{ color: colors.text, fontWeight: "800" }}>{food.name}</Text>
          <Muted>{fmt(food.kcal)} kcal / 100 g · {food.brand ?? "Catálogo SmartFit"}</Muted>
          <Text style={{ color: colors.accent, fontWeight: "800" }}>＋ Añadir ingrediente</Text>
        </Pressable>)}
        {recipeIngredients.map(item => <View key={item.food.id} style={{ borderTopWidth: 1, borderColor: colors.border, paddingTop: 9, gap: 6 }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <Text style={{ color: colors.text, fontWeight: "800", flex: 1 }}>{item.food.name}</Text>
            <Text onPress={() => setRecipeIngredients(current => current.filter(x => x.food.id !== item.food.id))} style={{ color: colors.danger, padding: 5 }}>Quitar</Text>
          </View>
          <Field label="Cantidad (g)" value={item.grams} onChangeText={value => setRecipeIngredients(current => current.map(x => x.food.id === item.food.id ? { ...x, grams: value } : x))} keyboardType="decimal-pad" />
        </View>)}
        {recipeIngredients.length ? <View style={{ gap: 4 }}>
          <Muted>Estimación por receta completa: {fmt(recipePreview.kcal)} kcal · proteína {fmt(recipePreview.protein_g)} g · hidratos {fmt(recipePreview.carbs_g)} g · grasas {fmt(recipePreview.fat_g)} g</Muted>
          <AppButton title="Guardar receta" onPress={() => void createRecipe()} loading={loading} />
        </View> : null}
      </Panel>
      <Muted>Las recetas del catálogo se pueden copiar a tu cuenta. La edición detallada de ingredientes y pasos queda disponible en la versión web; desde móvil puedes crear recetas nuevas, consultarlas y registrar raciones.</Muted>
    </> : null}
  </Screen>;
}
