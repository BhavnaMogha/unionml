import runpy
import subprocess
import time
from contextlib import contextmanager

import pytest
import requests
from sklearn.utils.validation import check_is_fitted


def _app(ml_framework: str, *args, port: str = "8000"):
    """Transient app server for testing."""
    process = subprocess.Popen(
        ["unionml", "serve", f"tests.integration.{ml_framework}_app.fastapi_app:app", "--port", port, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if len(process.stderr.peek().decode()) == 0:  # type: ignore
        _wait_to_exist(port)
    try:
        yield process
    finally:
        process.terminate()


def _wait_to_exist(port):
    for _ in range(30):
        try:
            requests.get(f"http://127.0.0.1:{port}/")
            break
        except Exception:  # pylint: disable=broad-except
            time.sleep(1.0)


@pytest.mark.parametrize(
    "ml_framework, model_cls_name, model_checker",
    [
        ("sklearn", "LogisticRegression", check_is_fitted),
        ("pytorch", "PytorchModel", None),
        ("keras", "Sequential", None),
    ],
    ids=["sklearn", "pytorch", "keras"],
)
def test_module(ml_framework, model_cls_name, model_checker):
    module_vars = runpy.run_module(f"tests.integration.{ml_framework}_app.quickstart", run_name="__main__")
    model_object = module_vars["model_object"]
    predictions = module_vars["predictions"]

    model_cls = module_vars[model_cls_name]
    assert isinstance(model_object, model_cls)
    if model_checker:
        model_checker(model_object)

    assert all([isinstance(x, float) and 0 <= x <= 9 for x in predictions])


@pytest.mark.parametrize(
    "ml_framework, filename",
    [
        ("sklearn", "model.joblib"),
        ("pytorch", "model.pt"),
        ("keras", "model.h5"),
    ],
    ids=["sklearn", "pytorch", "keras"],
)
def test_fastapi_app(ml_framework, filename, tmp_path):
    # run the quickstart module to train a model
    model_path = tmp_path / filename
    module_vars = runpy.run_module(f"tests.integration.{ml_framework}_app.quickstart", run_name="__main__")

    # extract unionml model and model_object from module global namespace
    model = module_vars["model"]
    model.save(model_path)
    n_samples = 5

    with contextmanager(_app)(ml_framework, "--model-path", str(model_path)):
        api_request_vars = runpy.run_module("tests.integration.api_requests", run_name="__main__")
        prediction_response = api_request_vars["prediction_response"]
        output = prediction_response.json()
        assert len(output) == n_samples
        assert all(isinstance(x, float) for x in output)


def test_fastapi_app_no_model():
    # excluding the --model-path argument should raise an error since the unionml.Model object
    # doesn't have a model_artifact attribute set yet
    with contextmanager(_app)("sklearn", port="8001") as process:
        error_msg = process.stderr.read().decode().splitlines()[-1]
        assert error_msg.startswith("ValueError: Model artifact path not specified")
