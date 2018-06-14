import os
import string
import escapism

# Optionally enable user authentication for selected OAuth providers.

if os.environ.get('OAUTH_SERVICE_TYPE') == 'GitHub':
    from oauthenticator.github import GitHubOAuthenticator
    c.JupyterHub.authenticator_class = GitHubOAuthenticator

c.MyOAuthenticator.oauth_callback_url = os.environ.get('OAUTH_CALLBACK_URL' )
c.MyOAuthenticator.client_id = os.environ.get('OAUTH_CLIENT_ID')
c.MyOAuthenticator.client_secret = os.environ.get('OAUTH_CLIENT_SECRET')

# Provide persistent storage for users notebooks. We share one
# persistent volume for all users, mounting just their subdirectory into
# their pod. The persistent volume type needs to be ReadWriteMany so it
# can be mounted on multiple nodes as can't control where pods for a
# user may land. Because it is a shared volume, there are no quota
# restrictions which prevent a specific user filling up the entire
# persistent volume.
#
# As we need to populate the persistent volume with notebooks from the
# image in an init container, and the command needs to vary based on
# the user, we add the volume mount and init container details using
# the modify_pod_hook.

c.KubeSpawner.user_storage_pvc_ensure = True

c.KubeSpawner.pvc_name_template = '%s-notebooks' % c.KubeSpawner.hub_connect_ip

c.KubeSpawner.user_storage_capacity = '1Gi'

c.KubeSpawner.user_storage_access_modes = ['ReadWriteMany']

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

# Startup the notebook in the subdirectory of the users area of the
# persistent volume. This is so that the user can traverse up a
# directory and remove or rename the directory and have it recreated
# with a fresh copf of the notebook the next time the pod is started.

c.KubeSpawner.environment = {
    "NOTEBOOK_ARGS": "--NotebookApp.default_url=/tree/workspace"
}

# Setup culling of idle notebooks if timeout parameter is supplied.

idle_timeout = os.environ.get('JUPYTERHUB_IDLE_TIMEOUT')

if idle_timeout and int(idle_timeout):
    c.JupyterHub.services = [
        {
            'name': 'cull-idle',
            'admin': True,
            'command': ['cull-idle-servers', '--timeout=%s' % idle_timeout],
        }
    ]
