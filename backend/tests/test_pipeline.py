"""End-to-end tests for the collection → rollup → analytics → ML pipeline.

These follow one observation all the way from ``POST /v1/ingest`` to the number
the dashboard renders, which is the path most likely to break silently: each
stage individually "works" while the handoff between two of them quietly drops
or mis-buckets rows.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app import events
from app.analytics import health_score, health_timeline, request_heatmap, traffic_series
from app.jobs.ml_jobs import run_anomaly_detection, run_forecasts
from app.jobs.rollup import compute_rollups, minute_bucket, percentile
from app.ml.anomaly import confidence_from_score, detect, robust_zscore
from app.ml.forecasting import backtest, build_series, fit_forecast
from app.models import ApiRegistry, LogSource, MetricRollup, RequestLog
from app.routers.ingest import normalise_endpoint, registry_slug


@pytest.fixture(name="api")
def api_fixture(client: TestClient, auth_headers: dict[str, str]) -> dict[str, object]:
    """Register one API to hang the pipeline tests off.

    Args:
        client: HTTP client.
        auth_headers: Bearer header for the default account.

    Returns:
        dict[str, object]: The created registry row.
    """
    response = client.post(
        "/v1/apis",
        headers=auth_headers,
        json={
            "name": "Checkout",
            "base_url": "/checkout",
            "upstream_url": "http://upstream.invalid/checkout",
            "slo_target": 0.99,
            "slo_latency_ms": 200,
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def _seed_requests(
    session: Session,
    api_id: int,
    *,
    minutes: int = 40,
    per_minute: int = 6,
    latency_ms: float = 100.0,
    error_every: int = 0,
) -> None:
    """Write synthetic raw requests spread over recent minutes.

    Args:
        session: Test session.
        api_id: Registry id the rows belong to.
        minutes: How many minute buckets to fill, ending one minute ago.
        per_minute: Rows per bucket.
        latency_ms: Latency written on every row.
        error_every: Make every Nth row a 500. ``0`` means no errors.
    """
    now = datetime.now(UTC)
    rows = []
    for minute in range(minutes, 0, -1):
        bucket = minute_bucket(now - timedelta(minutes=minute))
        for index in range(per_minute):
            is_error = bool(error_every) and index % error_every == 0
            rows.append(
                RequestLog(
                    time=bucket + timedelta(seconds=index),
                    api_id=api_id,
                    endpoint="/pay",
                    method="POST",
                    status_code=500 if is_error else 200,
                    latency_ms=latency_ms,
                    is_error=is_error,
                    source=LogSource.PROXY,
                )
            )
    session.add_all(rows)
    session.commit()


# --------------------------------------------------------------------------- #
# Endpoint normalisation and proxy resolution                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", "/"),
        ("/", "/"),
        ("users/42", "/users/{id}"),
        ("/users/42/orders/7", "/users/{id}/orders/{id}"),
        ("/o/3f2504e0-4f89-11d3-9a0c-0305e82c3301", "/o/{uuid}"),
        ("/blob/deadbeefdeadbeef99", "/blob/{hash}"),
        ("/fast", "/fast"),
    ],
)
def test_normalise_endpoint_folds_identifiers(raw: str, expected: str) -> None:
    """Concrete ids collapse to templates so rollups group by route."""
    assert normalise_endpoint(raw) == expected


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [("/payments", "payments"), ("payments", "payments"), ("https://x.dev/Pay/v2", "pay")],
)
def test_registry_slug_is_tolerant_of_base_url_shape(base_url: str, expected: str) -> None:
    """The proxy mount point is derived from loosely-formatted base URLs."""
    assert registry_slug(base_url) == expected


def test_proxy_returns_404_for_unmounted_slug(client: TestClient) -> None:
    """A slug that matches no registered API is a 404, not a 501 or a 500."""
    response = client.get("/proxy/nothing-here/anything")

    assert response.status_code == 404
    assert "nothing-here" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# Ingest                                                                       #
# --------------------------------------------------------------------------- #


def test_ingest_persists_events(
    client: TestClient, session: Session, api: dict[str, object]
) -> None:
    """Accepted events land in ``request_log`` with normalised endpoints."""
    response = client.post(
        "/v1/ingest",
        json=[
            {
                "api_id": api["id"],
                "endpoint": "/orders/1234",
                "method": "get",
                "status_code": 200,
                "latency_ms": 12.5,
            },
            {
                "api_id": api["id"],
                "endpoint": "/orders/9",
                "method": "GET",
                "status_code": 503,
                "latency_ms": 41.0,
            },
        ],
    )

    assert response.status_code == 202
    assert response.json() == {"accepted": 2}

    rows = session.query(RequestLog).all()
    assert [row.endpoint for row in rows] == ["/orders/{id}", "/orders/{id}"]
    assert [row.method for row in rows] == ["GET", "GET"]
    assert [row.is_error for row in rows] == [False, True]
    assert all(row.source == LogSource.SDK for row in rows)


def test_ingest_rejects_unknown_api(client: TestClient) -> None:
    """An event for an unregistered API fails loudly instead of orphaning rows."""
    response = client.post(
        "/v1/ingest",
        json=[
            {
                "api_id": 9999,
                "endpoint": "/x",
                "method": "GET",
                "status_code": 200,
                "latency_ms": 1.0,
            }
        ],
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "unknown api_id: 9999"}


# --------------------------------------------------------------------------- #
# Rollup                                                                       #
# --------------------------------------------------------------------------- #


def test_percentile_interpolates_like_numpy() -> None:
    """The percentile helper matches the linear-interpolation convention."""
    values = [10.0, 20.0, 30.0, 40.0]

    assert percentile(values, 0.0) == 10.0
    assert percentile(values, 0.5) == 25.0
    assert percentile(values, 1.0) == 40.0
    assert percentile([7.0], 0.95) == 7.0


def test_rollup_aggregates_raw_rows(session: Session, api: dict[str, object]) -> None:
    """Raw rows become one bucket per (minute, api, endpoint)."""
    _seed_requests(session, int(api["id"]), minutes=3, per_minute=4, error_every=4)

    written = compute_rollups(session, window_min=10)

    assert written == 3
    buckets = session.query(MetricRollup).all()
    assert {bucket.req_count for bucket in buckets} == {4}
    assert {bucket.err_count for bucket in buckets} == {1}
    assert {round(bucket.p95_ms) for bucket in buckets} == {100}


def test_rollup_is_idempotent(session: Session, api: dict[str, object]) -> None:
    """Re-running over the same window updates buckets instead of duplicating."""
    _seed_requests(session, int(api["id"]), minutes=3, per_minute=4)

    compute_rollups(session, window_min=10)
    compute_rollups(session, window_min=10)

    assert session.query(MetricRollup).count() == 3


# --------------------------------------------------------------------------- #
# Analytics                                                                    #
# --------------------------------------------------------------------------- #


def test_analytics_series_read_from_rollups(
    client: TestClient, session: Session, api: dict[str, object]
) -> None:
    """Latency, traffic and error series all resolve from ``metric_rollup``."""
    api_id = int(api["id"])
    _seed_requests(session, api_id, minutes=5, per_minute=4, latency_ms=250.0, error_every=4)
    compute_rollups(session, window_min=10)

    latency = client.get(f"/v1/analytics/latency?api_id={api_id}&window_min=60").json()
    traffic = client.get(f"/v1/analytics/traffic?api_id={api_id}&window_min=60").json()
    errors = client.get(f"/v1/analytics/errors?api_id={api_id}&window_min=60").json()

    assert latency["metric"] == "latency.p95"
    assert len(latency["points"]) == 5
    assert all(point["value"] == pytest.approx(250.0) for point in latency["points"])
    assert [point["value"] for point in traffic["points"]] == [4.0] * 5
    assert all(point["value"] == pytest.approx(25.0) for point in errors["points"])


def test_analytics_404s_for_unknown_api(client: TestClient) -> None:
    """Series endpoints reject an api_id that was never registered."""
    response = client.get("/v1/analytics/latency?api_id=4242")

    assert response.status_code == 404


def test_health_score_penalises_breaches() -> None:
    """A perfect window scores 100; SLO breaches pull the score down."""
    assert health_score(0, 0, 0.0, 0.99, 200) == 100.0
    assert health_score(100, 0, 100.0, 0.99, 200) == 100.0
    assert health_score(100, 50, 100.0, 0.99, 200) == pytest.approx(50.5, abs=0.5)
    assert health_score(100, 100, 10.0, 0.99, 200) == 0.0
    assert 70.0 < health_score(100, 0, 800.0, 0.99, 200) < 80.0


def test_overview_reports_per_api_standing(
    client: TestClient, session: Session, api: dict[str, object]
) -> None:
    """The overview folds the tiles and every API's standing into one payload."""
    api_id = int(api["id"])
    _seed_requests(session, api_id, minutes=5, per_minute=4, latency_ms=90.0)
    compute_rollups(session, window_min=10)

    payload = client.get("/v1/analytics/overview?window_min=60").json()

    assert payload["summary"]["api_count"] == 1
    assert payload["summary"]["total_requests"] == 20
    assert payload["summary"]["error_rate"] == 0.0
    row = payload["apis"][0]
    assert row["api_id"] == api_id
    assert row["status"] == "healthy"
    assert row["score"] == 100.0


def test_endpoint_breakdown_orders_by_latency(
    client: TestClient, session: Session, api: dict[str, object]
) -> None:
    """The endpoint table triages slowest-first."""
    api_id = int(api["id"])
    now = datetime.now(UTC)
    session.add_all(
        [
            RequestLog(
                time=now - timedelta(seconds=30),
                api_id=api_id,
                endpoint="/quick",
                method="GET",
                status_code=200,
                latency_ms=10.0,
            ),
            RequestLog(
                time=now - timedelta(seconds=30),
                api_id=api_id,
                endpoint="/slow",
                method="GET",
                status_code=200,
                latency_ms=900.0,
            ),
        ]
    )
    session.commit()
    compute_rollups(session, window_min=10)

    payload = client.get(f"/v1/analytics/endpoints?api_id={api_id}").json()

    assert [item["endpoint"] for item in payload["endpoints"]] == ["/slow", "/quick"]


# --------------------------------------------------------------------------- #
# ML                                                                           #
# --------------------------------------------------------------------------- #


def test_build_series_fills_gaps_with_zero() -> None:
    """A minute with no rows is zero traffic, not a missing observation."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    frame = pd.DataFrame(
        {
            "bucket": [start, start + timedelta(minutes=3)],
            "req_count": [5, 9],
        }
    )

    series = build_series(frame)

    assert list(series) == [5.0, 0.0, 0.0, 9.0]


def test_fit_forecast_returns_bounded_points() -> None:
    """Forecasts are non-negative and bracketed by their prediction interval."""
    series = pd.Series([float(10 + (index % 5)) for index in range(120)])

    result = fit_forecast(series, horizon_min=10)

    assert len(result.yhat) == 10
    assert result.horizons[0] == 1
    assert all(value >= 0 for value in result.yhat_lower)
    assert all(
        low <= point <= high
        for low, point, high in zip(result.yhat_lower, result.yhat, result.yhat_upper, strict=True)
    )


def test_fit_forecast_handles_an_empty_series() -> None:
    """A brand-new API forecasts zeros rather than raising."""
    result = fit_forecast(pd.Series(dtype="float64"), horizon_min=3)

    assert result.yhat == [0.0, 0.0, 0.0]


def test_backtest_reports_folds_and_a_baseline() -> None:
    """The rolling-origin backtest scores the model against seasonal-naive."""
    series = pd.Series([float(20 + (index % 7)) for index in range(200)])

    scores = backtest(series, horizon_min=10, folds=3)

    assert scores["folds"] == 3.0
    assert scores["mae"] >= 0.0
    assert "mae_baseline" in scores


def test_robust_zscore_flags_a_spike_not_the_baseline() -> None:
    """A single spike scores high while the flat baseline stays near zero."""
    series = pd.Series([100.0] * 30 + [900.0])

    scores = robust_zscore(series)

    assert abs(scores.iloc[-1]) > 3.5
    assert abs(scores.iloc[20]) < 1.0


def test_detect_finds_a_latency_cliff() -> None:
    """A latency cliff in the newest bucket is reported with an expected band."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    buckets = [start + timedelta(minutes=index) for index in range(31)]
    frame = pd.DataFrame(
        {
            "bucket": buckets,
            "endpoint": ["/pay"] * 31,
            "req_count": [10] * 31,
            "err_count": [0] * 31,
            "p95_ms": [100.0] * 30 + [1200.0],
            "saturation_pct": [None] * 31,
        }
    )

    findings = detect(frame, slo_latency_ms=200)

    latency = [finding for finding in findings if finding.signal == "latency"]
    assert latency, findings
    assert latency[0].metric_value == 1200.0
    assert latency[0].severity in {"warning", "critical"}
    assert latency[0].expected_high < 1200.0


def test_detect_stays_quiet_without_a_baseline() -> None:
    """Too little history means no detection, rather than a false alarm."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    frame = pd.DataFrame(
        {
            "bucket": [start, start + timedelta(minutes=1)],
            "endpoint": ["/pay", "/pay"],
            "req_count": [10, 10],
            "err_count": [0, 9],
            "p95_ms": [100.0, 5000.0],
            "saturation_pct": [None, None],
        }
    )

    assert detect(frame) == []


def test_anomaly_job_raises_then_resolves(session: Session, api: dict[str, object]) -> None:
    """An incident opens one alert and closes it once the signal recovers."""
    api_id = int(api["id"])
    now = datetime.now(UTC)
    calm = [
        MetricRollup(
            bucket=minute_bucket(now - timedelta(minutes=index)),
            api_id=api_id,
            endpoint="/pay",
            req_count=10,
            err_count=0,
            p50_ms=100.0,
            p95_ms=100.0,
            p99_ms=100.0,
            avg_ms=100.0,
        )
        for index in range(30, 0, -1)
    ]
    spike = MetricRollup(
        bucket=minute_bucket(now),
        api_id=api_id,
        endpoint="/pay",
        req_count=10,
        err_count=0,
        p50_ms=100.0,
        p95_ms=2500.0,
        p99_ms=2500.0,
        avg_ms=2500.0,
    )
    session.add_all([*calm, spike])
    session.commit()

    assert run_anomaly_detection(session, window_min=120) >= 1

    # Re-running while the incident persists must not duplicate the alert.
    assert run_anomaly_detection(session, window_min=120) == 0

    spike.p95_ms = 100.0
    session.add(spike)
    session.commit()
    run_anomaly_detection(session, window_min=120)

    from app.models import Alert

    assert all(alert.resolved_at is not None for alert in session.query(Alert).all())


def test_forecast_endpoint_serves_stored_points(
    client: TestClient, session: Session, api: dict[str, object]
) -> None:
    """The scheduler's stored forecast is what the endpoint returns."""
    api_id = int(api["id"])
    _seed_requests(session, api_id, minutes=40, per_minute=5)
    compute_rollups(session, window_min=60)

    assert run_forecasts(session, horizon_min=5) == 1

    payload = client.get(f"/v1/forecast/{api_id}?horizon_min=5").json()

    assert payload["api_id"] == api_id
    assert len(payload["points"]) == 5
    assert all(
        point["yhat_lower"] <= point["yhat"] <= point["yhat_upper"] for point in payload["points"]
    )


def test_forecast_endpoint_fits_inline_on_a_cold_start(
    client: TestClient, session: Session, api: dict[str, object]
) -> None:
    """With no stored forecast the endpoint still answers with a chartable series."""
    api_id = int(api["id"])
    _seed_requests(session, api_id, minutes=20, per_minute=3)
    compute_rollups(session, window_min=60)

    payload = client.get(f"/v1/forecast/{api_id}?horizon_min=4").json()

    assert len(payload["points"]) == 4


def test_models_metrics_endpoint_reports_after_a_refit(
    client: TestClient, session: Session, api: dict[str, object]
) -> None:
    """``/v1/models/metrics`` reports the models scored by the last refit."""
    from app.ml import metrics_store

    metrics_store.clear()
    _seed_requests(session, int(api["id"]), minutes=60, per_minute=5)
    compute_rollups(session, window_min=90)
    run_forecasts(session, horizon_min=10)

    payload = client.get("/v1/models/metrics").json()

    assert payload, "a refit should have recorded at least one model"
    assert {"seasonal_naive"} <= {entry["model_name"] for entry in payload}
    metrics_store.clear()


# --------------------------------------------------------------------------- #
# Anomaly confidence + API name                                                #
# --------------------------------------------------------------------------- #


def test_confidence_from_score_is_bounded_and_monotonic() -> None:
    """A stronger score reads as more confident, but never reaches 1.0."""
    weak = confidence_from_score(3.5, "robust_zscore")
    strong = confidence_from_score(14.0, "robust_zscore")

    assert 0.0 < weak < strong < 1.0


def test_anomaly_job_persists_a_confidence(session: Session, api: dict[str, object]) -> None:
    """Alerts raised by the anomaly job carry the detector's confidence."""
    api_id = int(api["id"])
    now = datetime.now(UTC)
    calm = [
        MetricRollup(
            bucket=minute_bucket(now - timedelta(minutes=index)),
            api_id=api_id,
            endpoint="/pay",
            req_count=10,
            err_count=0,
            p50_ms=100.0,
            p95_ms=100.0,
            p99_ms=100.0,
            avg_ms=100.0,
        )
        for index in range(30, 0, -1)
    ]
    spike = MetricRollup(
        bucket=minute_bucket(now),
        api_id=api_id,
        endpoint="/pay",
        req_count=10,
        err_count=0,
        p50_ms=100.0,
        p95_ms=2500.0,
        p99_ms=2500.0,
        avg_ms=2500.0,
    )
    session.add_all([*calm, spike])
    session.commit()

    assert run_anomaly_detection(session, window_min=120) >= 1

    from app.models import Alert

    fired = session.query(Alert).one()
    assert fired.confidence is not None
    assert 0.0 < fired.confidence < 1.0


def test_alerts_endpoint_reports_api_name_and_confidence(
    client: TestClient, session: Session, api: dict[str, object]
) -> None:
    """``GET /v1/alerts`` denormalises the API name and carries confidence."""
    api_id = int(api["id"])
    now = datetime.now(UTC)
    calm = [
        MetricRollup(
            bucket=minute_bucket(now - timedelta(minutes=index)),
            api_id=api_id,
            endpoint="/pay",
            req_count=10,
            err_count=0,
            p95_ms=100.0,
        )
        for index in range(30, 0, -1)
    ]
    spike = MetricRollup(
        bucket=minute_bucket(now), api_id=api_id, endpoint="/pay", req_count=10, p95_ms=2500.0
    )
    session.add_all([*calm, spike])
    session.commit()
    run_anomaly_detection(session, window_min=120)

    payload = client.get("/v1/alerts").json()

    assert payload
    assert payload[0]["api_name"] == api["name"]
    assert payload[0]["confidence"] is not None


# --------------------------------------------------------------------------- #
# Incremental (``since=``) series fetches                                     #
# --------------------------------------------------------------------------- #


def test_traffic_series_since_returns_only_newer_buckets(
    session: Session, api: dict[str, object]
) -> None:
    """``since`` narrows the series to buckets strictly after the cursor."""
    api_id = int(api["id"])
    _seed_requests(session, api_id, minutes=10, per_minute=3)
    compute_rollups(session, window_min=20)

    full = traffic_series(session, api_id, window_min=20)
    assert len(full) >= 3

    cursor = full[-2].bucket
    incremental = traffic_series(session, api_id, window_min=20, since=cursor)

    assert incremental == [full[-1]]


def test_traffic_endpoint_accepts_since(
    client: TestClient, session: Session, api: dict[str, object]
) -> None:
    """The HTTP layer plumbs ``since`` through to the same incremental query."""
    api_id = int(api["id"])
    _seed_requests(session, api_id, minutes=10, per_minute=3)
    compute_rollups(session, window_min=20)

    full = client.get(f"/v1/analytics/traffic?api_id={api_id}&window_min=20").json()
    cursor = full["points"][-2]["bucket"]

    incremental = client.get(
        f"/v1/analytics/traffic?api_id={api_id}&window_min=20&since={cursor}"
    ).json()

    assert len(incremental["points"]) == 1
    assert incremental["points"][0]["bucket"] == full["points"][-1]["bucket"]


# --------------------------------------------------------------------------- #
# Health timeline + request heatmap                                           #
# --------------------------------------------------------------------------- #


def test_health_timeline_scores_each_bucket(session: Session, api: dict[str, object]) -> None:
    """The timeline applies the same ``health_score`` used for the live score."""
    api_id = int(api["id"])
    _seed_requests(session, api_id, minutes=10, per_minute=4)
    compute_rollups(session, window_min=20)
    row = session.get(ApiRegistry, api_id)
    assert row is not None

    result = health_timeline(session, row, window_min=20)

    assert result.points
    assert all(0.0 <= point.score <= 100.0 for point in result.points)


def test_health_timeline_endpoint(
    client: TestClient, session: Session, api: dict[str, object]
) -> None:
    """``GET /v1/analytics/health-timeline`` serves the same shape as the query."""
    api_id = int(api["id"])
    _seed_requests(session, api_id, minutes=10, per_minute=4)
    compute_rollups(session, window_min=20)

    payload = client.get(f"/v1/analytics/health-timeline?api_id={api_id}&window_min=20").json()

    assert payload["api_id"] == api_id
    assert payload["points"]


def test_heatmap_restricts_to_busiest_endpoints(
    client: TestClient, session: Session, api: dict[str, object]
) -> None:
    """The heatmap caps distinct endpoints to the busiest ones by volume."""
    api_id = int(api["id"])
    now = datetime.now(UTC)
    rows = []
    for endpoint_index in range(5):
        endpoint = f"/e{endpoint_index}"
        for minute in range(5):
            rows.append(
                MetricRollup(
                    bucket=minute_bucket(now - timedelta(minutes=minute)),
                    api_id=api_id,
                    endpoint=endpoint,
                    # Endpoint 0 is far busier, so it must survive the cap.
                    req_count=100 if endpoint_index == 0 else 1,
                )
            )
    session.add_all(rows)
    session.commit()

    result = request_heatmap(session, api_id, window_min=20, max_endpoints=1)

    assert result.cells
    assert {cell.endpoint for cell in result.cells} == {"/e0"}


# --------------------------------------------------------------------------- #
# Dirty-flag event bus                                                        #
# --------------------------------------------------------------------------- #


def test_ingest_marks_the_stream_dirty(client: TestClient, api: dict[str, object]) -> None:
    """A new ingested event bumps the version the SSE stream watches for."""
    before = events.version()

    response = client.post(
        "/v1/ingest",
        json=[
            {
                "api_id": int(api["id"]),
                "endpoint": "/pay",
                "method": "POST",
                "status_code": 200,
                "latency_ms": 12.0,
            }
        ],
    )

    assert response.status_code == 202
    assert events.version() != before


# --------------------------------------------------------------------------- #
# SSE                                                                          #
# --------------------------------------------------------------------------- #


def test_stream_emits_heartbeats_and_snapshots(
    client: TestClient, session: Session, api: dict[str, object]
) -> None:
    """``/v1/stream`` pushes both frame types in SSE wire format."""
    _seed_requests(session, int(api["id"]), minutes=3, per_minute=4)
    compute_rollups(session, window_min=10)

    with client.stream("GET", "/v1/stream?limit=2") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["x-accel-buffering"] == "no"
        body = "".join(response.iter_text())

    assert body.count("event: heartbeat") == 2
    assert body.count("event: snapshot") == 2
    assert body.endswith("\n\n")
    assert '"seq":1' in body
    assert '"total_requests":12' in body


def test_registered_apis_are_not_exposed_without_a_token(client: TestClient) -> None:
    """The registry stays authenticated even though analytics is open."""
    assert client.get("/v1/apis").status_code == 401
