"""Métricas GPS; los huecos largos no generan distancia ficticia."""
from __future__ import annotations
import math
from datetime import datetime,timezone
from typing import Iterable,Protocol
EARTH_RADIUS_KM=6371.0088
GAP_SECONDS=120
MAX_ROUTE_POINTS=10000
class Point(Protocol):
    lat:float
    lng:float
    altitude_m:float|None
    recorded_at:datetime
def as_utc(value:datetime)->datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
def haversine_km(lat1:float,lng1:float,lat2:float,lng2:float)->float:
    p1,p2=math.radians(lat1),math.radians(lat2)
    a=math.sin((p2-p1)/2)**2+math.cos(p1)*math.cos(p2)*math.sin(math.radians(lng2-lng1)/2)**2
    return EARTH_RADIUS_KM*2*math.atan2(math.sqrt(a),math.sqrt(max(0.0,1-a)))
def route_metrics(points:Iterable[Point],gap_seconds:float=GAP_SECONDS)->dict:
    pts=list(points);distance=elevation=gap=0.0
    for previous,current in zip(pts,pts[1:]):
        delta=(as_utc(current.recorded_at)-as_utc(previous.recorded_at)).total_seconds()
        if delta>gap_seconds:gap+=delta;continue
        distance+=haversine_km(previous.lat,previous.lng,current.lat,current.lng)
        if previous.altitude_m is not None and current.altitude_m is not None:elevation+=max(0.0,current.altitude_m-previous.altitude_m)
    return {"distance_km":distance,"elevation_gain_m":elevation,"gap_seconds":gap}
def merge_route_points(existing:list[dict],incoming:list[dict])->list[dict]:
    merged={}
    for point in [*existing,*incoming]:
        stamp=as_utc(datetime.fromisoformat(str(point["recorded_at"]).replace("Z","+00:00"))).isoformat()
        merged[stamp]=point
    return [merged[k] for k in sorted(merged)]
