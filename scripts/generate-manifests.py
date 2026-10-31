#!/usr/bin/env python3
"""Generate reviewable Kubernetes source templates. Contains no secret values."""
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'deploy/app'

def save(name, docs):
    (OUT/name).write_text(yaml.safe_dump_all(docs,sort_keys=False))
def meta(name): return {'name':name}
def secret(key): return {'valueFrom':{'secretKeyRef':{'name':'unter-secrets','key':key}}}
def env(name, value): return {'name':name,'value':str(value)}
def sec(name,key=None): return {'name':name,**secret(key or name)}
auth=[sec('SERVICE_USERNAME'),sec('SERVICE_PASSWORD')]
def database(name): return [env('DB_HOST','postgres'),env('DB_NAME',name),env('DB_USER',name),sec('DB_PASSWORD',name.upper()+'_DB_PASSWORD')]

save('namespace.yaml',[
 {'apiVersion':'v1','kind':'Namespace','metadata':{'name':'unter','labels':{'app.kubernetes.io/part-of':'unter'}}},
 {'apiVersion':'v1','kind':'ServiceAccount','metadata':meta('unter'),'automountServiceAccountToken':False},
 {'apiVersion':'v1','kind':'ResourceQuota','metadata':meta('unter-budget'),'spec':{'hard':{'requests.cpu':'3','requests.memory':'4Gi','limits.cpu':'8','limits.memory':'6Gi','requests.storage':'8Gi','persistentvolumeclaims':'4','pods':'16'}}},
])
services={
 'core':{'image':'unter-core','port':8080,'env':auth+database('core')+[sec('RABBITMQ_PASSWORD')],'memory':'768Mi','cpu':'100m'},
 'worker':{'module':'worker','env':auth+database('activity')+[sec('RABBITMQ_PASSWORD')],'memory':'512Mi'},
 'mcp':{'module':'mcp_server','env':auth,'memory':'512Mi'},
 'agent':{'module':'agent','env':auth+database('agent')+[sec('OPENAI_API_KEY'),sec('OPENAI_MODEL'),env('AGENT_MODE','live'),env('MAX_DAILY_RUNS','30'),env('AGNO_TELEMETRY','false')],'memory':'768Mi'},
 'gateway':{'module':'gateway','env':auth+[sec('ADMIN_USERNAME'),sec('ADMIN_PASSWORD')],'memory':'256Mi'},
}
for name, spec in services.items():
    port=spec.get('port',8000)
    variables=spec['env']+([env('SERVICE_MODULE',spec['module'])] if 'module' in spec else [])
    labels={'app':name}
    container={'name':name,'image':spec.get('image','unter-python'),'ports':[{'containerPort':port}],
        'env':variables,'securityContext':{'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}},
        'resources':{'requests':{'cpu':spec.get('cpu','25m'),'memory':'128Mi'},'limits':{'cpu':'1','memory':spec['memory']}},
        'readinessProbe':{'httpGet':{'path':'/healthz','port':port},'periodSeconds':5},
        'livenessProbe':{'httpGet':{'path':'/healthz','port':port},'periodSeconds':20,'failureThreshold':6},
        'startupProbe':{'httpGet':{'path':'/healthz','port':port},'periodSeconds':5,'failureThreshold':60}}
    deployment={'apiVersion':'apps/v1','kind':'Deployment','metadata':meta(name),'spec':{'replicas':1,'revisionHistoryLimit':3,'strategy':{'type':'Recreate'},'selector':{'matchLabels':labels},'template':{'metadata':{'labels':labels},'spec':{'serviceAccountName':'unter','automountServiceAccountToken':False,'securityContext':{'runAsNonRoot':True,'runAsUser':10001,'runAsGroup':10001,'seccompProfile':{'type':'RuntimeDefault'}},'containers':[container]}}}}
    svc={'apiVersion':'v1','kind':'Service','metadata':meta(name),'spec':{'selector':labels,'ports':[{'port':port,'targetPort':port}]}}
    if name=='gateway':
        svc['spec'].update(type='NodePort',externalTrafficPolicy='Local')
        svc['spec']['ports'][0]['nodePort']=30574
    save(name+'.yaml',[svc,deployment])

save('db-init.yaml',[{'apiVersion':'v1','kind':'ConfigMap','metadata':meta('db-init'),'data':{'init.sh':(ROOT/'scripts/init-db.sh').read_text()}}])
for name,image,port,variables,mount,size,probe in [
 ('postgres','postgres:17.6-alpine',5432,[env('POSTGRES_USER','unter'),sec('POSTGRES_PASSWORD'),sec('CORE_DB_PASSWORD'),sec('AGENT_DB_PASSWORD'),sec('ACTIVITY_DB_PASSWORD')],'/var/lib/postgresql/data','4Gi',{'exec':{'command':['pg_isready','-U','unter','-d','postgres']}}),
 ('rabbitmq','rabbitmq:4.1.4-alpine',5672,[env('RABBITMQ_DEFAULT_USER','unter'),sec('RABBITMQ_DEFAULT_PASS','RABBITMQ_PASSWORD'),env('RABBITMQ_NODENAME','rabbit@rabbitmq-0')],'/var/lib/rabbitmq','2Gi',{'exec':{'command':['rabbitmq-diagnostics','-q','ping']}}),
]:
    labels={'app':name}
    container={'name':name,'image':image,'ports':[{'containerPort':port}],'env':variables,
      'resources':{'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'cpu':'1','memory':'768Mi'}},
      'volumeMounts':[{'name':'data','mountPath':mount}],
      'readinessProbe':{**probe,'periodSeconds':10,'timeoutSeconds':10},
      'startupProbe':{**probe,'periodSeconds':5,'timeoutSeconds':10,'failureThreshold':60}}
    pod={'serviceAccountName':'unter','automountServiceAccountToken':False,'securityContext':{'seccompProfile':{'type':'RuntimeDefault'}},'containers':[container]}
    if name=='postgres':
        container['env'].append(env('PGDATA',mount+'/pgdata'))
        container['volumeMounts'].append({'name':'init','mountPath':'/docker-entrypoint-initdb.d','readOnly':True})
        pod['volumes']=[{'name':'init','configMap':{'name':'db-init','defaultMode':493}}]
    state={'apiVersion':'apps/v1','kind':'StatefulSet','metadata':meta(name),'spec':{'serviceName':name,'replicas':1,'selector':{'matchLabels':labels},'template':{'metadata':{'labels':labels},'spec':pod},'volumeClaimTemplates':[{'metadata':meta('data'),'spec':{'accessModes':['ReadWriteOnce'],'resources':{'requests':{'storage':size}}}}]}}
    svc={'apiVersion':'v1','kind':'Service','metadata':meta(name),'spec':{'clusterIP':'None','selector':labels,'ports':[{'port':port,'targetPort':port}]}}
    save(name+'.yaml',[svc,state])

policies=[{'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':meta('default-deny'),'spec':{'podSelector':{},'policyTypes':['Ingress','Egress']}},
 {'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':meta('dns'),'spec':{'podSelector':{},'policyTypes':['Egress'],'egress':[{'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'kube-system'}},'podSelector':{'matchLabels':{'k8s-app':'kube-dns'}}}],'ports':[{'protocol':p,'port':53} for p in ['UDP','TCP']]}]}}]
# Explicit source/destination pairs: no cross-project database or service access.
links={'gateway':[('core',8080),('worker',8000),('agent',8000),('mcp',8000)],'agent':[('mcp',8000),('postgres',5432)],'mcp':[('core',8080)],'core':[('postgres',5432),('rabbitmq',5672)],'worker':[('rabbitmq',5672),('postgres',5432)]}
for source,targets in links.items():
    policies.append({'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':meta(source+'-egress'),'spec':{'podSelector':{'matchLabels':{'app':source}},'policyTypes':['Egress'],'egress':[{'to':[{'podSelector':{'matchLabels':{'app':target}}}],'ports':[{'protocol':'TCP','port':port}]} for target,port in targets]}})
for target in ['core','worker','agent','mcp','postgres','rabbitmq']:
    policies.append({'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':meta(target+'-ingress'),'spec':{'podSelector':{'matchLabels':{'app':target}},'policyTypes':['Ingress'],'ingress':[{'from':[{'podSelector':{'matchLabels':{'app':source}}}],'ports':[{'protocol':'TCP','port':port}]} for source,targets in links.items() for dest,port in targets if dest==target]}})
policies.extend([
 {'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':meta('gateway-caddy'),'spec':{'podSelector':{'matchLabels':{'app':'gateway'}},'policyTypes':['Ingress'],'ingress':[{'from':[{'ipBlock':{'cidr':'172.22.0.0/16'}}],'ports':[{'protocol':'TCP','port':8000}]}]}},
 {'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':meta('agent-openai'),'spec':{'podSelector':{'matchLabels':{'app':'agent'}},'policyTypes':['Egress'],'egress':[{'to':[{'ipBlock':{'cidr':'0.0.0.0/0','except':['10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','169.254.0.0/16','127.0.0.0/8']}}],'ports':[{'protocol':'TCP','port':443}]}]}}
])
save('network-policy.yaml',policies)
resources=sorted(p.name for p in OUT.glob('*.yaml') if p.name!='kustomization.yaml')
save('kustomization.yaml',[{'apiVersion':'kustomize.config.k8s.io/v1beta1','kind':'Kustomization','namespace':'unter','resources':resources,'images':[{'name':'unter-'+part,'newName':'ghcr.io/andystan112/unter-'+part,'newTag':'dev'} for part in ['core','python']]}])
print('Generated manifests without secret values.')
