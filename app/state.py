from typing import cast
from fastapi import FastAPI
from starlette.datastructures import State

from app.models.state import AppState


def get_state(app_or_state: FastAPI | State) -> AppState:
    state_obj = app_or_state.state if isinstance(app_or_state, FastAPI) else app_or_state
    return cast(AppState, state_obj)
