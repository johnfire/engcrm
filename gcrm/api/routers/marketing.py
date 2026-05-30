from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from gcrm.api.auth import require_login

router = APIRouter(dependencies=[Depends(require_login)])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "ui" / "templates"))


@router.get("/marketing/", response_class=HTMLResponse)
def marketing_page(request: Request):
    return templates.TemplateResponse("marketing.html", {
        "request": request,
        "strategies": [],
        "digest": None,
        "archive": [],
    })
