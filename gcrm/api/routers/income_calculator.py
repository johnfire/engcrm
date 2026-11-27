"""Income calculator: an annual estimate of income, VAT and tax.

Everyone who can see the Forecast can use it. A signed-in account's figures are saved when
it calculates, encrypted and visible only to that account (gcrm.tools.db_income_inputs);
they are never logged or put in a URL. Storage failing never stops the calculation. Parsing
is in gcrm.income_calculator.form, the maths in gcrm.income_calculator.estimate. Income
can come from the typed fields or from the Forecast (gcrm.tools.forecast_income).
"""
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from gcrm.api.auth import require_login
from gcrm.api.redirects import local_redirect
from gcrm.api.session_workspace import session_workspace_id
from gcrm.api.templates import templates
from gcrm.income_calculator.estimate import calculate_estimates
from gcrm.income_calculator.form import IncomeCalculatorForm
from gcrm.tools.db_income_inputs import delete_inputs, load_inputs, save_inputs
from gcrm.tools.forecast_income import get_forecast_income
from gcrm.workspace_context import workspace_scope

logger = logging.getLogger(__name__)
# The year estimated. gcrm.income_calculator holds the law in force from 2026, which still applies
# to this year: a 2027 reform was only a draft when this was written (2026-11-27). When a new law
# is promulgated, its figures replace those in income_2026.py (and the law note on the page).
TAX_YEAR = 2027
router = APIRouter(
    prefix="/income-calculator", tags=["income-calculator"], dependencies=[Depends(require_login)]
)


def account_id(request: Request) -> int | None:
    """The signed-in account, or None for the shared admin login, which has no account row."""
    return request.session.get("user_id")


def render(request: Request, user_id: int | None, values: dict, estimates=(), error: bool = False,
           notice: str = "", forecast=None, forecast_failed: bool = False) -> HTMLResponse:
    context = {"request": request, "values": values, "estimates": estimates, "error": error,
               "notice": notice, "can_save": user_id is not None, "forecast": forecast,
               "forecast_failed": forecast_failed, "tax_year": TAX_YEAR}
    return templates.TemplateResponse("income_calculator.html", context, status_code=422 if error else 200)


def _calculate(request: Request, form: IncomeCalculatorForm) -> dict:
    """The estimates, and in Forecast mode what the Forecast contributed. If the Forecast
    cannot be read there is no result: typed figures must never stand in for it unnoticed."""
    if form.income_source == "manual":
        return {"estimates": calculate_estimates(form.to_inputs())}
    try:
        workspace_id = session_workspace_id(request)
        with workspace_scope(workspace_id):
            income = get_forecast_income(
                workspace_id, TAX_YEAR, include_expected=form.include_expected,
                include_possible=form.include_possible, possible_as=form.possible_as)
    except Exception as error:
        logger.warning("forecast income unavailable: %s", type(error).__name__)
        return {"forecast_failed": True}
    inputs = form.to_inputs(consulting=income.consulting, education=income.teaching)
    return {"estimates": calculate_estimates(inputs), "forecast": income}


def _saved_form(user_id: int | None) -> tuple[IncomeCalculatorForm | None, str]:
    """(the account's saved figures, or None; a notice key when they could not be read)."""
    if user_id is None:
        return None, ""
    try:
        saved = load_inputs(user_id)
        return (IncomeCalculatorForm.model_validate(saved) if saved else None), ""
    except Exception as error:
        # Only the error's type: its message can contain the figures.
        logger.warning("saved calculator figures unavailable: %s", type(error).__name__)
        return None, "incomeCalc.loadFailed"


@router.get("", response_class=HTMLResponse)
def income_calculator_page(request: Request, user_id: int | None = Depends(account_id)):
    form, notice = _saved_form(user_id)
    if form is None:
        return render(request, user_id, IncomeCalculatorForm().model_dump(mode="json"), notice=notice)
    return render(request, user_id, form.model_dump(mode="json"), **_calculate(request, form))


@router.post("", response_class=HTMLResponse)
async def income_calculator_estimate(request: Request, user_id: int | None = Depends(account_id)):
    entered = {key: str(value) for key, value in (await request.form()).items()}
    try:
        form = IncomeCalculatorForm.model_validate(entered)
    except ValidationError:
        # Never echo the validation structure: it contains the entered figures.
        return render(request, user_id, entered, error=True)
    values = form.model_dump(mode="json")
    notice = ""
    if user_id is not None:
        try:
            await run_in_threadpool(save_inputs, user_id, values)
            notice = "incomeCalc.saved"
        except Exception as error:
            logger.warning("calculator figures not saved: %s", type(error).__name__)
            notice = "incomeCalc.saveFailed"
    result = await run_in_threadpool(_calculate, request, form)
    return render(request, user_id, values, notice=notice, **result)


@router.post("/clear")
def clear_saved_figures(user_id: int | None = Depends(account_id)):
    if user_id is not None:
        delete_inputs(user_id)
    return local_redirect("/income-calculator")
