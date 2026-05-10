"""
MeterHub Installer UI - FastAPI application

Engineering commissioning tool: setup wizard, meter test, status pages, OTA updates.

HTTPS only (self-signed cert). Single installer login. Fail2ban-style lockout.
Auto-shutdown of Wi-Fi AP after 30 minutes.
"""

from fastapi import FastAPI
import logging

logger = logging.getLogger(__name__)

app = FastAPI(
    title="MeterHub Installer UI",
    description="Engineering commissioning interface for MeterHub devices",
    version="1.0.0",
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/")
async def redirect_to_setup():
    """Redirect to setup page."""
    # Phase 4: Implement setup wizard
    return {"message": "MeterHub Installer UI"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8443)
