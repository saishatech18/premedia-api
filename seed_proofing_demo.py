import os
import sys
import httpx

BASE_URL = os.getenv("PREMEDIA_API_URL", "https://premedia-frontend.onrender.com").rstrip("/")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# Distinct high-resolution visual variations representing v1, v2, and v3 iterations
VERSION_ASSETS = {
    "v1": "https://images.unsplash.com/photo-1620916566398-39f1143ab7be?auto=format&fit=crop&w=1200&q=80",
    "v2": "https://images.unsplash.com/photo-1608248543803-ba4f8c70ae0b?auto=format&fit=crop&w=1200&q=80",
    "v3": "https://images.unsplash.com/photo-1556228578-0d85b1a4d571?auto=format&fit=crop&w=1200&q=80",
}


def run():
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        print("Set ADMIN_EMAIL and ADMIN_PASSWORD first.", file=sys.stderr)
        sys.exit(1)

    with httpx.Client(base_url=BASE_URL, timeout=45.0) as client:
        login = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        login.raise_for_status()
        hdr = {"Authorization": f"Bearer {login.json()['token']}"}

        # 1. Ingest v1 Job
        job = client.post(
            "/api/jobs",
            headers=hdr,
            json={
                "title": "Aether Botanicals 50ml Foil Carton (Front & Back)",
                "project_code": "PRJ-DEMO-2026",
                "project_name": "Aether Holiday Luxury Relaunch",
                "client_name": "Aether Skincare Co.",
                "sku_code": "SKU-AETH-50ML",
                "complexity_tier": "complex",
                "sla_hours": 48,
                "estimated_hours": 4.5,
                "billable_amount": 8500.0,
                "billing_currency": "INR",
                "priority": "high",
                "file_url": VERSION_ASSETS["v1"],
            },
        ).json()
        jid = job["id"]
        print(f"Created Demo Job #{jid}: {job['projectCode']} (v1)")

        # 2. Allocate & Submit v1 -> QC -> Proofing -> Client Rejects v1
        client.patch(f"/api/jobs/{jid}/allocate", headers=hdr, json={"assignedTo": "John OR"})
        client.patch(f"/api/jobs/{jid}/command", headers=hdr, json={"commandName": "START_WORK", "payload": {"status": "active"}})
        client.patch(f"/api/jobs/{jid}/command", headers=hdr, json={"commandName": "SUBMIT_QC", "payload": {"status": "qc", "sessionHours": 1.5, "fileUrl": VERSION_ASSETS["v1"]}})
        client.patch(f"/api/jobs/{jid}/command", headers=hdr, json={"commandName": "QC_PASS", "payload": {"status": "review"}})
        client.patch(
            f"/api/jobs/{jid}/command",
            headers=hdr,
            json={
                "commandName": "CLIENT_REJECT",
                "payload": {
                    "status": "rework",
                    "notes": "v1 Feedback: Gold foil logo needs +15% contrast and warmer amber background tone.",
                },
            },
        )
        print("Logged v1 Client Rejection -> Rework (v2)")

        # 3. Studio Rework v2 -> QC -> Proofing -> Client Rejects v2
        client.patch(f"/api/jobs/{jid}/command", headers=hdr, json={"commandName": "START_WORK", "payload": {"status": "active"}})
        client.patch(f"/api/jobs/{jid}/command", headers=hdr, json={"commandName": "SUBMIT_QC", "payload": {"status": "qc", "sessionHours": 1.0, "fileUrl": VERSION_ASSETS["v2"]}})
        client.patch(f"/api/jobs/{jid}/command", headers=hdr, json={"commandName": "QC_PASS", "payload": {"status": "review"}})
        client.patch(
            f"/api/jobs/{jid}/command",
            headers=hdr,
            json={
                "commandName": "CLIENT_REJECT",
                "payload": {
                    "status": "rework",
                    "notes": "v2 Feedback: Lighting looks great! Please shift botanical prop framing slightly left for bleed safety.",
                },
            },
        )
        print("Logged v2 Client Rejection -> Rework (v3)")

        # 4. Studio Final Polish v3 -> QC -> Parked in Client Proofing (v3)
        client.patch(f"/api/jobs/{jid}/command", headers=hdr, json={"commandName": "START_WORK", "payload": {"status": "active"}})
        client.patch(f"/api/jobs/{jid}/command", headers=hdr, json={"commandName": "SUBMIT_QC", "payload": {"status": "qc", "sessionHours": 0.75, "fileUrl": VERSION_ASSETS["v3"]}})
        client.patch(f"/api/jobs/{jid}/command", headers=hdr, json={"commandName": "QC_PASS", "payload": {"status": "review"}})
        print(f"Ready for Demo! Job #{jid} is now parked in Stage 07: Client Proofing at v3 (3.25h banked).")


if __name__ == "__main__":
    run()