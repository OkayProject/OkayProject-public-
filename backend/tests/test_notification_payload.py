from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_missing_alert_payload_uses_null_risk_level():
    from backend.main import create_push_alert_payload

    payload = create_push_alert_payload(
        expo_push_token=None,
        user_id=1,
        alert_type="missing",
        risk_level=None,
        title="실종 알림",
        body="근처 실종자 정보를 확인해주세요.",
        meta="{}",
    )

    assert payload["data"]["type"] == "missing"
    assert payload["data"]["risk_level"] is None


def test_flood_alert_payload_normalizes_korean_risk_level():
    from backend.main import create_push_alert_payload

    payload = create_push_alert_payload(
        expo_push_token=None,
        user_id=1,
        alert_type="flood",
        risk_level="긴급",
        title="침수 긴급 알림",
        body="즉시 안전한 곳으로 이동해주세요.",
        meta="{}",
    )

    assert payload["data"]["type"] == "flood"
    assert payload["data"]["risk_level"] == "emergency"


def test_expo_push_token_validation_accepts_expo_token_formats():
    from backend.main import is_valid_expo_push_token

    assert is_valid_expo_push_token("ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]")
    assert is_valid_expo_push_token("ExpoPushToken[xxxxxxxxxxxxxxxxxxxxxx]")
    assert not is_valid_expo_push_token("not-a-token")


def test_send_test_notification_builds_expo_payload_without_network():
    import json
    import backend.main as backend_main

    sent_payloads = []
    original_sender = backend_main.send_expo_push_notification

    def fake_sender(payload):
        sent_payloads.append(payload)
        return {"data": {"status": "ok", "id": "ticket-id"}}

    backend_main.send_expo_push_notification = fake_sender

    try:
        response = backend_main.send_test_notification(
            backend_main.SendTestNotificationRequest(
                expo_push_token="ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]",
                type="missing",
                title="실종 알림",
                body="근처 실종자 정보를 확인해주세요.",
                meta="{}",
            )
        )
    finally:
        backend_main.send_expo_push_notification = original_sender

    response_body = json.loads(response.body.decode("utf-8"))

    assert response.status_code == 200
    assert response_body["expo_response"]["data"]["status"] == "ok"
    assert sent_payloads[0]["to"] == "ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]"
    assert sent_payloads[0]["data"]["type"] == "missing"
    assert sent_payloads[0]["data"]["risk_level"] is None


if __name__ == "__main__":
    test_missing_alert_payload_uses_null_risk_level()
    test_flood_alert_payload_normalizes_korean_risk_level()
    test_expo_push_token_validation_accepts_expo_token_formats()
    test_send_test_notification_builds_expo_payload_without_network()
    print("notification payload tests passed")
