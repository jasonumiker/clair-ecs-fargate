# Troposphere to create CloudFormation template of Clair Fargate deployment
# By Jason Umiker (jason.umiker@gmail.com)

from troposphere import Parameter, Ref, Template, Output, Join, GetAtt
from troposphere import ecs
from troposphere.logs import LogGroup
from troposphere.rds import DBSubnetGroup, DBInstance
from troposphere.iam import Role, PolicyType
from troposphere.ec2 import SecurityGroup, SecurityGroupRule
from troposphere.elasticloadbalancingv2 import LoadBalancer, TargetGroup, Matcher, Listener, Action

t = Template()
t.add_version('2010-09-09')

# Get the required Parameters

cluster = t.add_parameter(Parameter(
    'Cluster',
    Type='String',
    Description='The ECS Cluster to deploy to.',
))

clair_image = t.add_parameter(Parameter(
    'ClairImage',
    Type='String',
    Default='jasonumiker/clair:latest',
    Description='The Clair container image to deploy.',
))

clair_vpc = t.add_parameter(Parameter(
    'ClairVPC',
    Type='AWS::EC2::VPC::Id',
    Description='A VPC ID for the container.',
))

clair_subnet = t.add_parameter(Parameter(
    'ClairSubnet',
    Type='AWS::EC2::Subnet::Id',
    Description='A VPC subnet ID for the container.',
))

clair_subnet2 = t.add_parameter(Parameter(
    'ClairSubnet2',
    Type='AWS::EC2::Subnet::Id',
    Description='A 2nd VPC subnet ID for the container.',
))

clair_db_password = t.add_parameter(Parameter(
    'ClairDBPassword',
    Type='String',
    NoEcho=True,
    Description='The initial Clair RDS Password.',
))

# Create the Resources

# Create CloudWatch Log Group
clair_loggroup = t.add_resource(LogGroup(
    "ClairLogGroup",
))

# Create Security group that allows traffic into the ALB
alb_security_group = SecurityGroup(
    "ALBSecurityGroup",
    GroupDescription="Clair ALB Security Group",
    VpcId=Ref(clair_vpc),
    SecurityGroupIngress=[
        SecurityGroupRule(
            IpProtocol="tcp",
            FromPort="6060",
            ToPort="6061",
            CidrIp="0.0.0.0/0",
        ),
    ]
)
t.add_resource(alb_security_group)

# Create Security group for the host/ENI/Fargate that allows 6060-6061
clair_host_security_group = SecurityGroup(
    "ClairHostSecurityGroup",
    GroupDescription="Clair ECS Security Group.",
    VpcId=Ref(clair_vpc),
    SecurityGroupIngress=[
        SecurityGroupRule(
            IpProtocol="tcp",
            FromPort="6060",
            ToPort="6061",
            SourceSecurityGroupId=(GetAtt(alb_security_group, 'GroupId'))
        ),
    ]
)
t.add_resource(clair_host_security_group)

# Create the Task Role
TaskRole = t.add_resource(Role(
    "TaskRole",
    AssumeRolePolicyDocument={
        'Statement': [{
            'Effect': 'Allow',
            'Principal': {'Service': ['ecs-tasks.amazonaws.com']},
            'Action': ["sts:AssumeRole"]
        }]},
))

# Create the Task Execution Role
TaskExecutionRole = t.add_resource(Role(
    "TaskExecutionRole",
    AssumeRolePolicyDocument={
        'Statement': [{
            'Effect': 'Allow',
            'Principal': {'Service': ['ecs-tasks.amazonaws.com']},
            'Action': ["sts:AssumeRole"]
        }]},
))

# Create the Fargate Execution Policy (access to ECR and CW Logs)
FargateExecutionPolicy = t.add_resource(PolicyType(
    "FargateExecutionPolicy",
    PolicyName="fargate-execution",
    PolicyDocument={'Version': '2012-10-17',
                    'Statement': [{'Action': ['ecr:GetAuthorizationToken',
                                              'ecr:BatchCheckLayerAvailability',
                                              'ecr:GetDownloadUrlForLayer',
                                              'ecr:BatchGetImage', 'logs:CreateLogStream',
                                              'logs:PutLogEvents'],
                                   'Resource': ['*'],
                                   'Effect': 'Allow'},
                                  ]},
    Roles=[Ref(TaskExecutionRole)],
))

# Add the application ELB
ClairALB = t.add_resource(LoadBalancer(
    "ClairALB",
    Scheme="internal",
    Subnets=[Ref(clair_subnet), Ref(clair_subnet2)],
    SecurityGroups=[Ref(alb_security_group)]
))

ClairTargetGroup = t.add_resource(TargetGroup(
    "ClairTargetGroup",
    HealthCheckIntervalSeconds="30",
    HealthCheckProtocol="HTTP",
    HealthCheckTimeoutSeconds="10",
    HealthyThresholdCount="4",
    HealthCheckPort="6061",
    HealthCheckPath="/health",
    Matcher=Matcher(HttpCode="200"),
    Port="6060",
    Protocol="HTTP",
    UnhealthyThresholdCount="3",
    TargetType="ip",
    VpcId=Ref(clair_vpc)
))

Listener = t.add_resource(Listener(
    "Listener",
    Port="6060",
    Protocol="HTTP",
    LoadBalancerArn=Ref(ClairALB),
    DefaultActions=[Action(
        Type="forward",
        TargetGroupArn=Ref(ClairTargetGroup)
    )]
))

# Create the DB Subnet Group
dbsubnetgroup = t.add_resource(DBSubnetGroup(
    "DBSubnetGroup",
    DBSubnetGroupDescription="Subnets available for the RDS DB Instance",
    SubnetIds=[Ref(clair_subnet), Ref(clair_subnet2)],
))

# Create the DB's Security group which only allows access to members of the Ghost Host SG
dbsecuritygroup = t.add_resource(SecurityGroup(
    "DBSecurityGroup",
    GroupDescription="Security group for RDS DB Instance.",
    VpcId=Ref(clair_vpc),
    SecurityGroupIngress=[
        SecurityGroupRule(
            IpProtocol="tcp",
            FromPort="5432",
            ToPort="5432",
            SourceSecurityGroupId=(GetAtt(clair_host_security_group, 'GroupId'))
        ),
    ]
))

# Create the Postgres RDS
clair_db = t.add_resource(DBInstance(
    "ClairDB",
    DBName='postgres',
    AllocatedStorage='20',
    DBInstanceClass='db.t2.micro',
    Engine='postgres',
    EngineVersion='10.3',
    MasterUsername='postgres',
    MasterUserPassword=Ref(clair_db_password),
    DBSubnetGroupName=Ref(dbsubnetgroup),
    VPCSecurityGroups=[Ref(dbsecuritygroup)],
    MultiAZ='False',
    StorageType='gp2'
))

clair_task_definition = t.add_resource(ecs.TaskDefinition(
    'ClairTaskDefinition',
    RequiresCompatibilities=['FARGATE'],
    Cpu='512',
    Memory='1GB',
    NetworkMode='awsvpc',
    TaskRoleArn=Ref(TaskRole),
    ExecutionRoleArn=Ref(TaskExecutionRole),
    ContainerDefinitions=[
        ecs.ContainerDefinition(
            Name='clair',
            Image=Ref(clair_image),
            Essential=True,
            PortMappings=[ecs.PortMapping(ContainerPort=6060),ecs.PortMapping(ContainerPort=6061)],
            Environment=[
                ecs.Environment(
                    Name='DB_HOST',
                    Value=GetAtt(clair_db, "Endpoint.Address")
                ),
                ecs.Environment(
                    Name='DB_PASSWORD',
                    Value=Ref(clair_db_password),
                ),
            ],
            LogConfiguration=ecs.LogConfiguration(
                LogDriver='awslogs',
                Options={'awslogs-group': Ref(clair_loggroup),
                         'awslogs-region': Ref('AWS::Region'),
                         'awslogs-stream-prefix': 'clair'}
            )
        )
    ]
))

clair_service = t.add_resource(ecs.Service(
    'ClairService',
    Cluster=Ref(cluster),
    DesiredCount=1,
    TaskDefinition=Ref(clair_task_definition),
    LaunchType='FARGATE',
    LoadBalancers=[
        ecs.LoadBalancer(
            ContainerName='clair',
            ContainerPort=6060,
            TargetGroupArn=Ref('ClairTargetGroup')
        )
    ],
    NetworkConfiguration=ecs.NetworkConfiguration(
        AwsvpcConfiguration=ecs.AwsvpcConfiguration(
            Subnets=[Ref(clair_subnet), Ref(clair_subnet2)],
            SecurityGroups=[Ref(clair_host_security_group)],
        )
    ),
    DependsOn='ClairALB'
))

# Create the required Outputs

t.add_output(Output(
    "ClairURL",
    Description="URL of the ALB",
    Value=Join("", ["http://", GetAtt(ClairALB, "DNSName")])
))

print(t.to_json())