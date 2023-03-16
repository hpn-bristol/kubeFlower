import kopf
from kubernetes import client, config
import logging 

config.load_kube_config()
api = client.AppsV1Api()
v1 = client.CoreV1Api()
custom_api = client.CustomObjectsApi()

@kopf.on.create('flwr.dev', 'v1', 'fldeployments')
def create_fldeployment(spec, **kwargs):
    server_spec = spec.get('server', {})
    client_spec = spec.get('client', {})
    
    server_image = server_spec.get('image', 'kubeflower:latest')
    server_image_pull_policy = server_spec.get('imagePullPolicy', 'IfNotPresent')
    server_port = server_spec.get('port', 80)
    server_replicas = server_spec.get('replicas', 1)
    
    client_image = client_spec.get('image', 'kubeflower:latest')
    client_image_pull_policy = client_spec.get('imagePullPolicy', 'IfNotPresent')
    client_port = client_spec.get('port', 30050)
    client_replicas = client_spec.get('replicas', 1)
    client_args = client_spec.get('args', [])
    
    server_deployment_body = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": f"{kwargs['body']['metadata']['name']}-server",
            "namespace": kwargs['body']['metadata']['namespace']
        },
        "spec": {
            "replicas": server_replicas,
            "selector": {
                "matchLabels": {
                    "app": f"{kwargs['body']['metadata']['name']}-server"
                }
            },
            "template": {
                "metadata": {
                    "labels": {
                        "app": f"{kwargs['body']['metadata']['name']}-server"
                    }
                },
                "spec": {
                    "containers": [
                        {
                            "name": "fl-server",
                            "image": server_image,
                            "imagePullPolicy": server_image_pull_policy,
                            "command": ["/bin/sh", "-c"],
                            "args": ["python ./src/server.py"],
                            "ports": [
                                {
                                    "containerPort": server_port
                                }
                            ]
                        }
                    ]
                }
            }
        }
    }

    server_service_body = {
        "apiVersion":"v1",
        "kind":"Service",
        "metadata": {
            "name":f"{kwargs['body']['metadata']['name']}-service-server",
            "namespace": kwargs['body']['metadata']['namespace']
        },
        "spec":{
            "selector": {
                "app": f"{kwargs['body']['metadata']['name']}-server",
            },
            "type": "ClusterIP",
            "ports": [
                {
                    "port": client_port,
                    "targetPort": server_port
                }
            ]
        }
    }
    
    client_deployment_body = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": f"{kwargs['body']['metadata']['name']}-client",
            "namespace": kwargs['body']['metadata']['namespace']
        },
        "spec": {
            "replicas": client_replicas,
            "selector": {
                "matchLabels": {
                    "app": f"{kwargs['body']['metadata']['name']}-client"
                }
            },
            "template": {
                "metadata": {
                    "labels": {
                        "app": f"{kwargs['body']['metadata']['name']}-client"
                    }
                },
                "spec": {
                    "containers": [
                        {
                            "name": "fl-client",
                            "image": client_image,
                            "imagePullPolicy": client_image_pull_policy,
                            "command": ["/bin/sh", "-c"],
                            "args": [f"python ./src/client.py --server {kwargs['body']['metadata']['name']}-service-server --port {client_port}"],
                            "ports": [
                                {
                                    "containerPort": client_port
                                }
                            ]
                        }
                    ]
                }
            }
        }
    }
    flwr_service_server = v1.create_namespaced_service(
        namespace=kwargs['body']['metadata']['namespace'],
        body=server_service_body
    )

    flwr_deployment_server = api.create_namespaced_deployment(
        namespace=kwargs['body']['metadata']['namespace'],
        body=server_deployment_body
    )
    #logging.info(f"FLDeployment created with name '{flwr_deployment_server['metadata']['name']}'")
    flwr_deployment_client = api.create_namespaced_deployment(
        namespace=kwargs['body']['metadata']['namespace'],
        body=client_deployment_body
    )
    #logging.info(f"FLDeployment created with name '{flwr_deployment_client['metadata']['name']}'")
    
@kopf.on.delete('flwr.dev', 'v1', 'fldeployments')    
def delete_fldeployment(body, **kwargs):
    namespace = body['metadata']['namespace']
    server_service_name = f"{body['metadata']['name']}-service-server"
    server_deployment_name = f"{body['metadata']['name']}-server"
    client_deployment_name = f"{body['metadata']['name']}-client"
    
    api.delete_namespaced_deployment(
        name=server_deployment_name,
        namespace=namespace,
        body=client.V1DeleteOptions(),
    )
    
    api.delete_namespaced_deployment(
        name=client_deployment_name,
        namespace=namespace,
        body=client.V1DeleteOptions(),
    )
    v1.delete_namespaced_service(
        name=server_service_name,
        namespace=namespace,
        body=client.V1DeleteOptions()
    )
    custom_api.delete_namespaced_custom_object(
        group="flwr.dev",
        version="v1",
        namespace=namespace,
        plural="fldeployments",
        name=body['metadata']['name'],
        body=client.V1DeleteOptions(),
    )