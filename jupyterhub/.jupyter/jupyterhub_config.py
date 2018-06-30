import os
import string
import escapism

# Enable JupyterLab interface if enabled.

c.Spawner.environment = {}

if os.environ.get('JUPYTERHUB_ENABLE_LAB', 'false').lower() in ['true', 'yes', 'y', '1']:
    c.Spawner.environment.update(dict(JUPYTER_ENABLE_LAB='true'))

# Setup location for customised template files.

c.JupyterHub.template_paths = ['/opt/app-root/src/templates']

# Optionally enable user authentication for selected OAuth providers.

from openshift import client, config

with open('/var/run/secrets/kubernetes.io/serviceaccount/namespace') as fp:
    namespace = fp.read().strip()

config.load_incluster_config()
oapi = client.OapiApi()

routes = oapi.list_namespaced_route(namespace)

def extract_hostname(routes, name):
    for route in routes.items:
        if route.metadata.name == name:
            return route.spec.host

jupyterhub_name = os.environ.get('JUPYTERHUB_SERVICE_NAME')
jupyterhub_hostname = extract_hostname(routes, jupyterhub_name)
print('jupyterhub_hostname', jupyterhub_hostname)

keycloak_name = os.environ.get('KEYCLOAK_SERVICE_NAME')
keycloak_hostname = extract_hostname(routes, keycloak_name)
print('keycloak_hostname', keycloak_hostname)

keycloak_realm = os.environ.get('KEYCLOAK_REALM')

keycloak_account_url = 'https://%s/auth/realms/jupyterhub/account' % keycloak_hostname

with open('templates/vars.html', 'w') as fp:
    fp.write('{%% set keycloak_account_url = "%s" %%}' % keycloak_account_url)

os.environ['OAUTH2_TOKEN_URL'] = 'https://%s/auth/realms/%s/protocol/openid-connect/token' % (keycloak_hostname, keycloak_realm)
os.environ['OAUTH2_AUTHORIZE_URL'] = 'https://%s/auth/realms/%s/protocol/openid-connect/auth' % (keycloak_hostname, keycloak_realm)
os.environ['OAUTH2_USERDATA_URL'] = 'https://%s/auth/realms/%s/protocol/openid-connect/userinfo' % (keycloak_hostname, keycloak_realm)

os.environ['OAUTH2_TLS_VERIFY'] = '0'
os.environ['OAUTH_TLS_VERIFY'] = '0'

os.environ['OAUTH2_USERDATA_METHOD'] = 'POST'
os.environ['OAUTH2_USERNAME_KEY'] = 'preferred_username'

from oauthenticator.generic import GenericOAuthenticator
c.JupyterHub.authenticator_class = GenericOAuthenticator

c.OAuthenticator.login_service = "KeyCloak"

c.OAuthenticator.oauth_callback_url = 'https://%s/hub/oauth_callback' % jupyterhub_hostname

c.OAuthenticator.client_id = os.environ.get('OAUTH_CLIENT_ID')
c.OAuthenticator.client_secret = os.environ.get('OAUTH_CLIENT_SECRET')

c.OAuthenticator.tls_verify = False

# Populate admin users and use white list from config maps.

if os.path.exists('/opt/app-root/configs/admin_users.txt'):
    with open('/opt/app-root/configs/admin_users.txt') as fp:
        content = fp.read().strip()
        if content:
            c.Authenticator.admin_users = set(content.split())

if os.path.exists('/opt/app-root/configs/user_whitelist.txt'):
    with open('/opt/app-root/configs/user_whitelist.txt') as fp:
        content = fp.read().strip()
        if content:
            c.Authenticator.whitelist = set(content.split())

# Provide persistent storage for users notebooks.

c.KubeSpawner.user_storage_pvc_ensure = True

c.KubeSpawner.pvc_name_template = '%s-nb-{username}' % c.KubeSpawner.hub_connect_ip
c.KubeSpawner.user_storage_capacity = '1Gi'

c.KubeSpawner.volumes = [
    {
        'name': 'data',
        'persistentVolumeClaim': {
            'claimName': c.KubeSpawner.pvc_name_template
        }
    }
]

c.KubeSpawner.volume_mounts = [
    {
        'name': 'data',
        'mountPath': '/opt/app-root/src'
    }
]

c.Spawner.environment.update(dict(
    JUPYTER_MASTER_FILES='/opt/app-root/master',
    JUPYTER_WORKSPACE_NAME='workspace'))

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
