#!/usr/bin/env python3
from aws_cdk import (
    App,
    Environment
)

from repository.pipeline import PipelineStack

app = App()

environment = Environment(
    account=app.node.try_get_context("properties").get("account_id"),
    region=app.node.try_get_context("properties").get("region_id")
    ) 

PipelineStack(app, 'PipelineStack', env=environment)

app.synth()
