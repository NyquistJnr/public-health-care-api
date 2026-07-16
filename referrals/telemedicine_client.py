import httpx
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class TelemedicineClient:
    def __init__(self):
        self.base_url = settings.TELEMEDICINE_API_URL.rstrip('/')
        self.api_key = settings.TELEMEDICINE_API_KEY
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def create_session(self, title, duration_minutes, scheduled_for, participants, medical_data):
        url = f"{self.base_url}/sessions/"
        payload = {
            "title": title,
            "duration_minutes": duration_minutes,
            "participants": participants,
            "medical_data": medical_data
        }
        if scheduled_for:
            payload["scheduled_for"] = scheduled_for

        try:
            with httpx.Client() as client:
                response = client.post(url, json=payload, headers=self.headers, timeout=10.0)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to create telemedicine session: {str(e)}")
            raise e

    def extend_session(self, session_id, extend_minutes):
        url = f"{self.base_url}/sessions/{session_id}/extend"
        payload = {"extend_minutes": extend_minutes}
        try:
            with httpx.Client() as client:
                response = client.post(url, json=payload, headers=self.headers, timeout=10.0)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to extend telemedicine session: {str(e)}")
            raise e

    def end_session(self, session_id):
        url = f"{self.base_url}/sessions/{session_id}/end"
        try:
            with httpx.Client() as client:
                response = client.post(url, headers=self.headers, timeout=10.0)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to end telemedicine session: {str(e)}")
            raise e
