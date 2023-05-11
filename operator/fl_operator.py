import kopf
from kubernetes import client, config
import logging 
import traceback

config.load_kube_config()
api = client.AppsV1Api()
v1 = client.CoreV1Api()
custom_api = client.CustomObjectsApi()

@kopf.on.create('flwr.dev', 'v1', 'fldeployments')
def create_fldeployment(spec, **kwargs):
    server_spec = spec.get('server', {})
    client_spec = spec.get('client', {})
    server_image = server_spec.get('image', 'juanmarcelouob/kubeflower:latest')
    server_image_pull_policy = server_spec.get('imagePullPolicy', 'IfNotPresent')
    server_port = server_spec.get('port', 8080)
    server_replicas = server_spec.get('replicas', 1)
    #########POTENTIALLY MAKE THE SERVER TO ORCHESTRATE THE PRIVACY BUDGET- FA TO KEEP TRACK OF THE BUDGET
    client_image = client_spec.get('image', 'juanmarcelouob/kubeflower:latest')
    client_image_pull_policy = client_spec.get('imagePullPolicy', 'Always')
    client_port = client_spec.get('port', 30050)
    client_replicas = client_spec.get('replicas', 1)
    client_args = client_spec.get('args', [])
    client_dataset = client_spec.get('dataset', {})
    client_dataset_path = client_dataset.get('path', './data')
    client_dataset_download = client_dataset.get('download', True)
    client_privacy = client_spec.get('privacy', {})
    if len(client_privacy) == 0:
        print("You haven't add privacy values")
    else:
        client_privacy_budget = client_privacy.get('budget', 1.0)
        client_privacy_rate = client_privacy.get('rate',1.0)
    #Server deployment 
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
                            "args": ["ls; python ./src/server.py"],
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
                            "args": [f"ls; cd src; ls; cd ..; python ./src/client.py --server {kwargs['body']['metadata']['name']}-service-server --port {client_port} --download {client_dataset_download}"],
                            "ports": [
                                {
                                    "containerPort": client_port
                                }
                            ],
                        }
                    ],
                }
            }
        }
    }
    
    #Create Flower service server
    try:
        v1.create_namespaced_service(
            namespace=kwargs['body']['metadata']['namespace'],
            body=server_service_body
        )
    except Exception as e:
        logging.error(f"Error creating {kwargs['body']['metadata']['name']}-service server. Reason: {e}") 
        pass
    
    #Create Flower server
    try:        
        api.create_namespaced_deployment(
            namespace=kwargs['body']['metadata']['namespace'],
            body=server_deployment_body
        )
    except Exception as e:
        logging.error(f"Error creating {kwargs['body']['metadata']['name']}-server. Reason: {e}")
        pass

    #Create PV and PVCs if the user wants to load data from dataset.path. They have to be created before the deployment/pod that is going to consume them
    if not client_dataset_download:
        #Configuring the client descriptor to add the volume claims info. *****STILL MISSING A FOR LOOP TO ITERATE OVER PVCs
        valuesVolumeMounts = [
                                {
                                    "name": "my-volume",
                                    "mountPath": "/app/data/"
                                }
                            ]
        valuesVolumes = [
                        {
                            "name": "my-volume",
                            "persistentVolumeClaim": {
                                "claimName": f"{kwargs['body']['metadata']['name']}-client-pvc"
                            }
                        }
                    ]
        client_deployment_body.get('spec').get('template').get('spec').get('containers')[0]['volumeMounts'] = valuesVolumeMounts
        client_deployment_body.get('spec').get('template').get('spec')['volumes'] = valuesVolumes    
        persisten_volume_body = {
            "apiVersion":"v1",
            "kind":"PersistentVolume",
            "metadata": {
                "name":f"{kwargs['body']['metadata']['name']}-client-pv"
            },
            "spec":{
                "storageClassName" : "manual",
                "capacity":{
                    "storage":"1Gi"
                },
                "accessModes":[
                    "ReadWriteOnce"
                ],
                "hostPath": {
                    "path": client_dataset_path
                }
            }
        }
        persisten_volume_claim_body = {
            "apiVersion":"v1",
            "kind":"PersistentVolumeClaim",
            "metadata": {
                "name":f"{kwargs['body']['metadata']['name']}-client-pvc",
                "namespace": kwargs['body']['metadata']['namespace']
            },
            "spec":{
                "storageClassName" : "manual",
                "resources":{
                    "requests": {
                        "storage":"1Gi"
                        }
                },
                "accessModes":[
                    "ReadWriteOnce"
                ]
            }
        }

        #Create Persistent volume for flower client
        try:
            v1.create_persistent_volume(
                body=persisten_volume_body
            )
        except Exception as e:
            logging.error(f"Error creating persistent volume. Reason: {e}")
            pass

        #Create Persistent volume claim for flower client
        try:
            v1.create_namespaced_persistent_volume_claim(
                namespace=kwargs['body']['metadata']['namespace'],
                body=persisten_volume_claim_body
            )
        except Exception as e:
            logging.error(f"Error creating persistent volume claim. Reason: {e}")
            pass

    #Create Flower client
    try:
        api.create_namespaced_deployment(
            namespace=kwargs['body']['metadata']['namespace'],
            body=client_deployment_body
        )
    except Exception as e:
        logging.error(f"Error creating {kwargs['body']['metadata']['name']}-client. Reason: {e}")
        pass

@kopf.on.delete('flwr.dev', 'v1', 'fldeployments')    
def delete_fldeployment(body, **kwargs):
    namespace = body['metadata']['namespace']
    server_service_name = f"{body['metadata']['name']}-service-server"
    server_deployment_name = f"{body['metadata']['name']}-server"
    client_deployment_name = f"{body['metadata']['name']}-client"
    persisten_volume_name = f"my-pv"
    persisten_volume_claim_name = f"my-pvc"
    try:
        api.delete_namespaced_deployment(
            name=server_deployment_name,
            namespace=namespace,
            body=client.V1DeleteOptions(),
        )
    except Exception as e:
        logging.error(traceback)
        pass
    
    try: 
        api.delete_namespaced_deployment(
            name=client_deployment_name,
            namespace=namespace,
            body=client.V1DeleteOptions(),
        )
    except Exception as e:
        logging.error(traceback)
        pass

    try:
        v1.delete_namespaced_service(
            name=server_service_name,
            namespace=namespace,
            body=client.V1DeleteOptions()
        )
    except Exception as e:
        logging.error(traceback)
        pass

    try:        
        v1.delete_namespaced_persistent_volume_claim(
            name=persisten_volume_claim_name,
            namespace=namespace,
            body=client.V1DeleteOptions()
        )
    except Exception as e:
        logging.error(traceback)
        pass

    try:
        v1.delete_persistent_volume(
            name=persisten_volume_name,
            body=client.V1DeleteOptions()
        )
    except Exception as e:
        logging.error(traceback)
        pass

    try:    
        custom_api.delete_namespaced_custom_object(
            group="flwr.dev",
            version="v1",
            namespace=namespace,
            plural="fldeployments",
            name=body['metadata']['name'],
            body=client.V1DeleteOptions(),
        )
    except Exception as e:
        logging.error(traceback)
        pass
