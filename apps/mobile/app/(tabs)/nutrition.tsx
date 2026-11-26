import React, { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Alert, Image, Linking, Platform, Pressable, Text, View } from "react-native";
import * as ImagePicker from "expo-image-picker";
import { AudioModule, RecordingPresets, setAudioModeAsync, useAudioRecorder, useAudioRecorderState } from "expo-audio";
import { api, apiUpload, type DashboardDay, type FoodSearchResult } from "@/lib/api";
import { localDateISO, formatKcal, clampPercent } from "@/lib/format";
import { useAuth } from "@/auth/AuthProvider";
import { AppButton, ChoiceRow, ErrorMessage, Field, Muted, PageTitle, Panel, ProgressBar, Screen, SectionTitle } from "@/components/ui";
import { colors } from "@/theme";
import { BarcodeScanner } from "@/components/BarcodeScanner";

type Meal = "auto" | "breakfast" | "mid_morning" | "lunch" | "snack" | "dinner";
type FrequentFood = { food: FoodSearchResult; times: number; typical_grams: number; last_logged?: string };
type FoodDetail = FoodSearchResult & {
  source?: string; user_id?: number | null; barcode?: string | null; serving_g?: number | null; image_url?: string | null;
  nutriscore_grade?: string | null; nova_group?: number | null; ecoscore_grade?: string | null;
  sugars_g?: number | null; sat_fat_g?: number | null; fiber_g?: number | null; sodium_mg?: number | null;
  serving_size?: string | null; labels?: string[]; allergens?: string[]; ingredients?: string | null;
  categories?: string[]; attribution?: string | null; license?: string | null;
};
type OwnedFoodUnit = { id: number; food_id: number; unit_name: string; unit_name_plural?: string | null; grams_per_unit: number; description?: string | null };
type FoodServing = OwnedFoodUnit;
type OwnedFood = {
  id: number; name: string; brand?: string | null; barcode?: string | null; serving_g?: number | null;
  kcal: number; protein_g: number; carbs_g: number; sugars_g: number; fat_g: number;
  sat_fat_g: number; fiber_g: number; sodium_mg: number; times_used: number; share_status: string;
};
type FoodCatalogSection = { id: string; title: string; description?: string; icon?: string; count: number; foods: FoodSearchResult[] };
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
type RecipeDraftIngredient = { food: FoodSearchResult; quantity: string; unit_name: string; grams_per_unit: string };
type RecipeUnitOption = { value: string; label: string; factor: number };
const recipeUnits: RecipeUnitOption[] = [
  { value: "g", label: "Gramos", factor: 1 }, { value: "ml", label: "Mililitros", factor: 1 },
  { value: "cucharada", label: "Cucharadas", factor: 15 }, { value: "cucharadita", label: "Cucharaditas", factor: 5 },
  { value: "unidad", label: "Unidades", factor: 50 }, { value: "trozo", label: "Trozos", factor: 50 },
  { value: "taza", label: "Tazas", factor: 240 }, { value: "rebanada", label: "Rebanadas", factor: 30 },
  { value: "loncha", label: "Lonchas", factor: 20 },
];
type BarcodeResult = { status: string; food?: FoodSearchResult | null; name?: string | null; brand?: string | null };
type FoodEstimate = {
  name: string; items: Array<{
    name: string; grams: number; kcal_per_100g: number; protein_g_per_100g: number;
    carbs_g_per_100g: number; sugars_g_per_100g: number; fat_g_per_100g: number;
    sat_fat_g_per_100g: number; fiber_g_per_100g: number; sodium_mg_per_100g: number;
    confidence: "low" | "medium";
  }>;
  assumptions: string[]; total_grams: number; confidence: "low" | "medium";
  totals: { kcal: number; protein_g: number; carbs_g: number; sugars_g: number; fat_g: number; sat_fat_g: number; fiber_g: number; sodium_mg: number };
  per_100g: Record<string, number>;
  method?: "description" | "photo" | "audio";
};

const meals: Array<{ value: Meal; label: string }> = [
  { value: "auto", label: "✨ Automática" }, { value: "breakfast", label: "☀️ Desayuno" }, { value: "mid_morning", label: "🍎 Almuerzo" },
  { value: "lunch", label: "🍽️ Comida" }, { value: "snack", label: "☕ Merienda" }, { value: "dinner", label: "🌙 Cena" },
];
function shiftDay(value: string, amount: number) {
  const parts = value.split("-").map(Number);
  const day = new Date(parts[0], parts[1] - 1, parts[2], 12);
  day.setDate(day.getDate() + amount);
  return [day.getFullYear(), String(day.getMonth() + 1).padStart(2, "0"), String(day.getDate()).padStart(2, "0")].join("-");
}
const normalizeFoodQuery = (value: string) => value.toLocaleLowerCase("es").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
const fmt = (value: number | null | undefined) => value == null ? "—" : Math.round(value).toLocaleString("es-ES");

export default function NutritionScreen() {
  const { token } = useAuth();
  const [section, setSection] = useState<"diary" | "recipes" | "foods" | "catalog">("diary");
  const [date, setDate] = useState(localDateISO());
  const [data, setData] = useState<DashboardDay | null>(null);
  const [frequentFoods, setFrequentFoods] = useState<FrequentFood[]>([]);
  const [query, setQuery] = useState("");
  const [foodSearchSource, setFoodSearchSource] = useState<"generic" | "openfoodfacts">("generic");
  const [foodEntryMode, setFoodEntryMode] = useState<"smartfit" | "openfoodfacts" | "estimate" | "barcode">("smartfit");
  const [results, setResults] = useState<FoodSearchResult[]>([]);
  const [selectedFood, setSelectedFood] = useState<FoodSearchResult | null>(null);
  const [selectedFoodDetail, setSelectedFoodDetail] = useState<FoodDetail | null>(null);
  const [foodServings, setFoodServings] = useState<FoodServing[]>([]);
  const [selectedFoodUnit, setSelectedFoodUnit] = useState("grams");
  const [foodQuantity, setFoodQuantity] = useState("100");
  const [grams, setGrams] = useState("100");
  const [meal, setMeal] = useState<Meal>("lunch");
  const [barcode, setBarcode] = useState("");
  const [barcodeResult, setBarcodeResult] = useState<BarcodeResult | null>(null);
  const [barcodeScannerVisible, setBarcodeScannerVisible] = useState(false);
  const [estimatePhoto, setEstimatePhoto] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [voiceNoteUri, setVoiceNoteUri] = useState<string | null>(null);
  const voiceRecorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const voiceRecorderState = useAudioRecorderState(voiceRecorder, 400);
  const wasRecording = useRef(false);
  const [estimateCapabilities, setEstimateCapabilities] = useState<{ description: boolean; photo: boolean; audio: boolean } | null>(null);
  const [estimateDescription, setEstimateDescription] = useState("");
  const [estimateResult, setEstimateResult] = useState<FoodEstimate | null>(null);
  const [recipes, setRecipes] = useState<RecipeSummary[]>([]);
  const [ownedFoods, setOwnedFoods] = useState<OwnedFood[]>([]);
  const [catalogSections, setCatalogSections] = useState<FoodCatalogSection[]>([]);
  const [catalogCategory, setCatalogCategory] = useState("");
  const [catalogQuery, setCatalogQuery] = useState("");
  const [foodDraft, setFoodDraft] = useState<FoodDraft>(emptyFoodDraft());
  const [editingFoodId, setEditingFoodId] = useState<number | null>(null);
  const [ownedFoodUnits, setOwnedFoodUnits] = useState<OwnedFoodUnit[]>([]);
  const [unitName, setUnitName] = useState("");
  const [unitPlural, setUnitPlural] = useState("");
  const [unitGrams, setUnitGrams] = useState("");
  const [unitDescription, setUnitDescription] = useState("");
  const [selectedRecipe, setSelectedRecipe] = useState<RecipeDetail | null>(null);
  const [recipeEditName, setRecipeEditName] = useState("");
  const [recipeEditDescription, setRecipeEditDescription] = useState("");
  const [recipeEditServings, setRecipeEditServings] = useState("1");
  const [recipeEditSteps, setRecipeEditSteps] = useState("");
  const [recipeEditAmounts, setRecipeEditAmounts] = useState<Record<number, string>>({});
  const [recipeEditUnits, setRecipeEditUnits] = useState<Record<number, { quantity: string; unit_name: string; grams_per_unit: string }>>({});
  const [recipePreview, setRecipePreview] = useState<{ serving_g: number; per_serving: { kcal: number; protein_g: number; carbs_g: number; fat_g: number; fiber_g?: number } } | null>(null);
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
      const [day, frequent] = await Promise.all([
        api<DashboardDay>("/dashboard/day?date=" + encodeURIComponent(date), token),
        api<FrequentFood[]>("/logs/frequent?limit=8&days=60", token),
      ]);
      setData(day);
      setFrequentFoods(frequent);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo cargar el diario nutricional.");
    }
  }, [token, date]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!token || recipeIngredients.length === 0) {
      setRecipePreview(null);
      return;
    }
    let active = true;
    const handle = setTimeout(() => {
      void api<{ serving_g: number; per_serving: { kcal: number; protein_g: number; carbs_g: number; fat_g: number; fiber_g?: number } }>("/recipes/preview", token, {
        method: "POST", body: {
          serving_count: Number(servings) || 1,
          ingredients: recipeIngredientPayload.map(item => ({
            food_id: item.food_id, quantity_g: item.quantity_g, unit_name: item.unit_name,
            quantity: item.quantity, grams_per_unit: item.grams_per_unit,
          })),
        },
      }).then(result => { if (active) setRecipePreview(result); })
        .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "No se pudo calcular el resumen de la receta."); });
    }, 350);
    return () => { active = false; clearTimeout(handle); };
  }, [token, recipeIngredients, servings]);

  useEffect(() => {
    if (wasRecording.current && !voiceRecorderState.isRecording && !voiceNoteUri && voiceRecorder.uri) {
      setVoiceNoteUri(voiceRecorder.uri);
    }
    wasRecording.current = voiceRecorderState.isRecording;
  }, [voiceRecorderState.isRecording, voiceRecorder, voiceNoteUri]);

  useEffect(() => {
    if (!token) return;
    void api<{ description: boolean; photo: boolean; audio: boolean }>("/foods/estimate-capabilities", token)
      .then(setEstimateCapabilities)
      .catch(() => setEstimateCapabilities({ description: true, photo: false, audio: false }));
  }, [token]);

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

  async function loadCatalog() {
    if (!token) return;
    setLoading(true); setError("");
    try {
      const result = await api<{ sections: FoodCatalogSection[] }>("/foods/catalog", token);
      setCatalogSections(result.sections);
      setCatalogCategory(current => result.sections.some(item => item.id === current) ? current : "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo cargar el catálogo de alimentos.");
    } finally { setLoading(false); }
  }

  const loadSmartFitSearchData = useCallback(async () => {
    if (!token) return;
    setLoading(true); setError("");
    try {
      const [catalog, recipeItems, personalFoods] = await Promise.all([
        api<{ sections: FoodCatalogSection[] }>("/foods/catalog", token),
        api<RecipeSummary[]>("/recipes?limit=50", token),
        api<OwnedFood[]>("/foods/mine?limit=100", token),
      ]);
      setCatalogSections(catalog.sections);
      setCatalogCategory(current => catalog.sections.some(item => item.id === current) ? current : "");
      setRecipes(recipeItems);
      setOwnedFoods(personalFoods);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo cargar la búsqueda de alimentos y recetas.");
    } finally { setLoading(false); }
  }, [token]);

  useEffect(() => {
    if (token && ((section === "diary" && foodEntryMode === "smartfit") || section === "catalog")) {
      if (!catalogSections.length || !recipes.length || !ownedFoods.length) void loadSmartFitSearchData();
    }
  }, [token, section, foodEntryMode, catalogSections.length, recipes.length, ownedFoods.length, loadSmartFitSearchData]);

  async function loadOwnedFoods() {
    if (!token) return;
    setLoading(true); setError("");
    try {
      setOwnedFoods(await api<OwnedFood[]>("/foods/mine?limit=100", token));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudieron cargar tus alimentos.");
    } finally { setLoading(false); }
  }

  async function editOwnedFood(food: OwnedFood) {
    if (!token) return;
    setEditingFoodId(food.id);
    setFoodDraft({
      name: food.name, brand: food.brand ?? "", barcode: food.barcode ?? "",
      serving_g: food.serving_g == null ? "" : String(food.serving_g),
      kcal: String(food.kcal), protein_g: String(food.protein_g), carbs_g: String(food.carbs_g),
      sugars_g: String(food.sugars_g), fat_g: String(food.fat_g), sat_fat_g: String(food.sat_fat_g),
      fiber_g: String(food.fiber_g), sodium_mg: String(food.sodium_mg),
    });
    setNotice("");
    try {
      setOwnedFoodUnits(await api<OwnedFoodUnit[]>("/foods/" + food.id + "/servings", token));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudieron cargar las unidades habituales.");
    }
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
        const created = await api<OwnedFood>("/foods", token, { method: "POST", body: { ...values, share: false } });
        setEditingFoodId(created.id);
        setOwnedFoodUnits([]);
        await loadOwnedFoods();
        setNotice("Alimento creado. Puedes añadir ahora sus unidades habituales.");
      } else {
        await api("/foods/" + editingFoodId, token, { method: "PUT", body: values });
        await loadOwnedFoods();
        setNotice("Alimento actualizado.");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo guardar el alimento.");
    } finally { setLoading(false); }
  }

  async function addOwnedFoodUnit() {
    if (!token || editingFoodId === null) return;
    const gramsValue = Number(unitGrams.replace(",", "."));
    if (!unitName.trim() || !Number.isFinite(gramsValue) || gramsValue <= 0 || gramsValue > 5000) {
      setError("Indica el nombre de la unidad y su equivalencia entre 0 y 5000 gramos.");
      return;
    }
    setLoading(true); setError(""); setNotice("");
    try {
      const unit = await api<OwnedFoodUnit>("/foods/" + editingFoodId + "/servings", token, {
        method: "POST", body: {
          unit_name: unitName.trim(), unit_name_plural: unitPlural.trim() || null,
          grams_per_unit: gramsValue, description: unitDescription.trim() || null,
        },
      });
      setOwnedFoodUnits(current => [...current, unit].sort((a, b) => b.grams_per_unit - a.grams_per_unit));
      setUnitName(""); setUnitPlural(""); setUnitGrams(""); setUnitDescription("");
      setNotice("Unidad habitual añadida.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo añadir la unidad.");
    } finally { setLoading(false); }
  }

  async function deleteOwnedFoodUnit(unit: OwnedFoodUnit) {
    if (!token || editingFoodId === null) return;
    setLoading(true); setError("");
    try {
      await api("/foods/" + editingFoodId + "/servings/" + unit.id, token, { method: "DELETE" });
      setOwnedFoodUnits(current => current.filter(item => item.id !== unit.id));
      setNotice("Unidad eliminada.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo eliminar la unidad.");
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

  const searchFoods = useCallback(async () => {
    if (!token || !query.trim() || foodEntryMode !== "openfoodfacts") { setResults([]); return; }
    setLoading(true); setError("");
    try {
      const params = new URLSearchParams({
        q: query.trim(), limit: "12",
        online: foodSearchSource === "openfoodfacts" ? "true" : "false",
        source: foodSearchSource,
      });
      const found = await api<FoodSearchResult[]>("/foods/search?" + params.toString(), token);
      setResults(found);
      if (found.length === 0) setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falló la búsqueda.");
      setResults([]);
    } finally { setLoading(false); }
  }, [token, query, foodSearchSource, foodEntryMode]);

  useEffect(() => {
    const canSearch = section === "diary" && foodEntryMode === "openfoodfacts" && query.trim().length > 0;
    if (!canSearch) { setResults([]); return; }
    const timer = setTimeout(() => { void searchFoods(); }, 400);
    return () => clearTimeout(timer);
  }, [searchFoods, section, foodEntryMode]);

  async function openFoodForLogging(food: FoodSearchResult, initialQuantity = grams) {
    if (!token) return;
    setSelectedFood(food);
    setResults([]);
    setSelectedFoodDetail(null);
    setFoodQuantity(initialQuantity);
    setSelectedFoodUnit("grams");
    setFoodServings([]);
    setError("");
    try {
      const [detail, units] = await Promise.all([
        api<FoodDetail>("/foods/" + food.id, token),
        api<FoodServing[]>("/foods/" + food.id + "/servings", token),
      ]);
      setSelectedFoodDetail(detail);
      setFoodServings(units);
      if (detail.serving_g) setFoodQuantity(String(detail.serving_g));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudieron cargar los detalles de este alimento.");
    }
  }

  async function copySelectedFood() {
    if (!token || !selectedFood) return;
    setLoading(true); setError(""); setNotice("");
    try {
      const copy = await api<OwnedFood>("/foods/" + selectedFood.id + "/copy", token, { method: "POST", body: {} });
      setSelectedFood(null);
      setSelectedFoodDetail(null);
      setSection("foods");
      await loadOwnedFoods();
      await editOwnedFood(copy);
      setNotice("Copia personal creada. El alimento original permanece intacto.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo crear una copia del alimento.");
    } finally { setLoading(false); }
  }

  async function addSelectedFood() {
    if (!token || !selectedFood) return;
    const quantity = Number(foodQuantity.replace(",", "."));
    const usingUnit = selectedFoodUnit !== "grams";
    if (!Number.isFinite(quantity) || quantity <= 0 || quantity > (usingUnit ? 1000 : 5000)) {
      setError(usingUnit ? "La cantidad debe estar entre 0 y 1000 unidades." : "La cantidad debe estar entre 1 y 5000 gramos.");
      return;
    }
    setLoading(true); setError(""); setNotice("");
    try {
      const body = usingUnit
        ? { food_id: selectedFood.id, serving_id: Number(selectedFoodUnit), quantity, meal: meal === "auto" ? null : meal, log_date: date }
        : { food_id: selectedFood.id, grams: quantity, meal: meal === "auto" ? null : meal, log_date: date };
      await api("/logs", token, { method: "POST", body });
      setSelectedFood(null); setFoodServings([]); setFoodQuantity("100");
      setResults([]); setQuery("");
      await load();
      setNotice("Alimento registrado en el diario.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo guardar la ingesta.");
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
      await api("/logs", token, { method: "POST", body: { food_id: food.id, grams: quantity, meal: meal === "auto" ? null : meal, log_date: date } });
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

  async function chooseMealPhoto(source: "camera" | "library") {
    setError("");
    try {
      if (source === "camera") {
        const permission = await ImagePicker.requestCameraPermissionsAsync();
        if (!permission.granted) {
          setError("Necesitas permitir el acceso a la cámara para fotografiar la comida.");
          return;
        }
      }
      const options: ImagePicker.ImagePickerOptions = {
        mediaTypes: ["images"], allowsEditing: true, aspect: [4, 3], quality: 0.85,
      };
      const result = source === "camera"
        ? await ImagePicker.launchCameraAsync(options)
        : await ImagePicker.launchImageLibraryAsync(options);
      if (!result.canceled && result.assets[0]) {
        setEstimatePhoto(result.assets[0]);
        setEstimateResult(null);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo abrir la cámara o la galería.");
    }
  }

  async function startVoiceNote() {
    if (estimateCapabilities?.audio === false) {
      setError("La transcripción de audio no está configurada en el servidor.");
      return;
    }
    setError("");
    try {
      const permission = await AudioModule.requestRecordingPermissionsAsync();
      if (!permission.granted) {
        setError("Necesitas permitir el acceso al micrófono para grabar una nota de voz.");
        return;
      }
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
      await voiceRecorder.prepareToRecordAsync();
      setVoiceNoteUri(null);
      voiceRecorder.record({ forDuration: 120 });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo iniciar la grabación.");
    }
  }

  async function stopVoiceNote() {
    try {
      await voiceRecorder.stop();
      setVoiceNoteUri(voiceRecorder.uri);
      await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo finalizar la grabación.");
    }
  }

  async function transcribeVoiceNote() {
    if (!token || !voiceNoteUri) return;
    setLoading(true); setError(""); setNotice("");
    try {
      const form = new FormData();
      if (Platform.OS === "web") {
        const response = await fetch(voiceNoteUri);
        const blob = await response.blob();
        form.append("audio", blob, "nota-de-voz.webm");
      } else {
        form.append("audio", {
          uri: voiceNoteUri,
          name: "nota-de-voz.m4a",
          type: "audio/mp4",
        } as unknown as Blob);
      }
      const result = await apiUpload<{ transcript: string }>("/foods/transcribe-audio", form, token);
      setEstimateDescription(current => current.trim() ? current.trim() + "\n" + result.transcript : result.transcript);
      setVoiceNoteUri(null);
      setNotice("Nota de voz transcrita. Revisa el texto y pulsa «Estimar nutrientes».");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo transcribir la nota de voz.");
    } finally { setLoading(false); }
  }

  async function estimateFood() {
    if (!token || (!estimateDescription.trim() && !estimatePhoto)) {
      setError("Describe la comida o adjunta una fotografía.");
      return;
    }
    if (estimatePhoto && estimateCapabilities?.photo === false) {
      setError("La estimación por fotografía no está activada en el servidor. Puedes continuar describiendo la comida.");
      return;
    }
    const form = new FormData();
    form.append("description", estimateDescription.trim());
    form.append("method", estimatePhoto ? "photo" : "description");
    if (estimatePhoto) {
      if (Platform.OS === "web") {
        const response = await fetch(estimatePhoto.uri);
        const blob = await response.blob();
        form.append("image", blob, estimatePhoto.fileName ?? "comida.jpg");
      } else {
        form.append("image", {
          uri: estimatePhoto.uri,
          name: estimatePhoto.fileName ?? "comida.jpg",
          type: estimatePhoto.mimeType ?? "image/jpeg",
        } as unknown as Blob);
      }
    }
    setLoading(true); setError(""); setNotice(""); setEstimateResult(null);
    try {
      setEstimateResult(await apiUpload<FoodEstimate>("/foods/estimate", form, token));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo estimar la comida.");
    } finally { setLoading(false); }
  }

  function recalculateFoodEstimate(items: FoodEstimate["items"], original: FoodEstimate): FoodEstimate {
    const total_grams = items.reduce((sum, item) => sum + (Number.isFinite(item.grams) ? item.grams : 0), 0);
    const totals = {
      kcal: items.reduce((sum, item) => sum + item.kcal_per_100g * item.grams / 100, 0),
      protein_g: items.reduce((sum, item) => sum + item.protein_g_per_100g * item.grams / 100, 0),
      carbs_g: items.reduce((sum, item) => sum + item.carbs_g_per_100g * item.grams / 100, 0),
      sugars_g: items.reduce((sum, item) => sum + item.sugars_g_per_100g * item.grams / 100, 0),
      fat_g: items.reduce((sum, item) => sum + item.fat_g_per_100g * item.grams / 100, 0),
      sat_fat_g: items.reduce((sum, item) => sum + item.sat_fat_g_per_100g * item.grams / 100, 0),
      fiber_g: items.reduce((sum, item) => sum + item.fiber_g_per_100g * item.grams / 100, 0),
      sodium_mg: items.reduce((sum, item) => sum + item.sodium_mg_per_100g * item.grams / 100, 0),
    };
    const factor = total_grams > 0 ? 100 / total_grams : 0;
    return {
      ...original,
      items,
      total_grams,
      totals,
      per_100g: {
        kcal_per_100g: totals.kcal * factor,
        protein_g_per_100g: totals.protein_g * factor,
        carbs_g_per_100g: totals.carbs_g * factor,
        sugars_g_per_100g: totals.sugars_g * factor,
        fat_g_per_100g: totals.fat_g * factor,
        sat_fat_g_per_100g: totals.sat_fat_g * factor,
        fiber_g_per_100g: totals.fiber_g * factor,
        sodium_mg_per_100g: totals.sodium_mg * factor,
      },
    };
  }

  function updateEstimateItem(index: number, patch: Partial<FoodEstimate["items"][number]>) {
    setEstimateResult(current => current
      ? recalculateFoodEstimate(current.items.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item), current)
      : current);
  }

  function removeEstimateItem(index: number) {
    setEstimateResult(current => current
      ? recalculateFoodEstimate(current.items.filter((_, itemIndex) => itemIndex !== index), current)
      : current);
  }

  async function confirmEstimate() {
    if (!token || !estimateResult) return;
    if (estimateResult.items.length === 0 || estimateResult.items.some(item =>
      !item.name.trim() || !Number.isFinite(item.grams) || item.grams <= 0 || item.grams > 5000) ||
      estimateResult.total_grams <= 0 || estimateResult.total_grams > 5000) {
      setError("Revisa los ingredientes: debe quedar al menos uno y las cantidades deben sumar entre 1 y 5000 gramos.");
      return;
    }
    const values = estimateResult.per_100g;
    setLoading(true); setError(""); setNotice("");
    try {
      await api("/foods/estimate-log", token, { method: "POST", body: {
        name: estimateResult.name, grams: estimateResult.total_grams, log_date: date, meal: meal === "auto" ? null : meal,
        method: estimateResult.method ?? (estimatePhoto ? "photo" : "description"), description: estimateDescription,
        kcal: values.kcal_per_100g, protein_g: values.protein_g_per_100g,
        carbs_g: values.carbs_g_per_100g, sugars_g: values.sugars_g_per_100g,
        fat_g: values.fat_g_per_100g, sat_fat_g: values.sat_fat_g_per_100g,
        fiber_g: values.fiber_g_per_100g, sodium_mg: values.sodium_mg_per_100g,
        components: estimateResult.items,
      } });
      setEstimateResult(null); setEstimateDescription(""); setEstimatePhoto(null);
      await load();
      setNotice("Comida estimada revisada y registrada en tu diario.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo confirmar la estimación.");
    } finally { setLoading(false); }
  }

  async function lookupBarcode(code: string) {
    if (!token || !code.trim()) return;
    setBarcode(code.trim());
    setLoading(true); setError(""); setBarcodeResult(null);
    try {
      const result = await api<BarcodeResult>("/foods/barcode/" + encodeURIComponent(code.trim()), token);
      setBarcodeResult(result);
      if (!result.food) setError("No encontramos ese producto. Comprueba el código o búscalo por nombre.");
      else setNotice("Código detectado: " + result.food.name);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo consultar el código de barras.");
    } finally { setLoading(false); }
  }

  async function findBarcode() {
    await lookupBarcode(barcode);
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
      ? current : [...current, { food, quantity: "100", unit_name: "g", grams_per_unit: "1" }]);
  }

  function updateRecipeIngredient(index: number, patch: Partial<RecipeDraftIngredient>) {
    setRecipeIngredients(current => current.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));
  }

  function gramsForIngredient(item: RecipeDraftIngredient): number {
    const quantity = Number(item.quantity.replace(",", "."));
    const factor = Number(item.grams_per_unit.replace(",", "."));
    return Number.isFinite(quantity) && Number.isFinite(factor) ? quantity * factor : Number.NaN;
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
        steps: recipeEstimateSteps.split("\n").map(step => step.trim()).filter(Boolean),
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
        steps: recipeEstimateSteps.split("\n").map(step => step.trim()).filter(Boolean),
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
    const ingredients = recipeIngredients.map(item => {
      const quantity = Number(item.quantity.replace(",", "."));
      const gramsPerUnit = Number(item.grams_per_unit.replace(",", "."));
      return {
        food_id: item.food.id, quantity_g: quantity * gramsPerUnit,
        unit_name: item.unit_name, quantity, grams_per_unit: gramsPerUnit,
      };
    });
    if (ingredients.some(item => !Number.isFinite(item.quantity) || item.quantity <= 0 || item.quantity > 5000 ||
      !Number.isFinite(item.grams_per_unit) || item.grams_per_unit <= 0 || item.quantity_g <= 0 || item.quantity_g > 5000)) {
      setError("Revisa las cantidades y equivalencias de cada ingrediente.");
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
      setRecipeEditUnits(Object.fromEntries(created.ingredients.map(item => [item.id, { quantity: String(item.quantity), unit_name: item.unit_name || "g", grams_per_unit: String(item.grams_per_unit || 1) }])));
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
      setRecipeEditUnits(Object.fromEntries(detail.ingredients.map(item => [item.id, { quantity: String(item.quantity), unit_name: item.unit_name || "g", grams_per_unit: String(item.grams_per_unit || 1) }])));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo abrir la receta."); }
    finally { setLoading(false); }
  }

  async function saveRecipeEdits() {
    if (!token || !selectedRecipe?.editable) return;
    const count = Number(recipeEditServings);
    const ingredients = selectedRecipe.ingredients.map(item => {
      const unit = recipeEditUnits[item.id] ?? { quantity: String(item.quantity), unit_name: item.unit_name || "g", grams_per_unit: String(item.grams_per_unit || 1) };
      const quantity = Number(unit.quantity.replace(",", "."));
      const gramsPerUnit = Number(unit.grams_per_unit.replace(",", "."));
      return {
        food_id: item.food_id, quantity_g: quantity * gramsPerUnit,
        unit_name: unit.unit_name, quantity, grams_per_unit: gramsPerUnit,
      };
    });
    if (!recipeEditName.trim() || !Number.isFinite(count) || count <= 0 || count > 100 ||
        ingredients.some(item => !Number.isFinite(item.quantity) || item.quantity <= 0 || !Number.isFinite(item.grams_per_unit) || item.grams_per_unit <= 0 || item.quantity_g <= 0 || item.quantity_g > 5000)) {
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
      setRecipeEditUnits(Object.fromEntries(updated.ingredients.map(item => [item.id, { quantity: String(item.quantity), unit_name: item.unit_name || "g", grams_per_unit: String(item.grams_per_unit || 1) }])));
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
      await api("/recipes/" + recipe.id + "/log", token, { method: "POST", body: { servings: count, meal: meal === "auto" ? null : meal, log_date: date } });
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
      setRecipeEditUnits(Object.fromEntries(copy.ingredients.map(item => [item.id, { quantity: String(item.quantity), unit_name: item.unit_name || "g", grams_per_unit: String(item.grams_per_unit || 1) }])));
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

  if (selectedFood) {
    const detail = selectedFoodDetail;
    const imageUrl = detail?.image_url || selectedFood.image_url;
    const isOpenFoodFacts = detail?.source === "openfoodfacts" || selectedFood.source === "openfoodfacts";
    return <Screen>
      <PageTitle eyebrow={isOpenFoodFacts ? "Open Food Facts" : "Alimento"} title={selectedFood.name}
        subtitle={selectedFood.brand || (isOpenFoodFacts ? "Producto envasado" : "Ficha nutricional")} />
      <AppButton title="← Volver al catálogo" variant="quiet" onPress={() => setSelectedFood(null)} />
      <Panel>
        {imageUrl ? <Image source={{ uri: imageUrl }} style={{ width: "100%", height: 210, borderRadius: 14, backgroundColor: colors.surfaceRaised }} resizeMode="contain" /> : null}
        {detail ? <>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
            {detail.nutriscore_grade ? <Muted>Nutri-Score {detail.nutriscore_grade.toUpperCase()}</Muted> : null}
            {detail.nova_group ? <Muted>NOVA {detail.nova_group}</Muted> : null}
            {detail.ecoscore_grade ? <Muted>Eco-Score {detail.ecoscore_grade.toUpperCase()}</Muted> : null}
          </View>
          {detail.serving_size ? <Muted>Ración indicada: {detail.serving_size}</Muted> : null}
          {detail.labels?.length ? <Muted>Etiquetas: {detail.labels.join(", ")}</Muted> : null}
          {detail.allergens?.length ? <Muted>Alérgenos: {detail.allergens.join(", ")}</Muted> : null}
          {detail.ingredients ? <Muted>Ingredientes: {detail.ingredients}</Muted> : null}
          {isOpenFoodFacts && detail.barcode
            ? <Text onPress={() => void Linking.openURL("https://world.openfoodfacts.org/product/" + encodeURIComponent(detail.barcode!))}
                style={{ color: colors.accent, fontWeight: "800" }}>Ver ficha original en Open Food Facts ↗</Text>
            : null}
        </> : <ActivityIndicator color={colors.accent} />}
        <View style={{ borderTopWidth: 1, borderColor: colors.border, paddingTop: 12, gap: 7 }}>
          <Text style={{ color: colors.text, fontWeight: "900", fontSize: 16 }}>Información nutricional · por 100 g</Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 12 }}>
            <Muted>{fmt(selectedFood.kcal)} kcal</Muted>
            <Muted>Proteína {fmt(selectedFood.protein_g)} g</Muted>
            <Muted>Hidratos {fmt(selectedFood.carbs_g)} g</Muted>
            <Muted>Grasas {fmt(selectedFood.fat_g)} g</Muted>
            {detail?.sugars_g != null ? <Muted>Azúcares {fmt(detail.sugars_g)} g</Muted> : null}
            {detail?.sat_fat_g != null ? <Muted>Saturadas {fmt(detail.sat_fat_g)} g</Muted> : null}
            {detail?.fiber_g != null ? <Muted>Fibra {fmt(detail.fiber_g)} g</Muted> : null}
            {detail?.sodium_mg != null ? <Muted>Sodio {fmt(detail.sodium_mg)} mg</Muted> : null}
          </View>
        </View>
        {detail?.user_id == null ? <AppButton title="Crear mi versión editable" variant="quiet" onPress={() => void copySelectedFood()} loading={loading} /> : null}
        <Text style={{ color: colors.text, fontWeight: "800" }}>Unidad de medida</Text>
        <ChoiceRow value={selectedFoodUnit} onChange={setSelectedFoodUnit} options={[
          { value: "grams", label: "Gramos" },
          ...foodServings.map(unit => ({ value: String(unit.id), label: unit.unit_name_plural || unit.unit_name })),
        ]} />
        <Field label={selectedFoodUnit === "grams" ? "Cantidad (g)" : "Número de unidades"}
          value={foodQuantity} onChangeText={setFoodQuantity} keyboardType="decimal-pad" />
        {selectedFoodUnit !== "grams" ? <Muted>
          1 {foodServings.find(item => String(item.id) === selectedFoodUnit)?.unit_name ?? "unidad"} = {fmt(foodServings.find(item => String(item.id) === selectedFoodUnit)?.grams_per_unit)} g
        </Muted> : null}
        <Text style={{ color: colors.text, fontWeight: "800" }}>Comida del día</Text>
        <ChoiceRow value={meal} onChange={setMeal} options={meals} />
        <AppButton title="Añadir al diario" onPress={() => void addSelectedFood()} loading={loading} />
        <AppButton title="Cancelar" onPress={() => setSelectedFood(null)} variant="quiet" />
      </Panel>
    </Screen>;
  }

  const smartFitFilter = normalizeFoodQuery(query.trim());
  const filteredSmartFitSections = catalogSections.map(item => ({
    ...item,
    foods: smartFitFilter
      ? item.foods.filter(food => normalizeFoodQuery([food.name, food.brand ?? ""].join(" ")).includes(smartFitFilter))
      : item.foods,
  })).filter(item => !smartFitFilter || item.foods.length > 0);

  const catalogFilter = normalizeFoodQuery(catalogQuery.trim());
  const filteredCatalogSections = catalogSections.map(item => ({
    ...item,
    foods: catalogFilter
      ? item.foods.filter(food => normalizeFoodQuery([food.name, food.brand ?? ""].join(" ")).includes(catalogFilter))
      : item.foods,
  })).filter(item => !catalogFilter || item.foods.length > 0);
  const activeSmartFitFilter = section === "catalog" ? catalogFilter : smartFitFilter;
  const filteredSmartFitRecipes = recipes.filter(recipe => recipe.is_system &&
    normalizeFoodQuery([recipe.name, recipe.description ?? ""].join(" ")).includes(activeSmartFitFilter));
  const filteredPersonalFoods = ownedFoods.filter(food =>
    normalizeFoodQuery([food.name, food.brand ?? ""].join(" ")).includes(activeSmartFitFilter));


  const totals = data?.totals;
  const target = data?.targets;
  const recipePreviewLocal = recipeIngredients.reduce((sum, item) => {
    const gramsValue = gramsForIngredient(item);
    return {
      kcal: sum.kcal + item.food.kcal * gramsValue / 100,
      protein_g: sum.protein_g + item.food.protein_g * gramsValue / 100,
      carbs_g: sum.carbs_g + item.food.carbs_g * gramsValue / 100,
      fat_g: sum.fat_g + item.food.fat_g * gramsValue / 100,
    };
  }, { kcal: 0, protein_g: 0, carbs_g: 0, fat_g: 0 });
  const recipeIngredientPayload = recipeIngredients.map(item => ({
    food_id: item.food.id, quantity_g: gramsForIngredient(item),
    unit_name: item.unit_name, quantity: Number(item.quantity), grams_per_unit: Number(item.grams_per_unit),
  }));

  return <Screen>
    <PageTitle eyebrow="Nutrición" title="Alimenta tu progreso" subtitle="Diario de alimentos y recetas, sincronizados con tu cuenta." />
    <ChoiceRow value={section} onChange={value => { setSection(value); setError(""); if (value === "recipes") void loadRecipes(); if (value === "foods") void loadOwnedFoods(); if (value === "catalog") void loadSmartFitSearchData(); }} options={[
      { value: "diary", label: "Diario" }, { value: "catalog", label: "Buscar" }, { value: "recipes", label: "Recetas" }, { value: "foods", label: "Mis alimentos" },
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
        <Text style={{ color: colors.text, fontWeight: "800" }}>¿Cómo quieres añadirlo?</Text>
        <ChoiceRow value={foodEntryMode} onChange={value => {
          setFoodEntryMode(value);
          setFoodSearchSource(value === "openfoodfacts" ? "openfoodfacts" : "generic");
          setQuery(""); setResults([]); setError("");
        }} options={[
          { value: "smartfit", label: "🥗 Catálogo SmartFit" },
          { value: "openfoodfacts", label: "📦 OpenFoodFacts" },
          { value: "estimate", label: "✦ Estimar con IA" },
          { value: "barcode", label: "📷 Código" },
        ]} />
        <Text style={{ color: colors.text, fontWeight: "700" }}>Comida del día</Text>
        <ChoiceRow value={meal} onChange={setMeal} options={meals} />
        {(foodEntryMode === "smartfit" || foodEntryMode === "openfoodfacts") ? <>
          <Field
            label={foodEntryMode === "openfoodfacts" ? "Buscar producto de marca" : "Buscar en el catálogo SmartFit"}
            value={query}
            onChangeText={value => { setQuery(value); setCatalogCategory(""); setResults([]); }}
            placeholder={foodEntryMode === "openfoodfacts" ? "Ej. yogur Danone, avena Hacendado…" : "Ej. avena, plátano, yogur…"}
            returnKeyType="search"
            onSubmitEditing={() => void searchFoods()}
          />
          <Muted>{foodEntryMode === "openfoodfacts"
            ? "Resultados de Open Food Facts con fotografía del envase cuando está disponible."
            : "Los resultados se filtran mientras escribes; no necesitas pulsar Buscar."}</Muted>
          {foodEntryMode === "smartfit" ? <>
            {loading && !catalogSections.length ? <ActivityIndicator color={colors.accent} /> : null}
            <View style={{ gap: 8 }}>
              {filteredSmartFitSections.map(item => {
                const expanded = item.id === catalogCategory;
                return <Panel key={item.id}>
                  <Pressable onPress={() => setCatalogCategory(current => current === item.id ? "" : item.id)}
                    style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
                    <Text style={{ fontSize: 25 }}>{item.icon || "🥗"}</Text>
                    <View style={{ flex: 1, gap: 2 }}>
                      <Text style={{ color: colors.text, fontWeight: "900" }}>{item.title}</Text>
                      {item.description ? <Muted>{item.description}</Muted> : null}
                    </View>
                    <Muted>{item.foods.length} alimentos</Muted>
                    <Text style={{ color: colors.accent, fontWeight: "900", fontSize: 18 }}>{expanded ? "−" : "+"}</Text>
                  </Pressable>
                  {expanded ? <View style={{ marginTop: 9 }}>
                    {item.foods.map(food => <Pressable key={food.id} onPress={() => void openFoodForLogging(food)} style={{
                      flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 9,
                      borderTopWidth: 1, borderColor: colors.border,
                    }}>
                      {food.image_url
                        ? <Image source={{ uri: food.image_url }} style={{ width: 44, height: 44, borderRadius: 9, backgroundColor: colors.surfaceRaised }} resizeMode="contain" />
                        : <Text style={{ fontSize: 22 }}>{food.icon || item.icon || "🥗"}</Text>}
                      <View style={{ flex: 1, gap: 2 }}>
                        <Text style={{ color: colors.text, fontWeight: "800" }}>{food.name}</Text>
                        <Muted>{food.brand ?? "Alimento genérico"} · {fmt(food.kcal)} kcal/100 g</Muted>
                      </View>
                      <Text style={{ color: colors.accent, fontWeight: "900" }}>›</Text>
                    </Pressable>)}
                  </View> : null}
                </Panel>;
              })}
            </View>
            {!loading && smartFitFilter && !filteredSmartFitSections.length
              ? <Muted>No hay alimentos que coincidan con «{query}».</Muted> : null}
            {!smartFitFilter ? <Muted>Selecciona una categoría para explorar sus alimentos. Escribe arriba para filtrar productos en todas las categorías.</Muted> : null}
            <Panel>
              <Pressable onPress={() => setCatalogCategory(current => current === "__smartfit_recipes" ? "" : "__smartfit_recipes")}
                style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
                <Text style={{ fontSize: 25 }}>🍲</Text>
                <View style={{ flex: 1, gap: 2 }}>
                  <Text style={{ color: colors.text, fontWeight: "900" }}>Recetas SmartFit</Text>
                  <Muted>Recetas oficiales disponibles para registrar</Muted>
                </View>
                <Muted>{filteredSmartFitRecipes.length} recetas</Muted>
                <Text style={{ color: colors.accent, fontWeight: "900", fontSize: 18 }}>{catalogCategory === "__smartfit_recipes" ? "−" : "+"}</Text>
              </Pressable>
              {catalogCategory === "__smartfit_recipes" ? <View style={{ marginTop: 9 }}>
                {filteredSmartFitRecipes.map(recipe => <View key={"recipe-" + recipe.id} style={{ borderTopWidth: 1, borderColor: colors.border, paddingTop: 9, gap: 7 }}>
                  <Pressable onPress={() => void openRecipe(recipe)} style={{ gap: 4 }}>
                    <Text style={{ color: colors.text, fontWeight: "900" }}>{recipe.name}</Text>
                    <Muted>{recipe.description || "Receta del catálogo SmartFit"} · {fmt(recipe.per_serving?.kcal)} kcal/ración</Muted>
                    <Text style={{ color: colors.accent, fontWeight: "800" }}>Ver receta ›</Text>
                  </Pressable>
                  <AppButton title="Registrar receta" variant="secondary" onPress={() => void logRecipe(recipe)} loading={loading} />
                </View>)}
                {!filteredSmartFitRecipes.length ? <Muted>No hay recetas que coincidan con «{query}».</Muted> : null}
              </View> : null}
            </Panel>
            <Panel>
              <Pressable onPress={() => setCatalogCategory(current => current === "__my_personal_foods" ? "" : "__my_personal_foods")}
                style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
                <Text style={{ fontSize: 25 }}>👤</Text>
                <View style={{ flex: 1, gap: 2 }}>
                  <Text style={{ color: colors.text, fontWeight: "900" }}>Mis personalizados</Text>
                  <Muted>Alimentos que has creado para tu cuenta</Muted>
                </View>
                <Muted>{filteredPersonalFoods.length} alimentos</Muted>
                <Text style={{ color: colors.accent, fontWeight: "900", fontSize: 18 }}>{catalogCategory === "__my_personal_foods" ? "−" : "+"}</Text>
              </Pressable>
              {catalogCategory === "__my_personal_foods" ? <View style={{ marginTop: 9 }}>
                {filteredPersonalFoods.map(food => <Pressable key={"personal-" + food.id} onPress={() => void openFoodForLogging({
                  id: food.id, name: food.name, brand: food.brand, kcal: food.kcal, protein_g: food.protein_g,
                  carbs_g: food.carbs_g, fat_g: food.fat_g, source: "personal",
                })} style={{ flexDirection: "row", alignItems: "center", gap: 10, borderTopWidth: 1, borderColor: colors.border, paddingVertical: 9 }}>
                  <Text style={{ fontSize: 22 }}>👤</Text>
                  <View style={{ flex: 1, gap: 2 }}>
                    <Text style={{ color: colors.text, fontWeight: "800" }}>{food.name}</Text>
                    <Muted>{food.brand ?? "Alimento personal"} · {fmt(food.kcal)} kcal/100 g</Muted>
                  </View>
                  <Text style={{ color: colors.accent, fontWeight: "900" }}>›</Text>
                </Pressable>)}
                {!filteredPersonalFoods.length ? <Muted>No hay alimentos personalizados que coincidan con «{query}».</Muted> : null}
              </View> : null}
            </Panel>
            {smartFitFilter && !filteredSmartFitRecipes.length && !filteredPersonalFoods.length && !filteredSmartFitSections.length
              ? <Muted>No hay coincidencias en el catálogo, las recetas SmartFit ni tus personalizados.</Muted> : null}
          </> : <>
            {loading && query.trim() ? <ActivityIndicator color={colors.accent} /> : null}
            {results.map(food => <Pressable key={food.id} onPress={() => void openFoodForLogging(food)} style={{
              flexDirection: "row", alignItems: "center", gap: 11, borderTopWidth: 1,
              borderColor: colors.border, paddingVertical: 10,
            }}>
              {food.image_url
                ? <Image source={{ uri: food.image_url }} style={{ width: 58, height: 58, borderRadius: 10, backgroundColor: colors.surfaceRaised }} resizeMode="contain" />
                : <View style={{ width: 58, height: 58, borderRadius: 10, backgroundColor: colors.surfaceRaised, alignItems: "center", justifyContent: "center" }}>
                    <Text style={{ fontSize: 25 }}>📦</Text>
                  </View>}
              <View style={{ flex: 1, gap: 3 }}>
                <Text style={{ color: colors.text, fontWeight: "800" }}>{food.name}</Text>
                <Muted>{food.brand ? food.brand + " · " : ""}{fmt(food.kcal)} kcal/100 g · P {fmt(food.protein_g)} g</Muted>
                <Text style={{ color: colors.accent, fontSize: 12, fontWeight: "800" }}>Abrir ficha nutricional ›</Text>
              </View>
            </Pressable>)}
            {!query.trim() ? <Muted>Empieza a escribir para ver coincidencias al instante.</Muted> : null}
            {!!query.trim() && !loading && !results.length ? <Muted>No hay coincidencias con ese nombre.</Muted> : null}
          </>}
        </> : null}
      </Panel>
      {foodEntryMode === "estimate" ? <>
      <SectionTitle title="Estimar comida con IA" />
      <Panel>
        <Muted>Describe el plato o adjunta una foto. SmartFit propondrá ingredientes, cantidades y nutrientes aproximados. Revisa la estimación antes de guardarla.</Muted>
        <Field label="Descripción (opcional con foto)" value={estimateDescription} onChangeText={setEstimateDescription} multiline numberOfLines={3} maxLength={2000} placeholder="Ej. Arroz con pollo, verduras y aceite de oliva…" />
        <View style={{ flexDirection: "row", gap: 8 }}>
          <View style={{ flex: 1 }}><AppButton
            title={voiceRecorderState.isRecording ? "Grabando…" : "Grabar nota de voz"}
            onPress={() => void startVoiceNote()} loading={loading}
            disabled={voiceRecorderState.isRecording || estimateCapabilities?.audio === false}
            variant="secondary"
          /></View>
          <View style={{ flex: 1 }}><AppButton
            title="Detener grabación"
            onPress={() => void stopVoiceNote()}
            disabled={!voiceRecorderState.isRecording}
            variant="quiet"
          /></View>
        </View>
        {voiceRecorderState.isRecording ? <Muted>Grabando {Math.floor(voiceRecorderState.durationMillis / 1000)} s · máximo 120 s</Muted> : null}
        {voiceNoteUri ? <View style={{ gap: 6 }}>
          <Muted>Nota de voz preparada ({Math.round(voiceRecorderState.durationMillis / 1000)} s).</Muted>
          <AppButton title="Transcribir nota de voz" onPress={() => void transcribeVoiceNote()} loading={loading} />
          <Text onPress={() => setVoiceNoteUri(null)} style={{ color: colors.danger, fontWeight: "800", padding: 5 }}>Descartar audio</Text>
        </View> : null}
        {estimateCapabilities?.audio === false ? <Muted>La transcripción de audio no está habilitada en este servidor.</Muted> : null}
        <View style={{ flexDirection: "row", gap: 8 }}>
          <View style={{ flex: 1 }}><AppButton title="Hacer foto" variant="secondary" onPress={() => void chooseMealPhoto("camera")} loading={loading} /></View>
          <View style={{ flex: 1 }}><AppButton title="Galería" variant="secondary" onPress={() => void chooseMealPhoto("library")} loading={loading} /></View>
        </View>
        {estimatePhoto ? <View style={{ gap: 6 }}>
          <Image source={{ uri: estimatePhoto.uri }} style={{ width: "100%", height: 190, borderRadius: 12, backgroundColor: colors.surfaceRaised }} resizeMode="cover" />
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <Muted>{estimatePhoto.fileName ?? "Foto seleccionada"}</Muted>
            <Text onPress={() => { setEstimatePhoto(null); setEstimateResult(null); }} style={{ color: colors.danger, fontWeight: "800", padding: 6 }}>Quitar foto</Text>
          </View>
        </View> : null}
        {estimateCapabilities?.photo === false ? <Muted>El servidor no tiene activada la estimación visual. Puedes seguir usando la estimación por descripción.</Muted> : null}
        <AppButton title={loading ? "Estimando…" : "Estimar nutrientes"} onPress={() => void estimateFood()} loading={loading} disabled={!estimateDescription.trim() && !estimatePhoto} variant="secondary" />
        {estimateResult ? <View style={{ gap: 8 }}>
          <Text style={{ color: colors.text, fontWeight: "900", fontSize: 16 }}>{estimateResult.name}</Text>
          <Text style={{ color: colors.accent, fontWeight: "800" }}>{fmt(estimateResult.total_grams)} g · {fmt(estimateResult.per_100g.kcal_per_100g * estimateResult.total_grams / 100)} kcal estimadas</Text>
          <SectionTitle title="Revisar y ajustar ingredientes" action={estimateResult.items.length + " ingredientes"} />
          {estimateResult.items.map((item, index) => <View key={index} style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 7, gap: 5 }}>
            <Field label="Ingrediente" value={item.name} onChangeText={value => updateEstimateItem(index, { name: value })} />
            <Field label="Cantidad estimada (g)" value={String(item.grams)} onChangeText={value => updateEstimateItem(index, { grams: Number(value.replace(",", ".")) })} keyboardType="decimal-pad" />
            <Muted>{fmt(item.kcal_per_100g)} kcal/100 g · confianza {item.confidence === "medium" ? "media" : "baja"}</Muted>
            <Text onPress={() => removeEstimateItem(index)} style={{ color: colors.danger, fontWeight: "700", paddingVertical: 4 }}>Eliminar ingrediente</Text>
          </View>)}
          {estimateResult.assumptions.map((item, index) => <Muted key={index}>• {item}</Muted>)}
          <Muted>La estimación es orientativa, no equivale a un análisis de laboratorio.</Muted>
          <AppButton title="Confirmar y registrar en el diario" onPress={() => void confirmEstimate()} loading={loading} />
          <AppButton title="Descartar estimación" onPress={() => setEstimateResult(null)} variant="quiet" />
        </View> : null}
      </Panel>
      </> : null}
      {foodEntryMode === "barcode" ? <>
      <SectionTitle title="Buscar código de barras" />
      <Panel>
        <AppButton title="Abrir escáner de cámara" onPress={() => setBarcodeScannerVisible(true)} variant="secondary" />
        <Field label="O introduce el código EAN/UPC" value={barcode} onChangeText={setBarcode} keyboardType="number-pad" placeholder="Código del envase" />
        <AppButton title="Consultar código" onPress={() => void findBarcode()} loading={loading} disabled={!barcode.trim()} variant="quiet" />
        {barcodeResult ? <View style={{ gap: 6 }}>
          <Text style={{ color: colors.text, fontWeight: "800" }}>{barcodeResult.food?.name ?? barcodeResult.name ?? "Producto encontrado"}</Text>
          {barcodeResult.food ? <AppButton title={"Añadir " + barcodeResult.food.name} onPress={() => void addFood(barcodeResult.food!)} /> : null}
        </View> : null}
        <Muted>El escáner detecta EAN/UPC y códigos de barras habituales. Si no se reconoce, puedes introducir los dígitos manualmente.</Muted>
      </Panel>
      </> : null}
      <SectionTitle title="Tus alimentos habituales" action={frequentFoods.length + " favoritos"} />
      <Panel>
        {frequentFoods.length ? frequentFoods.map(item => <Pressable key={item.food.id} onPress={() => {
          setGrams(String(Math.round(item.typical_grams)));
          void openFoodForLogging(item.food, String(Math.round(item.typical_grams)));
        }} style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8, borderBottomWidth: 1, borderBottomColor: colors.border, paddingVertical: 9 }}>
          <View style={{ flex: 1, gap: 3 }}>
            <Text style={{ color: colors.text, fontWeight: "800" }}>{item.food.name}</Text>
            <Muted>{item.times} registros · ración habitual {fmt(item.typical_grams)} g</Muted>
          </View>
          <Text style={{ color: colors.accent, fontWeight: "900" }}>＋ Añadir</Text>
        </Pressable>) : <Muted>Cuando repitas alimentos, aparecerán aquí para registrarlos rápidamente.</Muted>}
      </Panel>
      <SectionTitle title="Comidas registradas" action={(data?.entries?.length ?? 0) + " registros"} />
      <Panel>
        {data?.entries?.length ? data.entries.map(entry => <View key={entry.id} style={{ paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.border, gap: 4 }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 8 }}>
            <Text style={{ color: colors.text, fontWeight: "700", flex: 1 }}>{entry.food}</Text>
            <Text style={{ color: colors.accent, fontWeight: "800" }}>{Math.round(entry.kcal)} kcal</Text>
          </View>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <Muted>{entry.time} · {entry.grams} g · {meals.find(item => item.value === entry.meal)?.label ?? entry.meal}</Muted>
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

    {section === "catalog" ? <>
      <SectionTitle title="Buscar en SmartFit" action={(catalogSections.reduce((sum, item) => sum + item.count, 0) + filteredSmartFitRecipes.length + filteredPersonalFoods.length) + " resultados"} />
      <Muted>Explora alimentos por categoría y añádelos al diario con la cantidad y comida seleccionadas.</Muted>
      <Field label="Buscar alimentos en todas las categorías" value={catalogQuery} onChangeText={value => { setCatalogQuery(value); setCatalogCategory(""); }} placeholder="Ej. lentejas, café, arroz, tortilla…" />
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      <View style={{ gap: 8 }}>
        {filteredCatalogSections.map(item => {
          const expanded = item.id === catalogCategory;
          return <Panel key={item.id}>
            <Pressable onPress={() => setCatalogCategory(current => current === item.id ? "" : item.id)}
              style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
              <Text style={{ fontSize: 25 }}>{item.icon || "🥗"}</Text>
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.text, fontWeight: "900" }}>{item.title}</Text>
                {item.description ? <Muted>{item.description}</Muted> : null}
              </View>
              <Muted>{item.foods.length}/{item.count}</Muted>
              <Text style={{ color: colors.accent, fontWeight: "900", fontSize: 18 }}>{expanded ? "−" : "+"}</Text>
            </Pressable>
            {expanded ? <View style={{ marginTop: 10 }}>
              {item.foods.map(food => <Pressable key={food.id} onPress={() => void openFoodForLogging(food)} style={{
                flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 9,
                borderTopWidth: 1, borderColor: colors.border,
              }}>
                {food.image_url
                  ? <Image source={{ uri: food.image_url }} style={{ width: 42, height: 42, borderRadius: 9, backgroundColor: colors.surfaceRaised }} resizeMode="contain" />
                  : <Text style={{ fontSize: 22 }}>{food.icon || item.icon || "🥗"}</Text>}
                <View style={{ flex: 1, gap: 2 }}>
                  <Text style={{ color: colors.text, fontWeight: "800" }}>{food.name}</Text>
                  <Muted>{food.brand ?? "Alimento genérico"} · {fmt(food.kcal)} kcal/100 g</Muted>
                </View>
                <Text style={{ color: colors.accent, fontWeight: "900" }}>›</Text>
              </Pressable>)}
            </View> : null}
          </Panel>;
        })}
        {catalogFilter && !filteredCatalogSections.length ? <Muted>No hay alimentos que coincidan con «{catalogQuery}».</Muted> : null}
      </View>
      <Panel>
        <Pressable onPress={() => setCatalogCategory(current => current === "__smartfit_recipes" ? "" : "__smartfit_recipes")}
          style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
          <Text style={{ fontSize: 25 }}>🍲</Text>
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={{ color: colors.text, fontWeight: "900" }}>Recetas SmartFit</Text>
            <Muted>Recetas oficiales disponibles para registrar</Muted>
          </View>
          <Muted>{filteredSmartFitRecipes.length} recetas</Muted>
          <Text style={{ color: colors.accent, fontWeight: "900", fontSize: 18 }}>{catalogCategory === "__smartfit_recipes" ? "−" : "+"}</Text>
        </Pressable>
        {catalogCategory === "__smartfit_recipes" ? <View style={{ marginTop: 9 }}>
          {filteredSmartFitRecipes.map(recipe => <View key={"catalog-recipe-" + recipe.id} style={{ borderTopWidth: 1, borderColor: colors.border, paddingTop: 9, gap: 7 }}>
            <Pressable onPress={() => void openRecipe(recipe)} style={{ gap: 4 }}>
              <Text style={{ color: colors.text, fontWeight: "900" }}>{recipe.name}</Text>
              <Muted>{recipe.description || "Receta del catálogo SmartFit"} · {fmt(recipe.per_serving?.kcal)} kcal/ración</Muted>
              <Text style={{ color: colors.accent, fontWeight: "800" }}>Ver receta ›</Text>
            </Pressable>
            <AppButton title="Registrar receta" variant="secondary" onPress={() => void logRecipe(recipe)} loading={loading} />
          </View>)}
          {!filteredSmartFitRecipes.length ? <Muted>No hay recetas que coincidan con «{catalogQuery}».</Muted> : null}
        </View> : null}
      </Panel>
      <Panel>
        <Pressable onPress={() => setCatalogCategory(current => current === "__my_personal_foods" ? "" : "__my_personal_foods")}
          style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
          <Text style={{ fontSize: 25 }}>👤</Text>
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={{ color: colors.text, fontWeight: "900" }}>Mis personalizados</Text>
            <Muted>Alimentos que has creado para tu cuenta</Muted>
          </View>
          <Muted>{filteredPersonalFoods.length} alimentos</Muted>
          <Text style={{ color: colors.accent, fontWeight: "900", fontSize: 18 }}>{catalogCategory === "__my_personal_foods" ? "−" : "+"}</Text>
        </Pressable>
        {catalogCategory === "__my_personal_foods" ? <View style={{ marginTop: 9 }}>
          {filteredPersonalFoods.map(food => <Pressable key={"catalog-personal-" + food.id} onPress={() => void openFoodForLogging({
            id: food.id, name: food.name, brand: food.brand, kcal: food.kcal, protein_g: food.protein_g,
            carbs_g: food.carbs_g, fat_g: food.fat_g, source: "personal",
          })} style={{ flexDirection: "row", alignItems: "center", gap: 10, borderTopWidth: 1, borderColor: colors.border, paddingVertical: 9 }}>
            <Text style={{ fontSize: 22 }}>👤</Text>
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={{ color: colors.text, fontWeight: "800" }}>{food.name}</Text>
              <Muted>{food.brand ?? "Alimento personal"} · {fmt(food.kcal)} kcal/100 g</Muted>
            </View>
            <Text style={{ color: colors.accent, fontWeight: "900" }}>›</Text>
          </Pressable>)}
          {!filteredPersonalFoods.length ? <Muted>No hay alimentos personalizados que coincidan con «{catalogQuery}».</Muted> : null}
        </View> : null}
      </Panel>
      {catalogFilter && !filteredSmartFitRecipes.length && !filteredPersonalFoods.length && !filteredCatalogSections.length
        ? <Muted>No hay coincidencias en ninguna de las tres fuentes.</Muted> : null}
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
        {editingFoodId !== null ? <>
          <SectionTitle title="Unidades habituales" action={ownedFoodUnits.length + " unidades"} />
          {ownedFoodUnits.map(unit => <View key={unit.id} style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 8 }}>
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={{ color: colors.text, fontWeight: "800" }}>{unit.unit_name_plural || unit.unit_name}</Text>
              <Muted>{fmt(unit.grams_per_unit)} g por unidad{unit.description ? " · " + unit.description : ""}</Muted>
            </View>
            <Text onPress={() => void deleteOwnedFoodUnit(unit)} style={{ color: colors.danger, fontWeight: "700", padding: 7 }}>Quitar</Text>
          </View>)}
          <Field label="Nombre de unidad (singular)" value={unitName} onChangeText={setUnitName} placeholder="Ej. cucharada" />
          <Field label="Plural (opcional)" value={unitPlural} onChangeText={setUnitPlural} placeholder="Ej. cucharadas" />
          <Field label="Equivalencia en gramos" value={unitGrams} onChangeText={setUnitGrams} keyboardType="decimal-pad" placeholder="Ej. 15" />
          <Field label="Descripción (opcional)" value={unitDescription} onChangeText={setUnitDescription} placeholder="Ej. rasa" />
          <AppButton title="Añadir unidad habitual" onPress={() => void addOwnedFoodUnit()} loading={loading} disabled={!unitName.trim() || !unitGrams.trim()} variant="secondary" />
          <AppButton title="Cerrar edición" onPress={() => { setEditingFoodId(null); setFoodDraft(emptyFoodDraft()); setOwnedFoodUnits([]); }} variant="quiet" />
        </> : null}
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
        {selectedRecipe.ingredients.map(item => {
          const unit = recipeEditUnits[item.id] ?? { quantity: String(item.quantity), unit_name: item.unit_name || "g", grams_per_unit: String(item.grams_per_unit || 1) };
          return <View key={item.id} style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 7, gap: 6 }}>
            <Text style={{ color: colors.text, fontWeight: "700", flex: 1 }}>{item.food}</Text>
            {selectedRecipe.editable ? <>
              <Field label="Cantidad" value={unit.quantity} onChangeText={value => setRecipeEditUnits(current => ({ ...current, [item.id]: { ...unit, quantity: value } }))} keyboardType="decimal-pad" />
              <ChoiceRow value={unit.unit_name} onChange={value => setRecipeEditUnits(current => ({ ...current, [item.id]: { ...unit, unit_name: value, grams_per_unit: String(recipeUnits.find(option => option.value === value)?.factor ?? 1) } }))} options={recipeUnits.map(option => ({ value: option.value, label: option.label }))} />
              {unit.unit_name !== "g" && unit.unit_name !== "ml" ? <Field label="Gramos por unidad" value={unit.grams_per_unit} onChangeText={value => setRecipeEditUnits(current => ({ ...current, [item.id]: { ...unit, grams_per_unit: value } }))} keyboardType="decimal-pad" /> : null}
              <Muted>Equivale a {fmt(Number(unit.quantity) * Number(unit.grams_per_unit))} g</Muted>
            </> : <Muted>{fmt(item.quantity)} {item.unit_name || "g"} · {fmt(item.quantity_g)} g</Muted>}
          </View>;
        })}
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
        {recipeIngredients.map((item, index) => <View key={item.food.id} style={{ borderTopWidth: 1, borderColor: colors.border, paddingTop: 9, gap: 6 }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <Text style={{ color: colors.text, fontWeight: "800", flex: 1 }}>{item.food.name}</Text>
            <Text onPress={() => setRecipeIngredients(current => current.filter(x => x.food.id !== item.food.id))} style={{ color: colors.danger, padding: 5 }}>Quitar</Text>
          </View>
          <Field label="Cantidad" value={item.quantity} onChangeText={value => updateRecipeIngredient(index, { quantity: value })} keyboardType="decimal-pad" />
          <ChoiceRow value={item.unit_name} onChange={value => updateRecipeIngredient(index, { unit_name: value, grams_per_unit: String(recipeUnits.find(option => option.value === value)?.factor ?? 1) })} options={recipeUnits.map(option => ({ value: option.value, label: option.label }))} />
          {item.unit_name !== "g" && item.unit_name !== "ml" ? <Field label="Gramos por unidad" value={item.grams_per_unit} onChangeText={value => updateRecipeIngredient(index, { grams_per_unit: value })} keyboardType="decimal-pad" /> : null}
          <Muted>Equivale a {fmt(gramsForIngredient(item))} g</Muted>
        </View>)}
        {recipeIngredients.length ? <View style={{ gap: 4 }}>
          <Muted>Estimación por receta completa: {fmt(recipePreviewLocal.kcal)} kcal · proteína {fmt(recipePreviewLocal.protein_g)} g · hidratos {fmt(recipePreviewLocal.carbs_g)} g · grasas {fmt(recipePreviewLocal.fat_g)} g</Muted>
          {recipePreview ? <Muted>Por ración · {fmt(recipePreview.serving_g)} g · {fmt(recipePreview.per_serving.kcal)} kcal · proteína {fmt(recipePreview.per_serving.protein_g)} g · hidratos {fmt(recipePreview.per_serving.carbs_g)} g · grasas {fmt(recipePreview.per_serving.fat_g)} g</Muted> : null}
          <AppButton title="Guardar receta" onPress={() => void createRecipe()} loading={loading} />
        </View> : null}
      </Panel>
      <Muted>Las recetas del catálogo se pueden copiar a tu cuenta. La edición detallada de ingredientes y pasos queda disponible en la versión web; desde móvil puedes crear recetas nuevas, consultarlas y registrar raciones.</Muted>
    </> : null}
    <BarcodeScanner visible={barcodeScannerVisible} onClose={() => setBarcodeScannerVisible(false)} onScanned={code => { setBarcodeScannerVisible(false); void lookupBarcode(code); }} />
  </Screen>;
}
