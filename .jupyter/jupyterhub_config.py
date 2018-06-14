import os
import string
import escapism

if os.environ.get('OAUTH_SERVICE_TYPE') == 'GitHub':
    from oauthenticator.github import GitHubOAuthenticator
    c.JupyterHub.authenticator_class = GitHubOAuthenticator

c.MyOAuthenticator.oauth_callback_url = os.environ.get('OAUTH_CALLBACK_URL' )
c.MyOAuthenticator.client_id = os.environ.get('OAUTH_CLIENT_ID')
c.MyOAuthenticator.client_secret = os.environ.get('OAUTH_CLIENT_SECRET')

c.KubeSpawner.environment = {
    "NOTEBOOK_ARGS": "--NotebookApp.default_url=/tree/workspace"
}

c.KubeSpawner.user_storage_pvc_ensure = True

c.KubeSpawner.pvc_name_template = '%s-notebooks' % c.KubeSpawner.hub_connect_ip

c.KubeSpawner.user_storage_capacity = '1Gi'

c.KubeSpawner.volumes = [
    {
        'name': 'notebooks',
        'persistentVolumeClaim': {
            'claimName': c.KubeSpawner.pvc_name_template
        }
    }
]

volume_mounts = [
    {
        'name': 'notebooks',
        'mountPath': '/opt/app-root/src',
        'subPath': 'notebooks/{username}'
    }
]

init_containers = [
    {
        'name': 'setup-volume',
        'image': os.environ['JUPYTERHUB_NOTEBOOK_IMAGE'],
        'command': [
            'setup-volume.sh',
            '/opt/app-root/src',
            '/mnt/notebooks/{username}/workspace'
        ],
        'resources': {
            'limits': {
                'memory': '256Mi'
            }
        },
        'volumeMounts': [
            {
                'name': 'notebooks',
                'mountPath': '/mnt'
            }
        ]
    }
]

def interpolate_properties(spawner, template):
    safe_chars = set(string.ascii_lowercase + string.digits)
    username = escapism.escape(spawner.user.name, safe=safe_chars,
            escape_char='-').lower()

    return template.format(
        userid=spawner.user.id,
        username=username
        )

def expand_strings(spawner, src):
    if isinstance(src, list):
        return [expand_strings(spawner, i) for i in src]
    elif isinstance(src, dict):
        return {k: expand_strings(spawner, v) for k, v in src.items()}
    elif isinstance(src, str):
        return interpolate_properties(spawner, src)
    else:
        return src

def modify_pod_hook(spawner, pod):
    pod.spec.containers[0].volume_mounts.extend(
            expand_strings(spawner, volume_mounts))
    pod.spec.init_containers.extend(
            expand_strings(spawner, init_containers))
    return pod

c.KubeSpawner.modify_pod_hook = modify_pod_hook
