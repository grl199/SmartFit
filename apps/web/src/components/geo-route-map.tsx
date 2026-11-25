"use client";
import { useMemo } from "react";

export type GeoRoutePoint = {
  lat: number;
  lng: number;
  altitude_m?: number | null;
  accuracy_m?: number | null;
  recorded_at?: string;
};

type Tile = { url: string; x: number; y: number };
type Geometry = { zoom: number; tiles: Tile[]; line: string } | null;

const TILE_TEMPLATE = process.env.NEXT_PUBLIC_OSM_TILE_URL || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

function mercator(point: GeoRoutePoint, zoom: number) {
  const size = 256 * Math.pow(2, zoom);
  const latitude = Math.max(-85.05112878, Math.min(85.05112878, point.lat));
  const sin = Math.sin(latitude * Math.PI / 180);
  return {
    x: (point.lng + 180) / 360 * size,
    y: (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * size
  };
}

function buildGeometry(points: GeoRoutePoint[]): Geometry {
  if (points.length < 2) return null;
  let zoom = 17;
  let projected = points.map(point => mercator(point, zoom));
  for (let candidate = 17; candidate >= 10; candidate--) {
    const values = points.map(point => mercator(point, candidate));
    const xs = values.map(point => point.x);
    const ys = values.map(point => point.y);
    const width = Math.max(...xs) - Math.min(...xs);
    const height = Math.max(...ys) - Math.min(...ys);
    zoom = candidate;
    projected = values;
    if (width <= 520 && height <= 240) break;
  }
  const xs = projected.map(point => point.x);
  const ys = projected.map(point => point.y);
  const left = (Math.min(...xs) + Math.max(...xs)) / 2 - 320;
  const top = (Math.min(...ys) + Math.max(...ys)) / 2 - 180;
  const totalTiles = Math.pow(2, zoom);
  const minX = Math.floor(left / 256);
  const maxX = Math.floor((left + 640) / 256);
  const minY = Math.floor(top / 256);
  const maxY = Math.floor((top + 360) / 256);
  const tiles: Tile[] = [];
  for (let y = minY; y <= maxY; y++) {
    if (y < 0 || y >= totalTiles) continue;
    for (let x = minX; x <= maxX; x++) {
      const wrappedX = ((x % totalTiles) + totalTiles) % totalTiles;
      const url = TILE_TEMPLATE.replace("{z}", String(zoom)).replace("{x}", String(wrappedX)).replace("{y}", String(y));
      tiles.push({ url, x: x * 256 - left, y: y * 256 - top });
    }
  }
  const line = projected.map(point => (point.x - left).toFixed(1) + "," + (point.y - top).toFixed(1)).join(" ");
  return { zoom, tiles, line };
}

export function GeoRouteMap({ points, compact = false }: { points: GeoRoutePoint[]; compact?: boolean }) {
  const geometry = useMemo(() => buildGeometry(points), [points]);
  if (!geometry) return null;
  const start = geometry.line.split(" ")[0].split(",");
  const end = geometry.line.split(" ").slice(-1)[0].split(",");
  return (
    <div className={compact ? "geo-route-map compact" : "geo-route-map"}>
      <svg viewBox="0 0 640 360" role="img" aria-label="Mapa del recorrido GPS">
        {geometry.tiles.map((tile, index) => (
          <image key={index} href={tile.url} x={tile.x} y={tile.y} width="256" height="256" />
        ))}
        <polyline points={geometry.line} fill="none" stroke="#ffffff" strokeWidth="9" strokeLinecap="round" strokeLinejoin="round" />
        <polyline points={geometry.line} fill="none" stroke="#4e8a43" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx={start[0]} cy={start[1]} r="8" fill="#367e3e" stroke="#fff" strokeWidth="3" />
        <circle cx={end[0]} cy={end[1]} r="8" fill="#ce5946" stroke="#fff" strokeWidth="3" />
      </svg>
      <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a>
    </div>
  );
}
