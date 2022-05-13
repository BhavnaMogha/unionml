"""Utilities for the FastAPI integration."""

import os
from typing import Any, Dict, List, Optional, Union

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from unionml.model import Model, ModelArtifact
from unionml.remote import get_model_artifact


def serving_app(model: Model, app: FastAPI, remote: bool = False, model_version: str = "latest"):

    model_path = os.getenv("UNIONML_MODEL_PATH")
    if model.artifact is None:
        if not remote:
            if model.artifact is None and model_path is None:
                raise ValueError(
                    "Model artifact path not specified. Make sure to specify the unionml serve --model-path in "
                    "the option when starting the unionml prediction service in local mode."
                )
            model.artifact = ModelArtifact(model.load(model_path))
        else:
            model.artifact = get_model_artifact(model, model_version=model_version)

    @app.get("/", response_class=HTMLResponse)
    def root():
        return """
            <html>
                <head>
                    <title>unionml</title>
                </head>
                <body>
                    <h1>unionml</h1>
                    <p>The easiest way to build and deploy models</p>
                </body>
            </html>
        """

    @app.post("/predict")
    async def predict(
        inputs: Optional[Union[Dict[str, Any], BaseModel]] = Body(None),
        features: Optional[List[Dict[str, Any]]] = Body(None),
    ):
        if inputs is None and features is None:
            raise HTTPException(status_code=500, detail="inputs or features must be supplied.")

        workflow_inputs: Dict[str, Any] = {}
        if model._dataset.reader_return_type is not None:
            # convert raw features to whatever the output type of the reader is.
            (_, feature_type), *_ = model._dataset.reader_return_type.items()
            features = feature_type(features)
        workflow_inputs.update(inputs if inputs else {"features": features})

        return model.predict(**workflow_inputs)
