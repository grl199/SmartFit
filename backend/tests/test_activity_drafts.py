"""Borradores GPS: persistencia por lotes, privacidad y huecos de señal."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
T0=datetime(2026,11,25,10,0,0,tzinfo=timezone.utc)
def pt(seconds,lat=40.0,lng=-3.7,alt=None):return SimpleNamespace(lat=lat,lng=lng,altitude_m=alt,recorded_at=T0+timedelta(seconds=seconds))
def payload(seconds,lat=40.0,lng=-3.7,alt=None):return {"lat":lat,"lng":lng,"altitude_m":alt,"accuracy_m":8.0,"recorded_at":(T0+timedelta(seconds=seconds)).isoformat().replace("+00:00","Z")}
def test_route_metrics_skip_gaps():
    from app.services.route import GAP_SECONDS,route_metrics
    m=route_metrics([pt(0),pt(30,lat=40.0003),pt(2430,lat=40.018),pt(2460,lat=40.0183)])
    assert m["gap_seconds"]==2400
    assert m["distance_km"]==pytest.approx(.0667,abs=.005)
    assert route_metrics([pt(0),pt(GAP_SECONDS,lat=40.001)])["gap_seconds"]==0
def test_merge_points_is_idempotent():
    from app.services.route import merge_route_points
    a,b,c=payload(0),payload(10),payload(20)
    m=merge_route_points([b],[c,a,b])
    assert [p["recorded_at"] for p in m]==[a["recorded_at"],b["recorded_at"],c["recorded_at"]]
    assert merge_route_points(m,m)==m
def draft(client,headers,cid,points=(),**over):
    return client.put(f"/activity-drafts/{cid}",headers=headers,json={"kind":"Correr","category":"running","started_at":T0.isoformat().replace("+00:00","Z"),"points":list(points),**over})
def test_draft_batches_are_idempotent_and_private(client,onboarded):
    from conftest import onboard_new_user
    h=onboarded["headers"]
    assert client.get("/activity-drafts/active",headers=h).json() is None
    r=draft(client,h,"run-abc-0001",[payload(0),payload(10,lat=40.0001)])
    assert r.status_code==200 and r.json()["point_count"]==2
    r=draft(client,h,"run-abc-0001",[payload(10,lat=40.0001),payload(20,lat=40.0002)])
    assert r.json()["point_count"]==3
    other=onboard_new_user(client)["headers"]
    assert client.get("/activity-drafts/active",headers=other).json() is None
    client.delete("/activity-drafts/run-abc-0001",headers=other)
    assert client.get("/activity-drafts/active",headers=h).json()["point_count"]==3
    assert client.delete("/activity-drafts/run-abc-0001",headers=h).status_code==204
def test_workout_consumes_draft_and_ignores_gap(client,onboarded):
    from unittest.mock import patch
    from test_training import llm
    h=onboarded["headers"];draft(client,h,"run-save-0001",[payload(0)])
    route=[payload(0),payload(30,lat=40.0003),payload(2430,lat=40.018),payload(2460,lat=40.0183)]
    with patch("app.services.calories.chat_text",llm(8.0)):
        r=client.post("/workouts",headers=h,json={"kind":"Correr","category":"running","duration_min":2,"route_points":route,"draft_id":"run-save-0001"})
    assert r.status_code==201,r.text
    assert r.json()["distance_km"]==pytest.approx(.067,abs=.005)
    assert client.get("/activity-drafts/active",headers=h).json() is None


def test_account_deletion_removes_active_gps_draft(client,onboarded):
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models import ActivityDraft
    headers=onboarded["headers"]
    draft(client,headers,"run-delete-0001",[payload(0),payload(10,lat=40.0001)])
    response=client.request("DELETE","/auth/me",headers=headers,json={"password":onboarded["password"]})
    assert response.status_code==204,response.text
    with SessionLocal() as db:
        assert db.scalar(select(ActivityDraft).where(ActivityDraft.user_id==onboarded["id"])) is None
