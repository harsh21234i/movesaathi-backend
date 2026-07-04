from app.core.metrics import metrics


def test_metrics_endpoint_exposes_request_and_job_counters(client) -> None:
    client.get("/health")
    metrics.record_job(name="demo-job", status="success")
    metrics.record_dispatch(event="request_created", outcome="success")
    metrics.record_payment(event="payment_created")

    response = client.get("/metrics")

    assert response.status_code == 200
    body = response.text
    assert 'moovesaathi_requests_total{method="GET",path="/health",status="200"} 1' in body
    assert 'moovesaathi_jobs_total{job="demo-job",status="success"} 1' in body
    assert 'moovesaathi_dispatch_total{event="request_created",outcome="success"} 1' in body
    assert 'moovesaathi_payment_total{event="payment_created",outcome="success"} 1' in body


def test_metrics_capture_exceptions(client) -> None:
    response = client.get("/api/v1/nonexistent")

    assert response.status_code == 404
    metrics_body = client.get("/metrics").text
    assert 'moovesaathi_exceptions_total{code="not_found"} 1' in metrics_body
