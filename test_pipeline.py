import os
import random
import sys
from datetime import datetime
import httpx

BASE_URL = os.getenv("PREMEDIA_API_URL", "https://premedia-frontend.onrender.com").rstrip("/")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

DEMO_CAMPAIGNS = [
    {
        "title": "Velvet Noir Cold Brew Can 330ml (Wrap Sleeve)",
        "project_name": "Velvet Noir RTD Coffee Launch",
        "client_name": "Roast & Co. Beverages",
        "sku_prefix": "SKU-VN-330",
        "versions": {
            "v1": "https://images.unsplash.com/photo-1559056199-641a0ac8b55e?auto=format&fit=crop&w=1200&q=80",
            "v2": "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?auto=format&fit=crop&w=1200&q=80",
            "v3": "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?auto=format&fit=crop&w=1200&q=80",
        },
        "v1_feedback": "v1 Feedback: Darken roast background tone by 12% so metallic gold typography pops.",
        "v2_feedback": "v2 Feedback: Contrast is spot on! Shift nutrition panel 3mm inward from seam bleed.",
    },
    {
        "title": "Saffron & Neroli Serum Dropper Box (Foil + Emboss)",
        "project_name": "Lumina Botanicals Festive Edition",
        "client_name": "Lumina Derma Labs",
        "sku_prefix": "SKU-LUM-30",
        "versions": {
            "v1": "https://images.unsplash.com/photo-1611930022073-b7a4ba5fcccd?auto=format&fit=crop&w=1200&q=80",
            "v2": "https://images.unsplash.com/photo-1571781926291-c477ebfd024b?auto=format&fit=crop&w=1200&q=80",
            "v3": "https://images.unsplash.com/photo-1598440947619-2c35fc9aa908?auto=format&fit=crop&w=1200&q=80",
        },
        "v1_feedback": "v1 Feedback: Warm up amber glass highlights and increase Pantone 871C foil border thickness.",
        "v2_feedback": "v2 Feedback: Lighting looks great! Adjust front ingredient callout alignment to center.",
    },
    {
        "title": "Matcha Ceremonial Tin Label & Outer Carton",
        "project_name": "Kyoto Harvest Reserve Line",
        "client_name": "Uji Leaf Artisans",
        "sku_prefix": "SKU-UJI-100",
        "versions": {
            "v1": "https://images.unsplash.com/photo-1582793988951-9aed5509eb97?auto=format&fit=crop&w=1200&q=80",
            "v2": "https://images.unsplash.com/photo-1515823064-d6e0c04616a7?auto=format&fit=crop&w=1200&q=80",
            "v3": "https://images.unsplash.com/photo-1563822249366-3efb23b8e0c9?auto=format&fit=crop&w=1200&q=80",
        },
        "v1_feedback": "v1 Feedback: Boost emerald green saturation on ceremonial seal and sharpen kanji crest.",
        "v2_feedback": "v2 Feedback: Color balance approved! Move net weight badge 2mm above bottom trim line.",
    },
]


def run():
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        print("Set ADMIN_EMAIL and ADMIN_PASSWORD first.", file=sys.stderr)
        sys.exit(1)

    campaign = random.choice(DEMO_CAMPAIGNS)
    suffix = datetime.now().strftime("%H%M%S")
    project_code = f"PRJ-DEMO-{suffix}"
    sku_code = f"{campaign['sku_prefix']}-{suffix[-3:]}"
    assets = campaign["versions"]

    with httpx.Client(base_url=BASE_URL, timeout=45.0) as client:
        login = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        login.raise_for_status()
        hdr = {"Authorization": f"Bearer {login.json()['token']}"}

        # 1. Ingest v1 Job
        job = client.post(
            "/api/jobs",
            headers=hdr,
            json={
                "title": campaign["title"],
                "project_code": project_code,
                "project_name": campaign["project_name"],
                "client_name": campaign["client_name"],
                "sku_code": sku_code,
                "complexity_tier": "complex",
                "sla_hours": 48,
                "estimated_hours": 4.5,
                "billable_amount": 8500.0,
                "billing_currency": "INR",
                "priority": "high",
                "file_url": assets["v1"],
            },
        ).json()
        jid = job["id"]
        print(f"Created Demo Job #{jid}: {project_code} — {campaign['title']} (v1)")

        # 2. v1 -> QC -> Proofing -> Client Rejects v1
        client.patch(f"/api/jobs/{jid}/allocate", headers=hdr, json={"assignedTo": "John OR"})
        client.patch(f"/api/jobs/{jid}/command", headers=hdr, json={"commandName": "START_WORK", "payload": {"status": "active"}})
        client.patch(f"/api/jobs/{jid}/command", headers=hdr, json={"commandName": "SUBMIT_QC", "payload": {"status": "qc", "sessionHours": 1.5, "fileUrl": assets["v1"]}})
        client.patch(f"/api/jobs/{jid}/command", headers=hdr, json={"commandName": "QC_PASS", "payload": {"status": "review"}})
        client.patch(
            f"/api/jobs/{jid}/command",
            headers=hdr,
            json={"commandName": "CLIENT_REJECT", "payload": {"status": "rework", "notes": campaign["v1_feedback"]}},
        )
        print("Logged v1 Client Rejection -> Rework (v2)")

        # 3. v2 -> QC -> Proofing -> Client Rejects v2
        client.patch(f"/api/jobs/{jid}/command", headers=hdr, json={"commandName": "START_WORK", "payload": {"status": "active"}})
        client.patch(f"/api/jobs/{jid}/command", headers=hdr, json={"commandName": "SUBMIT_QC", "payload": {"status": "qc", "sessionHours": 1.0, "fileUrl": assets["v2"]}})
        client.patch(f"/api/jobs/{jid}/command", headers=hdr, json={"commandName": "QC_PASS", "payload": {"status": "review"}})
        client.patch(
            f"/api/jobs/{jid}/command",
            headers=hdr,
            json={"commandName": "CLIENT_REJECT", "payload": {"status": "rework", "notes": campaign["v2_feedback"]}},
        )
        print("Logged v2 Client Rejection -> Rework (v3)")

        # 4. v3 -> QC -> Parked in Client Proofing (v3)
        client.patch(f"/api/jobs/{jid}/command", headers=hdr, json={"commandName": "START_WORK", "payload": {"status": "active"}})
        client.patch(f"/api/jobs/{jid}/command", headers=hdr, json={"commandName": "SUBMIT_QC", "payload": {"status": "qc", "sessionHours": 0.75, "fileUrl": assets["v3"]}})
        client.patch(f"/api/jobs/{jid}/command", headers=hdr, json={"commandName": "QC_PASS", "payload": {"status": "review"}})
        print(f"Ready for Demo! Job #{jid} ({project_code}) is parked in Stage 07: Client Proofing at v3 (3.25h banked).")


if __name__ == "__main__":
    run()