"""Firestore client setup."""

from functools import lru_cache
from pathlib import Path

from google.cloud import firestore
from google.oauth2 import service_account

from .config import settings


@lru_cache
def get_firestore_client() -> firestore.Client:
    """Create and cache a Firestore client.

    The Google Cloud SDK automatically uses GOOGLE_APPLICATION_CREDENTIALS
    when it is set, or the default application credentials on Google Cloud.
    """

    if settings.google_application_credentials:
        credential_path = Path(settings.google_application_credentials)
        credentials = service_account.Credentials.from_service_account_file(
            credential_path
        )
        return firestore.Client(
            project=settings.google_cloud_project or credentials.project_id,
            credentials=credentials,
        )

    if settings.google_cloud_project:
        return firestore.Client(project=settings.google_cloud_project)
    return firestore.Client()
