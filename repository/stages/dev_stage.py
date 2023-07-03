from repository.util import util as _util

import aws_cdk as cdk
from constructs import Construct

from repository.stacks.reception_modeling_zone_stack.reception_modeling_zone_stack import ReceptionAndModelingZoneStack
from repository.stacks.neptune_stack.neptune_stack import NeptuneStack
from repository.stacks.comformed_zone_stack.comformed_zone_stack import ComformedZoneStack
from repository.stacks.analytics_stack.analytics_stack import AnalyticsStack
from repository.stacks.fargate_stack.fargate_stack import FargateStack
from repository.stacks.network_stack.network_layer_stack import NetworkLayer

class DevStage(cdk.Stage):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        properties = self.node.try_get_context("properties")
                
        account_id = properties.get("account_id")
        region_id = properties.get("region_id")

        print("Deploying BASE NETWORK STACK to: " + account_id + "@" + region_id)
        network_stack = NetworkLayer(self, 'NetworkLayer',
            env=cdk.Environment(account=account_id, region=region_id),
        )

        print("Deploying RECEPTION AND MODELING Zone to: " + account_id + "@" + region_id)
        landing_zone_stack = ReceptionAndModelingZoneStack(self, 'ReceptionAndModelingZoneStack',
            env=cdk.Environment(account=account_id, region=region_id),
        )
      
        print("Deploying CONFORMED Zone to: " + account_id + "@" + region_id)
        comformed_zone_stack = ComformedZoneStack(self, 'ComformedZoneStack',
            env=cdk.Environment(account=account_id, region=region_id),
        )

        print("Deploying FARGATE Zone to: " + account_id + "@" + region_id)
        fargate_stack = FargateStack(self, 'FargateStack',
            network_stack=network_stack,
            env=cdk.Environment(account=account_id, region=region_id),
        )

        print("Deploying NEPTUNE Zone to: " + account_id + "@" + region_id)
        neptune_stack = NeptuneStack(self, 'NeptuneStack',
            network_stack=network_stack,
            fargate_stack=fargate_stack,
            comformed_zone_stack=comformed_zone_stack,
            env=cdk.Environment(account=account_id, region=region_id),
        )

        analytics_stack = AnalyticsStack(self, 'AnalyticsStack',
            env=cdk.Environment(account=account_id, region=region_id),
            conformed_zone=comformed_zone_stack,
            reception_zone_bucket_name=landing_zone_stack._reception_zone_bucket_name
        )

        # Define dependencies
        fargate_stack.add_dependency(network_stack)

        neptune_stack.add_dependency(network_stack)
        neptune_stack.add_dependency(comformed_zone_stack)
        neptune_stack.add_dependency(fargate_stack)


        