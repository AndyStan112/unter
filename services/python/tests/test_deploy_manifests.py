"""Keeps deploy/app consistent with the generator, the synced Secret and the network policy.

A manifest that references a Secret key sync-secrets.py doesn't copy leaves the pod unable to start
(CreateContainerConfigError); a missing network-policy path fails only at runtime. Both are cheap to
catch here.
"""
import ast
import shutil
import subprocess
import sys
from pathlib import Path
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / 'deploy' / 'app'


def docs():
    for path in sorted(APP.glob('*.yaml')):
        for doc in yaml.safe_load_all(path.read_text()):
            if doc:
                yield path.name, doc


def synced_keys():
    """The `keys` (required) and `optional` lists of scripts/sync-secrets.py, read without running it."""
    found = {}
    for node in ast.walk(ast.parse((ROOT / 'scripts' / 'sync-secrets.py').read_text())):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.List):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('keys', 'optional'):
                    found[target.id] = {element.value for element in node.value.elts}
    return found['keys'], found.get('optional', set())


def containers():
    for name, doc in docs():
        if doc['kind'] in ('Deployment', 'StatefulSet'):
            for container in doc['spec']['template']['spec']['containers']:
                yield doc['metadata']['name'], container


def test_manifests_match_the_generator(tmp_path):
    (tmp_path / 'scripts').mkdir()
    shutil.copy(ROOT / 'scripts' / 'generate-manifests.py', tmp_path / 'scripts')
    shutil.copy(ROOT / 'scripts' / 'init-db.sh', tmp_path / 'scripts')
    (tmp_path / 'deploy' / 'app').mkdir(parents=True)
    subprocess.run([sys.executable, str(tmp_path / 'scripts' / 'generate-manifests.py')], check=True, capture_output=True)
    generated = {p.name: p.read_text() for p in (tmp_path / 'deploy' / 'app').glob('*.yaml')}
    committed = {name: (APP / name).read_text() for name in generated}
    stale = [name for name in generated if generated[name] != committed[name]]
    assert not stale, f'regenerate with scripts/generate-manifests.py: {stale}'


def test_kustomization_lists_every_manifest():
    resources = set(yaml.safe_load((APP / 'kustomization.yaml').read_text())['resources'])
    files = {p.name for p in APP.glob('*.yaml')} - {'kustomization.yaml'}
    assert resources == files


def test_every_secret_reference_is_synced():
    required, optional = synced_keys()
    for app, container in containers():
        for variable in container.get('env', []):
            ref = variable.get('valueFrom', {}).get('secretKeyRef')
            if not ref:
                continue
            assert ref['name'] == 'unter-secrets'
            if ref.get('optional'):
                assert ref['key'] in optional | required, f'{app}: optional {ref["key"]} is never synced'
            else:
                assert ref['key'] in required, f'{app}: {ref["key"]} is not a required key in sync-secrets.py'


def egress():
    allowed = {}
    for _, doc in docs():
        if doc['kind'] != 'NetworkPolicy' or 'Egress' not in doc['spec'].get('policyTypes', []):
            continue
        app = doc['spec']['podSelector'].get('matchLabels', {}).get('app')
        for rule in doc['spec'].get('egress', []):
            for peer in rule.get('to', []):
                target = peer.get('podSelector', {}).get('matchLabels', {}).get('app')
                if app and target:
                    allowed.setdefault(app, set()).update((target, p['port']) for p in rule['ports'])
    return allowed


def ingress():
    allowed = {}
    for _, doc in docs():
        if doc['kind'] != 'NetworkPolicy' or 'Ingress' not in doc['spec'].get('policyTypes', []):
            continue
        app = doc['spec']['podSelector'].get('matchLabels', {}).get('app')
        for rule in doc['spec'].get('ingress', []):
            for peer in rule.get('from', []):
                source = peer.get('podSelector', {}).get('matchLabels', {}).get('app')
                if app and source:
                    allowed.setdefault(app, set()).update((source, p['port']) for p in rule['ports'])
    return allowed


NEEDS = [  # (environment variable, service it implies, port)
    ('RABBITMQ_PASSWORD', 'rabbitmq', 5672), ('DB_PASSWORD', 'postgres', 5432)]


@pytest.mark.parametrize('variable, target, port', NEEDS)
def test_network_policy_allows_what_each_pod_is_configured_for(variable, target, port):
    out, into = egress(), ingress()
    for app, container in containers():
        if app in ('postgres', 'rabbitmq'):
            continue
        if any(v['name'] == variable for v in container.get('env', [])):
            assert (target, port) in out.get(app, set()), f'{app} has {variable} but no egress to {target}:{port}'
            assert (app, port) in into.get(target, set()), f'{target} has no ingress from {app}:{port}'


def test_mcp_and_mailer_hold_no_service_login():
    for app, container in containers():
        names = {v['name'] for v in container.get('env', [])}
        if app in ('mcp', 'mailer'):
            assert not names & {'SERVICE_USERNAME', 'SERVICE_PASSWORD'}, f'{app} must not hold the SERVICE login'


def test_read_only_and_mailer_pods_cannot_reach_core():
    out = egress()
    for app in ('mcp', 'agent', 'mailer', 'worker'):
        if app != 'mcp':
            assert ('core', 8080) not in out.get(app, set()), f'{app} must not reach core'
    assert out['mcp'] == {('core', 8080)}, 'the MCP server reaches core only'


def test_quota_fits_every_pod():
    quota = next(doc for _, doc in docs() if doc['kind'] == 'ResourceQuota')['spec']['hard']
    def cpu(value):
        value = str(value)
        return float(value[:-1]) / 1000 if value.endswith('m') else float(value)
    def memory(value):
        units = {'Mi': 1, 'Gi': 1024}
        return float(value[:-2]) * units[value[-2:]]
    limits = [c['resources']['limits'] for _, c in containers()]
    requests = [c['resources']['requests'] for _, c in containers()]
    # Recreate rollouts need no surge capacity, but keep room for e.g. a debug pod.
    assert sum(cpu(l['cpu']) for l in limits) <= cpu(quota['limits.cpu']) - 0.5, 'keep half a CPU of headroom'
    assert sum(memory(l['memory']) for l in limits) <= memory(quota['limits.memory'])
    assert sum(cpu(r['cpu']) for r in requests) <= cpu(quota['requests.cpu'])
    assert sum(memory(r['memory']) for r in requests) <= memory(quota['requests.memory'])
