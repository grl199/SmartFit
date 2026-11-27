import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Location from "expo-location";
import * as TaskManager from "expo-task-manager";
import { Platform } from "react-native";
import { api, getStoredAccessToken } from "@/lib/api";

export type CardioRoutePoint = {
  lat: number;
  lng: number;
  altitude_m: number | null;
  accuracy_m: number | null;
  recorded_at: string;
};

export type CardioLocalDraft = {
  owner: string;
  client_id: string;
  kind: string;
  category: "walking" | "running";
  performed_on?: string | null;
  started_at: string;
  points: CardioRoutePoint[];
  point_count: number;
  synced_point_count: number;
  received_fix_count: number;
  accepted_fix_count: number;
  rejected_fix_count: number;
  last_fix_at: string | null;
  last_accuracy_m: number | null;
  last_location_error?: string | null;
};

export const CARDIO_LOCATION_TASK = "smartfit-cardio-location";
const ACTIVE_DRAFT_KEY = "smartfit.activeRun.current-key";
const MAX_POINTS = 10000;
const MAX_ACCURACY_M = 65;
const MAX_SPEED_MS = 15;
const EARTH_RADIUS_KM = 6371.0088;

let storageQueue: Promise<unknown> = Promise.resolve();
const syncPromises = new Map<string, Promise<CardioLocalDraft | null>>();

function withStorageQueue<T>(operation: () => Promise<T>): Promise<T> {
  const result = storageQueue.then(operation, operation);
  storageQueue = result.then(() => undefined, () => undefined);
  return result;
}

function distanceMeters(a: CardioRoutePoint, b: CardioRoutePoint) {
  const rad = (value: number) => value * Math.PI / 180;
  const dLat = rad(b.lat - a.lat);
  const dLng = rad(b.lng - a.lng);
  const x = Math.sin(dLat / 2) ** 2
    + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return EARTH_RADIUS_KM * 1000 * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(Math.max(0, 1 - x)));
}

function mergePoints(existing: CardioRoutePoint[], incoming: CardioRoutePoint[]) {
  const byTimestamp = new Map<string, CardioRoutePoint>();
  for (const point of [...existing, ...incoming]) byTimestamp.set(point.recorded_at, point);
  return [...byTimestamp.values()]
    .sort((a, b) => Date.parse(a.recorded_at) - Date.parse(b.recorded_at))
    .slice(-MAX_POINTS);
}

function shouldAccept(previous: CardioRoutePoint | undefined, next: CardioRoutePoint) {
  if (!Number.isFinite(next.lat) || !Number.isFinite(next.lng)
    || next.lat < -90 || next.lat > 90 || next.lng < -180 || next.lng > 180) return false;
  if (next.accuracy_m != null && next.accuracy_m > MAX_ACCURACY_M) return false;
  if (!previous) return true;
  const seconds = (Date.parse(next.recorded_at) - Date.parse(previous.recorded_at)) / 1000;
  if (!(seconds > 0)) return false;
  const metres = distanceMeters(previous, next);
  const jitterLimit = Math.max(1, Math.min(3, ((previous.accuracy_m ?? 8) + (next.accuracy_m ?? 8)) * 0.1));
  if (metres < jitterLimit && seconds < 3) return false;
  return metres / seconds <= MAX_SPEED_MS;
}

async function readRawDraft(key: string): Promise<CardioLocalDraft | null> {
  const raw = await AsyncStorage.getItem(key);
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as CardioLocalDraft;
    return value && value.client_id && Array.isArray(value.points) ? value : null;
  } catch {
    return null;
  }
}

export function readLocalCardioDraft(key: string) {
  return withStorageQueue(() => readRawDraft(key));
}

export function saveLocalCardioDraft(key: string, draft: CardioLocalDraft) {
  return withStorageQueue(async () => {
    const previous = await readRawDraft(key);
    const sameActivity = previous?.client_id === draft.client_id;
    const points = sameActivity ? mergePoints(previous.points, draft.points) : draft.points.slice(-MAX_POINTS);
    const saved: CardioLocalDraft = {
      ...(sameActivity ? previous : {} as CardioLocalDraft),
      ...draft,
      points,
      point_count: points.length,
      synced_point_count: sameActivity
        ? Math.min(points.length, Math.max(previous.synced_point_count ?? 0, draft.synced_point_count ?? 0))
        : Math.min(points.length, draft.synced_point_count ?? 0),
      received_fix_count: sameActivity
        ? Math.max(previous.received_fix_count ?? 0, draft.received_fix_count ?? 0)
        : draft.received_fix_count ?? 0,
      accepted_fix_count: sameActivity
        ? Math.max(previous.accepted_fix_count ?? 0, draft.accepted_fix_count ?? 0)
        : draft.accepted_fix_count ?? 0,
      rejected_fix_count: sameActivity
        ? Math.max(previous.rejected_fix_count ?? 0, draft.rejected_fix_count ?? 0)
        : draft.rejected_fix_count ?? 0,
    };
    await AsyncStorage.setItem(key, JSON.stringify(saved));
    return saved;
  });
}

export function appendCardioLocations(key: string, locations: Location.LocationObject[]) {
  return withStorageQueue(async () => {
    const draft = await readRawDraft(key);
    if (!draft || locations.length === 0) return draft;
    const sorted = [...locations].sort((a, b) => a.timestamp - b.timestamp);
    const points = [...draft.points];
    let received = draft.received_fix_count ?? 0;
    let accepted = draft.accepted_fix_count ?? 0;
    let rejected = draft.rejected_fix_count ?? 0;
    let lastAccuracy = draft.last_accuracy_m ?? null;

    for (const location of sorted) {
      received += 1;
      const coords = location.coords;
      const point: CardioRoutePoint = {
        lat: coords.latitude,
        lng: coords.longitude,
        altitude_m: coords.altitude,
        accuracy_m: coords.accuracy,
        recorded_at: new Date(location.timestamp || Date.now()).toISOString(),
      };
      lastAccuracy = coords.accuracy;
      const previous = points[points.length - 1];
      const seconds = previous ? (Date.parse(point.recorded_at) - Date.parse(previous.recorded_at)) / 1000 : Infinity;
      const duplicate = previous && seconds >= 0 && seconds < 1.5 && distanceMeters(previous, point) < 4;
      if (duplicate || !shouldAccept(previous, point)) {
        rejected += 1;
        continue;
      }
      points.push(point);
      accepted += 1;
      if (points.length > MAX_POINTS) points.splice(0, points.length - MAX_POINTS);
    }

    const saved: CardioLocalDraft = {
      ...draft,
      points,
      point_count: points.length,
      received_fix_count: received,
      accepted_fix_count: accepted,
      rejected_fix_count: rejected,
      last_fix_at: new Date().toISOString(),
      last_accuracy_m: lastAccuracy,
      last_location_error: null,
    };
    await AsyncStorage.setItem(key, JSON.stringify(saved));
    return saved;
  });
}

export function syncLocalCardioDraft(key: string, providedToken?: string) {
  const existing = syncPromises.get(key);
  if (existing) return existing;
  const operation = (async () => {
    let draft = await readLocalCardioDraft(key);
    if (!draft) return null;
    const token = providedToken || await getStoredAccessToken();
    if (!token) return draft;

    while (true) {
      draft = await readLocalCardioDraft(key);
      if (!draft) return null;
      const from = Math.min(draft.synced_point_count ?? 0, draft.points.length);
      const batch = draft.points.slice(from, from + 500);
      if (batch.length === 0) return draft;
      await api("/activity-drafts/" + draft.client_id, token, {
        method: "PUT",
        body: {
          kind: draft.kind.trim().slice(0, 100) || "Actividad",
          category: draft.category,
          performed_on: draft.performed_on ?? null,
          started_at: draft.started_at,
          points: batch,
        },
      });
      draft = await saveLocalCardioDraft(key, {
        ...draft,
        synced_point_count: from + batch.length,
      });
    }
  })().finally(() => syncPromises.delete(key));
  syncPromises.set(key, operation);
  return operation;
}

export async function startCardioBackgroundUpdates(key: string) {
  if (!(await TaskManager.isAvailableAsync())) {
    throw new Error("El seguimiento GPS en segundo plano requiere una instalación nativa de SmartFit.");
  }
  await AsyncStorage.setItem(ACTIVE_DRAFT_KEY, key);
  if (await Location.hasStartedLocationUpdatesAsync(CARDIO_LOCATION_TASK)) return;
  await Location.startLocationUpdatesAsync(CARDIO_LOCATION_TASK, {
    accuracy: Location.Accuracy.High,
    timeInterval: 1000,
    distanceInterval: 3,
    pausesUpdatesAutomatically: false,
    showsBackgroundLocationIndicator: true,
    foregroundService: {
      notificationTitle: "SmartFit está registrando tu actividad",
      notificationBody: "El GPS sigue activo mientras caminas o corres.",
      notificationColor: "#16A86B",
      killServiceOnDestroy: false,
    },
  });
}

export async function stopCardioBackgroundUpdates(key: string) {
  if (await TaskManager.isAvailableAsync()
    && await Location.hasStartedLocationUpdatesAsync(CARDIO_LOCATION_TASK)) {
    await Location.stopLocationUpdatesAsync(CARDIO_LOCATION_TASK);
  }
  if (await AsyncStorage.getItem(ACTIVE_DRAFT_KEY) === key) {
    await AsyncStorage.removeItem(ACTIVE_DRAFT_KEY);
  }
}

export async function clearLocalCardioDraft(key: string) {
  await withStorageQueue(async () => {
    await AsyncStorage.removeItem(key);
    if (await AsyncStorage.getItem(ACTIVE_DRAFT_KEY) === key) {
      await AsyncStorage.removeItem(ACTIVE_DRAFT_KEY);
    }
  });
}

if (Platform.OS !== "web") TaskManager.defineTask(CARDIO_LOCATION_TASK, async ({ data, error }) => {
  const key = await AsyncStorage.getItem(ACTIVE_DRAFT_KEY);
  if (!key) return;
  if (error) {
    await withStorageQueue(async () => {
      const draft = await readRawDraft(key);
      if (draft) await AsyncStorage.setItem(key, JSON.stringify({
        ...draft,
        last_location_error: error.message || "El servicio de ubicación notificó un error.",
      }));
    });
    return;
  }
  const payload = data as { locations?: Location.LocationObject[] } | undefined;
  const locations = payload?.locations ?? [];
  if (!locations.length) return;
  await appendCardioLocations(key, locations);
  try {
    await syncLocalCardioDraft(key);
  } catch {
    // El borrador local permanece guardado y se sincronizará al volver a primer plano.
  }
});
