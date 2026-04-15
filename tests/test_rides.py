from datetime import datetime, timedelta, timezone


def test_create_and_search_ride(client, auth_headers) -> None:
    departure_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    create_response = client.post(
        "/api/v1/rides",
        headers=auth_headers,
        json={
            "origin": "Delhi",
            "destination": "Gurugram",
            "departure_time": departure_time,
            "available_seats": 3,
            "price_per_seat": 250,
            "vehicle_details": "White Swift",
            "notes": "No smoking",
        },
    )

    assert create_response.status_code == 201
    assert create_response.json()["origin"] == "Delhi"

    search_response = client.get("/api/v1/rides", params={"origin": "Del", "destination": "Guru"})
    assert search_response.status_code == 200
    assert len(search_response.json()) == 1
    assert search_response.json()[0]["destination"] == "Gurugram"
