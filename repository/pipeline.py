import json

from repository.util import util as _util

from constructs import Construct
from aws_cdk import (
    Stack,
    aws_codecommit as codecommit
)
from aws_cdk.pipelines import (
    CodePipeline,
    CodePipelineSource,
    ShellStep
)
from repository.stages.dev_stage import DevStage

class PipelineStack(Stack):
    
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        properties = self.node.try_get_context("properties")
                
        environment = properties.get("environment")

        print("CREATING pipeline for environment: " + environment)
        
        repository=codecommit.Repository.from_repository_name(self, "CodeCommitRepo", "repository")
                
        pipeline = CodePipeline(self, "Pipeline",
                                pipeline_name='Pipeline',
                                synth=ShellStep("Synth",
                                                input=CodePipelineSource.code_commit(
                                                    repository, environment),
                                                install_commands=[
                                                    "npm install -g aws-cdk",
                                                    "pip install -r requirements.txt"
                                                ],
                                                commands=[
                                                    "cdk synth"
                                                ],
                                                ),
                                                role=None)
        
        #Landing Zone stage
        pipeline.add_stage(DevStage(self,environment))
    