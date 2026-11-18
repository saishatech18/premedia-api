import os
import sys
import httpx

BASE_URL = os.getenv("PREMEDIA_API_URL", "https://premedia-api.onrender.com").rstrip("/")

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
OPERATOR_EMAIL = os.getenv("OPERATOR_EMAIL", "")
OPERATOR_PASSWORD = os.getenv("OPERATOR_PASSWORD", "")
CLIENT_EMAIL = os.getenv("CLIENT_EMAIL", "")
CLIENT_PASSWORD = os.getenv("CLIENT_PASSWORD", "")


def login(client: httpx.Client, email: str, password: str) -> dict:
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, f"Login failed for {email}: {res.status_code} {res.text}"
    return res.json()


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def run_e2e():
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        print("ERROR: Set ADMIN_EMAIL and ADMIN_PASSWORD environment variables first.", file=sys.stderr)
        sys.exit(1)

    with httpx.Client(base_url=BASE_URL, timeout=45.0) as client:
        print(f"1. Health Check -> {BASE_URL}/")
        health = client.get("/")
        assert health.status_code == 200, f"Health check failed: {health.status_code}"
        print("   API reachable.")

        print(f"2. Authenticating Admin ({ADMIN_EMAIL})...")
        admin_session = login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
        admin_hdr = auth_headers(admin_session["token"])

        print("3. Stage 01 (Intake): Creating test deliverable...")
        create_res = client.post(
            "/api/jobs",
            headers=admin_hdr,
            json={
                "title": "E2E Automated Verification Pack",
                "project_code": "PRJ-E2E-999",
                "project_name": "E2E Verification Campaign",
                "client_name": "Test Client Ltd",
                "sku_code": "SKU-E2E-01",
                "complexity_tier": "standard",
                "sla_hours": 24,
                "estimated_hours": 2.0,
                "billable_amount": 2500.0,
                "billing_currency": "INR",
                "priority": "normal",
            },
        )
        assert create_res.status_code == 201, f"Job creation failed: {create_res.status_code} {create_res.text}"
        job = create_res.json()
        job_id = job["id"]
        assert job["status"] == "new", f"Expected status 'new', got {job['status']}"
        assert job["actualHours"] == 0.0, f"Expected 0.0 actualHours, got {job['actualHours']}"
        assert job["workStartedAt"] is None, "Clock should be paused on creation"
        print(f"   Job #{job_id} created (status=new, actualHours=0.00, clock=paused).")

        print("4. Stage 02 (Allocation): Dispatching to operator...")
        alloc_res = client.patch(
            f"/api/jobs/{job_id}/allocate",
            headers=admin_hdr,
            json={
                "assignedTo": "John OR",
                "priority": "high",
                "allocationNotes": '[PLAN:{"mode":"single","operators":["John OR"]}]',
            },
        )
        assert alloc_res.status_code == 200, f"Allocation failed: {alloc_res.status_code} {alloc_res.text}"
        alloc_job = alloc_res.json()
        assert alloc_job["status"] == "new", "Allocated job should stay 'new' until Studio pickup"
        assert alloc_job["workStartedAt"] is None, "Clock must remain paused after allocation"
        print("   Allocated to John OR (clock still paused at 0.00h).")

        print("5. Stage 05 (Studio): Starting Studio Work...")
        start_res = client.patch(
            f"/api/jobs/{job_id}/command",
            headers=admin_hdr,
            json={"commandName": "START_WORK", "payload": {"status": "active"}},
        )
        assert start_res.status_code == 200, f"Start work failed: {start_res.status_code} {start_res.text}"
        active_job = start_res.json()
        assert active_job["status"] == "active"
        assert active_job["workStartedAt"] is not None, "Clock should have started"
        print("   Shift clock started (status=active).")

        print("6. Stage 06 (QC): Submitting deliverable with 1.25h effort...")
        qc_res = client.patch(
            f"/api/jobs/{job_id}/command",
            headers=admin_hdr,
            json={
                "commandName": "SUBMIT_QC",
                "payload": {
                    "status": "qc",
                    "sessionHours": 1.25,
                    "fileUrl": "https://drive.google.com/file/d/e2e-test/view",
                },
            },
        )
        assert qc_res.status_code == 200, f"QC handoff failed: {qc_res.status_code} {qc_res.text}"
        qc_job = qc_res.json()
        assert qc_job["status"] == "qc"
        assert qc_job["actualHours"] == 1.25
        assert qc_job["workStartedAt"] is None, "Clock must stop when submitted to QC"
        print("   Banked 1.25h and paused clock (status=qc).")

        print("7. Stage 07 (Proofing) -> Approved...")
        proof_res = client.patch(
            f"/api/jobs/{job_id}/command",
            headers=admin_hdr,
            json={"commandName": "QC_PASS", "payload": {"status": "review"}},
        )
        assert proof_res.status_code == 200 and proof_res.json()["status"] == "review"

        approve_res = client.patch(
            f"/api/jobs/{job_id}/command",
            headers=admin_hdr,
            json={"commandName": "CLIENT_APPROVE", "payload": {"status": "approved"}},
        )
        assert approve_res.status_code == 200
        approved_job = approve_res.json()
        assert approved_job["status"] == "approved"
        assert approved_job["billingStatus"] == "ready_to_invoice"
        print("   Approved and queued for billing (billingStatus=ready_to_invoice).")

        print("8. Stage 08 (Billing & Invoicing): Testing Invoiced -> Paid transitions...")
        inv_res = client.patch(
            f"/api/jobs/{job_id}/command",
            headers=admin_hdr,
            json={"commandName": "UPDATE_BILLING", "payload": {"billingStatus": "invoiced"}},
        )
        assert inv_res.status_code == 200 and inv_res.json()["billingStatus"] == "invoiced"

        paid_res = client.patch(
            f"/api/jobs/{job_id}/command",
            headers=admin_hdr,
            json={"commandName": "UPDATE_BILLING", "payload": {"billingStatus": "paid"}},
        )
        assert paid_res.status_code == 200 and paid_res.json()["billingStatus"] == "paid"
        print("   Billing lifecycle verified (ready_to_invoice -> invoiced -> paid).")

        if OPERATOR_EMAIL and OPERATOR_PASSWORD:
            print(f"9a. Testing Operator RBAC restrictions ({OPERATOR_EMAIL})...")
            op_session = login(client, OPERATOR_EMAIL, OPERATOR_PASSWORD)
            op_hdr = auth_headers(op_session["token"])
            op_bill = client.patch(
                f"/api/jobs/{job_id}/command",
                headers=op_hdr,
                json={"commandName": "UPDATE_BILLING", "payload": {"billingStatus": "unbilled"}},
            )
            assert op_bill.status_code == 403, f"Expected 403 for operator billing edit, got {op_bill.status_code}"
            print("   Operator blocked from billing changes (403 Forbidden).")

        if CLIENT_EMAIL and CLIENT_PASSWORD:
            print(f"9b. Testing Client RBAC restrictions ({CLIENT_EMAIL})...")
            cli_session = login(client, CLIENT_EMAIL, CLIENT_PASSWORD)
            cli_hdr = auth_headers(cli_session["token"])
            forbidden_alloc = client.patch(
                f"/api/jobs/{job_id}/allocate",
                headers=cli_hdr,
                json={"assignedTo": "Unauthorized"},
            )
            assert forbidden_alloc.status_code == 403, f"Expected 403 for client allocate, got {forbidden_alloc.status_code}"
            print("   Client blocked from allocation (403 Forbidden).")

        print(f"\nALL E2E CHECKS PASSED! (Test Job #{job_id} - PRJ-E2E-999)")


if __name__ == "__main__":
    try:
        run_e2e()
    except AssertionError as exc:
        print(f"\nTEST FAILED: {exc}", file=sys.stderr)
        sys.exit(1)