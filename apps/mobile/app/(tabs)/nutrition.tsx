import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Alert, Pressable, Text, View } from "react-native";
import { api, apiUpload, type DashboardDay, type FoodSearchResult } from "@/lib/api";
import { localDateISO, formatKcal, clampPercent } from "@/lib/format";
import { useAuth } from "@/auth/AuthProvider";
import { AppButton, ChoiceRow, ErrorMessage, Field, Muted, PageTitle, Panel, ProgressBar, Screen, SectionTitle } from "@/components/ui";
import { colors } from "@/theme";

type Meal = "breakfast" | "mid_morning" | "lunch" | "snack" | "dinner";
type OwnedFood = {
  id: number; name: string; brand?: string | null; barcode?: string | null; serving_g?: number | null;
  kcal: number; protein_g: number; carbs_g: number; sugars_g: number; fat_g: number;
  sat_fat_g: number; fiber_g: number; sodium_mg: number; times_used: number; share_status: string;
};
type FoodDraft = {
  name: string; brand: string; barcode: string; serving_g: string; kcal: string; protein_g: string;
  carbs_g: string; sugars_g: string; fat_g: string; sat_fat_g: string; fiber_g: string; sodium_mg: string;
};
const emptyFoodDraft = (): FoodDraft => ({
  name: "", brand: "", barcode: "", serving_g: "100", kcal: "0", protein_g: "0",
  carbs_g: "0", sugars_g: "0", fat_g: "0", sat_fat_g: "0", fiber_g: "0", sodium_mg: "0",
});
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
type FoodEstimate = {
  name: string; items: Array<{
    name: string; grams: number; kcal_per_100g: number; protein_g_per_100g: number;
    carbs_g_per_100g: number; sugars_g_per_100g: number; fat_g_per_100g: number;
    sat_fat_g_per_100g: number; fiber_g_per_100g: number; sodium_mg_per_100g: number;
    confidence: "low" | "medium";
  }>;
  assumptions: string[]; total_grams: number; confidence: "low" | "medium";
  per_100g: Record<string, number>;
};

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
  const [section, setSection] = useState<"diary" | "recipes" | "foods">("diary");
  const [date, setDate] = useState(localDateISO());
  const [data, setData] = useState<DashboardDay | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<FoodSearchResult[]>([]);
  const [grams, setGrams] = useState("100");
  const [meal, setMeal] = useState<Meal>("lunch");
  const [barcode, setBarcode] = useState("");
  const [barcodeResult, setBarcodeResult] = useState<BarcodeResult | null>(null);
  const [estimateDescription, setEstimateDescription] = useState("");
  const [estimateResult, setEstimateResult] = useState<FoodEstimate | null>(null);
  const [recipes, setRecipes] = useState<RecipeSummary[]>([]);
  const [ownedFoods, setOwnedFoods] = useState<OwnedFood[]>([]);
  const [foodDraft, setFoodDraft] = useState<FoodDraft>(emptyFoodDraft());
  const [editingFoodId, setEditingFoodId] = useState<number | null>(null);
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
  const [recipeEstimateName, setRecipeEstimateName] = useState("");
  const [recipeEstimateDescription, setRecipeEstimateDescription] = useState("");
  const [recipeEstimateSteps, setRecipeEstimateSteps] = useState("");
  const [recipeEstimateResult, setRecipeEstimateResult] = useState<FoodEstimate | null>(null);
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

  async function loadOwnedFoods() {
    if (!token) return;
    setLoading(true); setError("");
    try {
      setOwnedFoods(await api<OwnedFood[]>("/foods/mine?limit=100", token));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudieron cargar tus alimentos.");
    } finally { setLoading(false); }
  }

  function editOwnedFood(food: OwnedFood) {
    setEditingFoodId(food.id);
    setFoodDraft({
      name: food.name, brand: food.brand ?? "", barcode: food.barcode ?? "",
      serving_g: food.serving_g == null ? "" : String(food.serving_g),
      kcal: String(food.kcal), protein_g: String(food.protein_g), carbs_g: String(food.carbs_g),
      sugars_g: String(food.sugars_g), fat_g: String(food.fat_g), sat_fat_g: String(food.sat_fat_g),
      fiber_g: String(food.fiber_g), sodium_mg: String(food.sodium_mg),
    });
    setNotice("");
  }

  async function saveOwnedFood() {
    if (!token) return;
    if (!foodDraft.name.trim()) {
      setError("El nombre del alimento es obligatorio.");
      return;
    }
    const values = {
      name: foodDraft.name.trim(), brand: foodDraft.brand.trim() || null,
      barcode: foodDraft.barcode.trim() || null,
      serving_g: foodDraft.serving_g.trim() ? Number(foodDraft.serving_g.replace(",", ".")) : null,
      kcal: Number(foodDraft.kcal), protein_g: Number(foodDraft.protein_g),
      carbs_g: Number(foodDraft.carbs_g), sugars_g: Number(foodDraft.sugars_g),
      fat_g: Number(foodDraft.fat_g), sat_fat_g: Number(foodDraft.sat_fat_g),
      fiber_g: Number(foodDraft.fiber_g), sodium_mg: Number(foodDraft.sodium_mg),
    };
    const numeric = [values.kcal, values.protein_g, values.carbs_g, values.sugars_g, values.fat_g,
      values.sat_fat_g, values.fiber_g, values.sodium_mg, ...(values.serving_g === null ? [] : [values.serving_g])];
    if (numeric.some(value => !Number.isFinite(value) || value < 0) ||
        (values.serving_g !== null && values.serving_g <= 0) ||
        values.protein_g + values.carbs_g + values.fat_g > 105 ||
        values.sugars_g > values.carbs_g + 0.5 || values.sat_fat_g > values.fat_g + 0.5) {
      setError("Revisa los nutrientes: no pueden ser negativos y los macronutrientes deben ser coherentes.");
      return;
    }
    setLoading(true); setError(""); setNotice("");
    try {
      if (editingFoodId === null) {
        await api("/foods", token, { method: "POST", body: { ...values, share: false } });
      } else {
        await api("/foods/" + editingFoodId, token, { method: "PUT", body: values });
      }
      setFoodDraft(emptyFoodDraft());
      setEditingFoodId(null);
      await loadOwnedFoods();
      setNotice(editingFoodId === null ? "Alimento personalizado creado." : "Alimento actualizado.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo guardar el alimento.");
    } finally { setLoading(false); }
  }

  async function toggleFoodSharing(food: OwnedFood) {
    if (!token) return;
    setLoading(true); setError(""); setNotice("");
    try {
      if (food.share_status !== "private") {
        await api("/foods/" + food.id + "/share", token, { method: "DELETE" });
        setNotice("Se ha retirado el alimento de la comunidad.");
      } else {
        await api("/foods/" + food.id + "/share", token, { method: "POST" });
        setNotice("Alimento enviado al proceso de verificación de la comunidad.");
      }
      await loadOwnedFoods();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo cambiar el estado del alimento.");
    } finally { setLoading(false); }
  }

  async function deleteOwnedFood(food: OwnedFood) {
    if (!token) return;
    Alert.alert("Eliminar alimento", "¿Quieres eliminar «" + food.name + "»? Solo se podrá borrar si no aparece en tu diario ni en tus recetas.", [
      { text: "Cancelar", style: "cancel" },
      { text: "Eliminar", style: "destructive", onPress: () => {
        void (async () => {
          setLoading(true); setError("");
          try {
            await api("/foods/" + food.id, token, { method: "DELETE" });
            if (editingFoodId === food.id) { setEditingFoodId(null); setFoodDraft(emptyFoodDraft()); }
            await loadOwnedFoods();
            setNotice("Alimento eliminado.");
          } catch (reason) {
            setError(reason instanceof Error ? reason.message : "No se pudo eliminar el alimento.");
          } finally { setLoading(false); }
        })();
      } },
    ]);
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

  async function estimateFood() {
    if (!token || !estimateDescription.trim()) return;
    const form = new FormData();
    form.append("description", estimateDescription.trim());
    form.append("method", "description");
    setLoading(true); setError(""); setEstimateResult(null);
    try {
      setEstimateResult(await apiUpload<FoodEstimate>("/foods/estimate", form, token));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo estimar la comida.");
    } finally { setLoading(false); }
  }

  async function confirmEstimate() {
    if (!token || !estimateResult) return;
    const values = estimateResult.per_100g;
    setLoading(true); setError(""); setNotice("");
    try {
      await api("/foods/estimate-log", token, { method: "POST", body: {
        name: estimateResult.name, grams: estimateResult.total_grams, log_date: date, meal,
        method: "description", description: estimateDescription,
        kcal: values.kcal_per_100g, protein_g: values.protein_g_per_100g,
        carbs_g: values.carbs_g_per_100g, sugars_g: values.sugars_g_per_100g,
        fat_g: values.fat_g_per_100g, sat_fat_g: values.sat_fat_g_per_100g,
        fiber_g: values.fiber_g_per_100g, sodium_mg: values.sodium_mg_per_100g,
        components: estimateResult.items,
      } });
      setEstimateResult(null); setEstimateDescription("");
      await load();
      setNotice("Comida estimada revisada y registrada en tu diario.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo confirmar la estimación.");
    } finally { setLoading(false); }
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

  async function estimateRecipe() {
    if (!token || !recipeEstimateName.trim()) {
      setError("Escribe el nombre de la receta antes de estimarla.");
      return;
    }
    setLoading(true); setError(""); setRecipeEstimateResult(null);
    try {
      const result = await api<FoodEstimate>("/recipes/estimate", token, { method: "POST", body: {
        name: recipeEstimateName.trim(),
        description: recipeEstimateDescription.trim(),
        steps: recipeEstimateSteps.split("\\n").map(step => step.trim()).filter(Boolean),
      } });
      setRecipeEstimateResult(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo estimar la receta.");
    } finally { setLoading(false); }
  }

  async function confirmRecipeEstimate() {
    if (!token || !recipeEstimateResult) return;
    const count = Number(servings);
    if (!Number.isFinite(count) || count <= 0 || count > 100) {
      setError("El número de raciones debe estar entre 1 y 100.");
      return;
    }
    setLoading(true); setError(""); setNotice("");
    try {
      const created = await api<RecipeDetail>("/recipes/from-estimate", token, { method: "POST", body: {
        name: recipeEstimateName.trim() || recipeEstimateResult.name,
        description: recipeEstimateDescription.trim() || null,
        serving_count: count,
        steps: recipeEstimateSteps.split("\\n").map(step => step.trim()).filter(Boolean),
        items: recipeEstimateResult.items.map(item => ({
          name: item.name, grams: item.grams, kcal_per_100g: item.kcal_per_100g,
          protein_g_per_100g: item.protein_g_per_100g, carbs_g_per_100g: item.carbs_g_per_100g,
          sugars_g_per_100g: item.sugars_g_per_100g, fat_g_per_100g: item.fat_g_per_100g,
          sat_fat_g_per_100g: item.sat_fat_g_per_100g, fiber_g_per_100g: item.fiber_g_per_100g,
          sodium_mg_per_100g: item.sodium_mg_per_100g, confidence: item.confidence,
          unit_name: "g", quantity: item.grams, grams_per_unit: 1,
        })),
      } });
      setRecipeEstimateResult(null);
      setRecipeEstimateName(""); setRecipeEstimateDescription(""); setRecipeEstimateSteps("");
      await loadRecipes();
      await openRecipe({ id: created.id, name: created.name, description: created.description, is_system: false,
        food_id: created.food_id, serving_count: created.serving_count, serving_g: created.serving_g,
        per_serving: created.per_serving, steps: created.steps });
      setNotice("Receta estimada, revisada y guardada. Puedes editar sus ingredientes antes de volver a registrarla.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo guardar la receta estimada.");
    } finally { setLoading(false); }
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
    <ChoiceRow value={section} onChange={value => { setSection(value); setError(""); if (value === "recipes") void loadRecipes(); if (value === "foods") void loadOwnedFoods(); }} options={[
      { value: "diary", label: "Diario" }, { value: "recipes", label: "Recetas" }, { value: "foods", label: "Mis alimentos" },
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
      <SectionTitle title="Estimar comida con IA" />
      <Panel>
        <Muted>Describe el plato y la IA propondrá ingredientes, cantidades y nutrientes aproximados. Revisa la estimación antes de guardarla.</Muted>
        <Field label="Descripción de la comida" value={estimateDescription} onChangeText={setEstimateDescription} multiline numberOfLines={3} maxLength={2000} placeholder="Ej. Un plato de arroz con pollo, verduras y aceite de oliva…" />
        <AppButton title="Estimar nutrientes" onPress={() => void estimateFood()} loading={loading} disabled={!estimateDescription.trim()} variant="secondary" />
        {estimateResult ? <View style={{ gap: 8 }}>
          <Text style={{ color: colors.text, fontWeight: "900", fontSize: 16 }}>{estimateResult.name}</Text>
          <Text style={{ color: colors.accent, fontWeight: "800" }}>{fmt(estimateResult.total_grams)} g · {fmt(estimateResult.per_100g.kcal_per_100g * estimateResult.total_grams / 100)} kcal estimadas</Text>
          {estimateResult.items.map((item, index) => <View key={index} style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 7 }}>
            <Text style={{ color: colors.text, fontWeight: "700" }}>{item.name} · {fmt(item.grams)} g</Text>
            <Muted>{fmt(item.kcal_per_100g)} kcal/100 g · confianza {item.confidence === "medium" ? "media" : "baja"}</Muted>
          </View>)}
          {estimateResult.assumptions.map((item, index) => <Muted key={index}>• {item}</Muted>)}
          <Muted>La estimación es orientativa, no equivale a un análisis de laboratorio.</Muted>
          <AppButton title="Confirmar y registrar en el diario" onPress={() => void confirmEstimate()} loading={loading} />
          <AppButton title="Descartar estimación" onPress={() => setEstimateResult(null)} variant="quiet" />
        </View> : null}
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

    {section === "foods" ? <>
      <SectionTitle title="Mis alimentos" action={ownedFoods.length + " personalizados"} />
      <Muted>Crea alimentos propios con sus nutrientes por 100 g. Puedes editarlos, compartirlos con la comunidad o eliminarlos si no están en uso.</Muted>
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {ownedFoods.map(food => <Panel key={food.id}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
          <Text style={{ color: colors.text, fontWeight: "900", fontSize: 15, flex: 1 }}>{food.name}</Text>
          <Text style={{ color: food.share_status === "verified" ? colors.accent : colors.muted, fontSize: 10, fontWeight: "900" }}>
            {food.share_status === "verified" ? "VERIFICADO" : food.share_status === "pending" ? "EN REVISIÓN" : "PRIVADO"}
          </Text>
        </View>
        <Muted>{food.brand ?? "Sin marca"} · {food.times_used} usos</Muted>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 9 }}>
          <Muted>{fmt(food.kcal)} kcal</Muted><Muted>P {fmt(food.protein_g)} g</Muted>
          <Muted>C {fmt(food.carbs_g)} g</Muted><Muted>G {fmt(food.fat_g)} g</Muted>
          <Muted>Fibra {fmt(food.fiber_g)} g</Muted>
        </View>
        <View style={{ flexDirection: "row", gap: 8 }}>
          <View style={{ flex: 1 }}><AppButton title="Editar" variant="secondary" onPress={() => editOwnedFood(food)} /></View>
          <View style={{ flex: 1 }}><AppButton title={food.share_status === "private" ? "Compartir" : "Retirar"} variant="quiet" onPress={() => void toggleFoodSharing(food)} loading={loading} /></View>
        </View>
        <Text onPress={() => deleteOwnedFood(food)} style={{ color: colors.danger, fontWeight: "700", paddingVertical: 5 }}>Eliminar alimento</Text>
      </Panel>)}
      <SectionTitle title={editingFoodId === null ? "Crear alimento" : "Editar alimento"} />
      <Panel>
        <Field label="Nombre" value={foodDraft.name} onChangeText={value => setFoodDraft(current => ({ ...current, name: value }))} placeholder="Ej. Yogur natural casero" />
        <Field label="Marca (opcional)" value={foodDraft.brand} onChangeText={value => setFoodDraft(current => ({ ...current, brand: value }))} />
        <Field label="Código de barras (opcional)" value={foodDraft.barcode} onChangeText={value => setFoodDraft(current => ({ ...current, barcode: value }))} keyboardType="number-pad" />
        <Field label="Tamaño de ración (g, opcional)" value={foodDraft.serving_g} onChangeText={value => setFoodDraft(current => ({ ...current, serving_g: value }))} keyboardType="decimal-pad" />
        <Muted>Nutrientes por 100 g</Muted>
        <Field label="Energía (kcal)" value={foodDraft.kcal} onChangeText={value => setFoodDraft(current => ({ ...current, kcal: value }))} keyboardType="decimal-pad" />
        <Field label="Proteína (g)" value={foodDraft.protein_g} onChangeText={value => setFoodDraft(current => ({ ...current, protein_g: value }))} keyboardType="decimal-pad" />
        <Field label="Carbohidratos (g)" value={foodDraft.carbs_g} onChangeText={value => setFoodDraft(current => ({ ...current, carbs_g: value }))} keyboardType="decimal-pad" />
        <Field label="Azúcares (g)" value={foodDraft.sugars_g} onChangeText={value => setFoodDraft(current => ({ ...current, sugars_g: value }))} keyboardType="decimal-pad" />
        <Field label="Grasas (g)" value={foodDraft.fat_g} onChangeText={value => setFoodDraft(current => ({ ...current, fat_g: value }))} keyboardType="decimal-pad" />
        <Field label="Grasas saturadas (g)" value={foodDraft.sat_fat_g} onChangeText={value => setFoodDraft(current => ({ ...current, sat_fat_g: value }))} keyboardType="decimal-pad" />
        <Field label="Fibra (g)" value={foodDraft.fiber_g} onChangeText={value => setFoodDraft(current => ({ ...current, fiber_g: value }))} keyboardType="decimal-pad" />
        <Field label="Sodio (mg)" value={foodDraft.sodium_mg} onChangeText={value => setFoodDraft(current => ({ ...current, sodium_mg: value }))} keyboardType="decimal-pad" />
        <AppButton title={editingFoodId === null ? "Guardar alimento" : "Guardar cambios"} onPress={() => void saveOwnedFood()} loading={loading} disabled={!foodDraft.name.trim()} />
        {editingFoodId !== null ? <AppButton title="Cancelar edición" onPress={() => { setEditingFoodId(null); setFoodDraft(emptyFoodDraft()); }} variant="quiet" /> : null}
      </Panel>
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
      <SectionTitle title="Estimar receta con IA" />
      <Panel>
        <Muted>Describe la receta y sus pasos. SmartFit propondrá ingredientes, cantidades y nutrientes aproximados. Revisa la propuesta antes de guardarla.</Muted>
        <Field label="Nombre de la receta" value={recipeEstimateName} onChangeText={setRecipeEstimateName} placeholder="Ej. Lasaña de verduras" />
        <Field label="Descripción e ingredientes conocidos" value={recipeEstimateDescription} onChangeText={setRecipeEstimateDescription} multiline numberOfLines={3} placeholder="Ingredientes, cantidades aproximadas o características…" />
        <Field label="Pasos de preparación (uno por línea)" value={recipeEstimateSteps} onChangeText={setRecipeEstimateSteps} multiline numberOfLines={3} />
        <AppButton title="Estimar ingredientes" onPress={() => void estimateRecipe()} loading={loading} disabled={!recipeEstimateName.trim()} variant="secondary" />
        {recipeEstimateResult ? <View style={{ gap: 8 }}>
          <Text style={{ color: colors.text, fontWeight: "900", fontSize: 16 }}>{recipeEstimateResult.name}</Text>
          <Text style={{ color: colors.accent, fontWeight: "800" }}>{fmt(recipeEstimateResult.total_grams)} g · {fmt(recipeEstimateResult.totals.kcal)} kcal en total</Text>
          {recipeEstimateResult.items.map((item, index) => <View key={index} style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 7 }}>
            <Text style={{ color: colors.text, fontWeight: "700" }}>{item.name} · {fmt(item.grams)} g</Text>
            <Muted>{fmt(item.kcal_per_100g)} kcal/100 g · confianza {item.confidence === "medium" ? "media" : "baja"}</Muted>
          </View>)}
          {recipeEstimateResult.assumptions.map((item, index) => <Muted key={index}>• {item}</Muted>)}
          <Muted>Los nutrientes y cantidades son orientativos. Se guardarán como alimentos privados estimados por IA.</Muted>
          <AppButton title="Confirmar y guardar receta" onPress={() => void confirmRecipeEstimate()} loading={loading} />
          <AppButton title="Descartar propuesta" onPress={() => setRecipeEstimateResult(null)} variant="quiet" />
        </View> : null}
      </Panel>
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
