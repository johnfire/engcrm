"""Income calculator: a manual, unsaved annual estimate of income, VAT and tax.

Everyone who can see the Forecast can use it. The figures live only in the request
and the response: nothing is stored, logged or put in a URL. Parsing is in
gcrm.income_calculator.form, the maths in gcrm.income_calculator.estimate.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from gcrm.api.auth import require_login
from gcrm.api.templates import templates
from gcrm.income_calculator.estimate import calculate_estimates
from gcrm.income_calculator.form import IncomeCalculatorForm

router = APIRouter(
    prefix="/income-calculator", tags=["income-calculator"], dependencies=[Depends(require_login)]
)


def render(request: Request, values: dict, estimates=(), error: bool = False) -> HTMLResponse:
    return templates.TemplateResponse(
        "income_calculator.html",
        {"request": request, "values": values, "estimates": estimates, "error": error},
        status_code=422 if error else 200,
    )


@router.get("", response_class=HTMLResponse)
def income_calculator_page(request: Request):
    return render(request, IncomeCalculatorForm().model_dump(mode="json"))


@router.post("", response_class=HTMLResponse)
async def income_calculator_estimate(request: Request):
    entered = {key: str(value) for key, value in (await request.form()).items()}
    try:
        form = IncomeCalculatorForm.model_validate(entered)
    except ValidationError:
        # Never echo the validation structure: it contains the entered figures.
        return render(request, entered, error=True)
    return render(request, form.model_dump(mode="json"), calculate_estimates(form.to_inputs()))
