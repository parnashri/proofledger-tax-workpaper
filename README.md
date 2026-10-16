# ProofLedger

Evidence-focused tax workpaper for the fictional Okafor–Lindqvist 2025 return.

## Run locally

Requires Python 3.10 or later.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 server.py --port 8081
```

Open http://127.0.0.1:8081. In local demo mode, choose a staff identity and use `proofledger-demo` as the password. Leave the MFA field blank.

The workpaper saves to a SQLite database in the project folder. This file is created on first run and is not included in the submission. Keep it if you want to preserve local review work.

## Structure

- `server.py`: HTTP API, shared review state, role checks and audit log
- `workflow.py`: client invitations, review approvals, filing and notices
- `firm.py`: engagement workspaces and evidence storage
- `security.py`, `provision_staff.py`: individual credentials and optional MFA
- `index.html`, `client.html`, `static/`: staff and client interfaces
- `packet.json`: unmodified case-study dataset
- `tests/`: data consistency, workflow, security and browser smoke tests
- `docs/Architecture.pdf`: one-page design and data model
- `docs/Error_Findings.pdf`: identified discrepancies and source references

## Run tests

```bash
python3 -m unittest discover -s tests -p 'test_packet_checks.py' -v
python3 tests/test_firm_security.py
```

To run the filing workflow test, start a **separate** demo-mode server with a disposable database on port 8138. Then run `python3 tests/test_people_filing.py`. Do not run integration tests against a workpaper you want to keep. The optional browser smoke tests require Playwright and Chromium.

## Deployment and limitations

`Dockerfile` is provided for a container deployment. Public hosting needs HTTPS, a persistent volume for SQLite, a private `PROOFLEDGER_DB` path, a persistent `PROOFLEDGER_EVIDENCE_KEY`, and `PROOFLEDGER_STRICT_AUTH=1`. Provision individual staff passwords with `provision_staff.py`. Never expose the shared demo password publicly.

The packet's tax engine cannot be rerun. Adjustments are review overlays with estimated tax effects, not complete return recalculations. Government responses are scripted, and client acknowledgments are not certified e-signatures. This system has not undergone a production security review; do not use real taxpayer information.

AI tools were used for parts of development and testing. The findings were checked against the supplied fictional packet; full integration and production hardening remain outside this prototype.
