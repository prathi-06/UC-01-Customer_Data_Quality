import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from app.routes import router

app = FastAPI(title="Customer Data Quality SaaS", docs_url=None, redoc_url=None, openapi_url=None)

@app.exception_handler(HTTPException)
def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "HTTP_ERROR", "message": str(exc.detail)}}
    )

# Include API routes
app.include_router(router)

# Mount web/dist static files if present (no CORS, same origin)
web_dist_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "dist")
if os.path.isdir(web_dist_dir):
    app.mount("/", StaticFiles(directory=web_dist_dir, html=True), name="static")
