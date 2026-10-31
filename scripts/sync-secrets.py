#!/usr/bin/env python3
"""Copy .env credentials into Unter's Kubernetes Secret through SSH stdin only."""
import argparse
import json
import subprocess
from dotenv import dotenv_values
parser=argparse.ArgumentParser()
parser.add_argument('--host',default='andy@ssh.windogs.win')
args=parser.parse_args()
values=dotenv_values('.env')
keys=['ADMIN_USERNAME','ADMIN_PASSWORD','SERVICE_USERNAME','SERVICE_PASSWORD',
      'POSTGRES_PASSWORD','CORE_DB_PASSWORD','AGENT_DB_PASSWORD','ACTIVITY_DB_PASSWORD',
      'RABBITMQ_PASSWORD','OPENAI_API_KEY','OPENAI_MODEL']
missing=[key for key in keys if not values.get(key)]
if missing: raise SystemExit('Missing .env settings: '+', '.join(missing))
ssh=['ssh','-F','/dev/null','-o','BatchMode=yes',args.host]
kubectl='KUBECONFIG=/home/andy/.kube/cube-studio.yaml /usr/local/bin/kubectl'
namespace={'apiVersion':'v1','kind':'Namespace','metadata':{'name':'unter','labels':{'app.kubernetes.io/part-of':'unter'}}}
secret={'apiVersion':'v1','kind':'Secret','metadata':{'name':'unter-secrets','namespace':'unter'},
        'type':'Opaque','stringData':{key:values[key] for key in keys}}
# Capture output, including errors, so a validation failure cannot echo secret data.
for resource in (namespace,secret):
    result=subprocess.run(ssh+[kubectl+' apply --server-side --field-manager=unter-bootstrap -f -'],input=json.dumps(resource),text=True,capture_output=True)
    if result.returncode: raise SystemExit('Secret synchronization failed; remote command output suppressed to protect values.')
print('Unter namespace and Secret synchronized from local .env. Values not displayed.')
