"""
push_service.py — Firebase Cloud Messaging via firebase-admin SDK.

Requires FIREBASE_SERVICE_ACCOUNT_JSON env var containing the service account
JSON as a string. Silently no-ops if the env var is absent (local dev).
"""
import json
import os

_app = None


def _get_app():
    global _app
    if _app is not None:
        return _app
    sa_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
    if not sa_json:
        print('[push] FIREBASE_SERVICE_ACCOUNT_JSON not set — push disabled')
        return None
    try:
        import firebase_admin
        from firebase_admin import credentials
        cred = credentials.Certificate(json.loads(sa_json))
        _app = firebase_admin.initialize_app(cred)
        print('[push] Firebase Admin SDK initialised')
    except Exception as e:
        print(f'[push] Firebase init failed: {e}')
        return None
    return _app


def send_game_result(
    fcm_token: str,
    team_name: str,
    my_score: int,
    opp_score: int,
    opponent_name: str,
) -> None:
    if not _get_app():
        return
    try:
        from firebase_admin import messaging
        won  = my_score > opp_score
        lost = my_score < opp_score
        result_word = 'won' if won else 'lost' if lost else 'tied'
        body = (
            f'Your {team_name} {result_word} {my_score}–{opp_score} against {opponent_name}. '
            f'Check for injuries and set your game plan.'
        )
        message = messaging.Message(
            notification=messaging.Notification(title='Game Result', body=body),
            token=fcm_token,
        )
        messaging.send(message)
        print(f'[push] Sent to {team_name}: {result_word}')
    except Exception as e:
        print(f'[push] Send failed for {team_name}: {e}')
