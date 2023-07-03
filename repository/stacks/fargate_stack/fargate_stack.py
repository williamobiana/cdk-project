import os
import aws_cdk as core

from aws_cdk import (
    Stack,
    aws_ec2 as _ec2, 
    aws_ecs as _ecs,
    aws_s3 as _s3,
    aws_iam as _iam,
    aws_s3_notifications as _s3n,
    aws_ecs_patterns as _ecs_patterns,
    aws_neptune as _neptune,
    aws_sagemaker as _sagemaker,
    aws_elasticloadbalancingv2 as elbv2,
    aws_elasticloadbalancingv2_actions as elbv2_actions,
    aws_certificatemanager as _certificatemanager,
    aws_cognito as _cognito
)

from repository.util import util as _util

from constructs import Construct

class FargateStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, network_stack, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        env_prefix = self.node.try_get_context("properties").get("env_prefix")
        self.component_prefix = f"project-{env_prefix}"

        ########## FARGATE ##########
        _cluster_name = f"{self.component_prefix}-ecs-cluster"
        self.fargateCluster = _ecs.Cluster(
            self, 
            _cluster_name, 
            vpc=network_stack.vpc,
            cluster_name=_cluster_name)

        certificate = "arn:aws:acm:eu-west-1:123456789012:certificate/6f482442-968c-4211-bf35-a159e8c784df"

        domain_cert = _certificatemanager.Certificate.from_certificate_arn(self, f"{self.component_prefix}-domainCert", certificate)

        taskExecutionRole = _iam.Role.from_role_arn(self, 'ecsExecPolicy', role_arn='arn:aws:iam::123456789012:role/ecsTaskExecutionRole')
        
        _graph_db_sg_name = f"{self.component_prefix}-neptune-clientsg"
        sg_use_graph_db = _ec2.SecurityGroup(
            self, 
            _graph_db_sg_name,
            vpc=network_stack.vpc,
            allow_all_outbound=True,
            description='security group for Fargate tasks (neptune clients)',
            security_group_name=_graph_db_sg_name
        )

        _fargate_service_name = f"{self.component_prefix}-fargate-service"
        _alb_name = f"{self.component_prefix}-ec2-fargatealb"
        self.load_balanced_bft_fargate_service = _ecs_patterns.ApplicationLoadBalancedFargateService(
            self, 
            _fargate_service_name,
            service_name=_fargate_service_name,
            cluster=self.fargateCluster,
            security_groups=[sg_use_graph_db],
            circuit_breaker=_ecs.DeploymentCircuitBreaker(rollback=True),
            cpu=512,                    # Default is 256
            desired_count=2,            # Default is 1
            task_image_options=_ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                #image=_ecs.ContainerImage.from_registry("public.ecr.aws/neptune/graph-explorer:latest"),
                image=_ecs.ContainerImage.from_registry("123456789012.dkr.ecr.eu-west-1.amazonaws.com/ecr-repo"),
                enable_logging=True,
                command=[],
                environment={
                    "HOST":"localhost"
                    },
                execution_role=taskExecutionRole),
            memory_limit_mib=2048,      # Default is 512
            public_load_balancer=True,
            assign_public_ip=True,

            redirect_http=True,
            protocol=elbv2.ApplicationProtocol.HTTPS,
            certificate=domain_cert,
            load_balancer_name=_alb_name,
            task_subnets=_ec2.SubnetSelection(
                subnet_type=_ec2.SubnetType.PUBLIC
            )
        )

        #configure health checks
        self.load_balanced_bft_fargate_service.target_group.configure_health_check(
            path="/explorer",
            healthy_http_codes="200-399"
        )

        #configure sticky sessions
        self.load_balanced_bft_fargate_service.target_group.enable_cookie_stickiness(
            duration=core.Duration.minutes(10),
            cookie_name="GRAPH_EXPLORER_SESSIONID"
        )

        #scaling settings
        scalable_target = self.load_balanced_bft_fargate_service.service.auto_scale_task_count(
            min_capacity=1,
            max_capacity=5
        )

        scalable_target.scale_on_cpu_utilization("CpuScaling",
            target_utilization_percent=80
        )

        scalable_target.scale_on_memory_utilization("MemoryScaling",
            target_utilization_percent=80
        )

        self.fargateServiceSecGroup = sg_use_graph_db

        #create a user pool
        _cognito_userpool_name = f"{self.component_prefix}-azure-userpool"
        cognito_userpool = self.create_cognito_userpool(
            _cognito_userpool_name, 
            network_stack.vpc 
        )
        userpool = cognito_userpool[0]
        userpool_client = cognito_userpool[1]
        userpool_domain = cognito_userpool[2]

        #add authentication actions to listener
        self.load_balanced_bft_fargate_service.listener.add_action(
            "authenticate-action",
            action=elbv2_actions.AuthenticateCognitoAction(
                user_pool=userpool,
                user_pool_client=userpool_client,
                user_pool_domain=userpool_domain,

                next=elbv2.ListenerAction.forward([self.load_balanced_bft_fargate_service.target_group])
            )
        )

    def create_cognito_userpool(self, _userpool_name, _vpc):
        #userpool
        cognito_userpool = _cognito.UserPool(
            self, 
            "user-pool",
            email=_cognito.UserPoolEmail.with_cognito("no-reply@verificationemail.com"),
            user_pool_name=_userpool_name,
            removal_policy=core.RemovalPolicy.DESTROY                                    
        )
        
        _cognito.SignInAliases(username=True)
        
        #userpool domain
        cognito_userpool_domain = cognito_userpool.add_domain("cognito-domain",
            cognito_domain=_cognito.CognitoDomainOptions(
                #domain_prefix=_userpool_name
                domain_prefix="userpoolclientdomain"
            )
        )
        
        #userpool saml Idp
        _saml_idp_name = f"{self.component_prefix}-azure-idp"
        user_pool_identity_provider_saml = _cognito.UserPoolIdentityProviderSaml(
            self, 
            "user-pool-identity-provider-saml",
            metadata=_cognito.UserPoolIdentityProviderSamlMetadata.url("https://login.microsoftonline.com/xxxxxxx/federationmetadata/2007-06/federationmetadata.xml?appid=xxxxxx"),
            user_pool=cognito_userpool,
            name=_saml_idp_name,
            attribute_mapping=_cognito.AttributeMapping(
                email=_cognito.ProviderAttribute.other("emailaddress"),
                given_name=_cognito.ProviderAttribute.other("givenname")
            )
        )

        #userpool client
        _user_pool_client_name = f"{self.component_prefix}-azure-client"
        cognito_userpool_client = cognito_userpool.add_client(
            "user-pool-public-client",
            user_pool_client_name=_user_pool_client_name,
            generate_secret=True,
            o_auth=_cognito.OAuthSettings(
                flows=_cognito.OAuthFlows(
                    authorization_code_grant=True
                ),
                scopes=[_cognito.OAuthScope.OPENID, _cognito.OAuthScope.EMAIL],
                callback_urls=["https://loadbalancer-dns.eu-west-1.elb.amazonaws.com/oauth2/idpresponse"]
            ),
            supported_identity_providers=[_cognito.UserPoolClientIdentityProvider.custom(user_pool_identity_provider_saml.provider_name)], #This is enabled by default
            auth_session_validity=core.Duration.minutes(15),
            access_token_validity=core.Duration.minutes(60),
            id_token_validity=core.Duration.minutes(60),
            refresh_token_validity=core.Duration.days(30),
            enable_token_revocation=True # default
        )
        
        cognito_userpool_client.user_pool_client_id

        return (cognito_userpool, cognito_userpool_client, cognito_userpool_domain)
        
        ########## FARGATE ##########
