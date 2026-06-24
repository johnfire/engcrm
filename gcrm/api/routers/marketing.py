from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from gcrm.api.templates import templates
from gcrm.api.auth import require_login

router = APIRouter(dependencies=[Depends(require_login)])


@router.get("/marketing/", response_class=HTMLResponse)
def marketing_page(request: Request):
    return templates.TemplateResponse("marketing.html", {
        "request": request,
        "strategies": [],
        "digest": None,
        "archive": [],
    })
