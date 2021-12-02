from lazycls.envs import *
from lazycls.types import *
from lazycls import BaseModel, classproperty
from lazycls.funcs import timed_cache
from lazycls.serializers import Base
from kubernetes.client import Configuration
from lazycls.base import set_modulename
from lazycls.utils import get_parent_path, to_path, Path
from .logz import get_logger


DefaultHeaders = {
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}

DefaultCacheDir = get_parent_path(__file__).joinpath('.kctlcache')
logger = get_logger()

set_modulename('kctl')

# This is the base KctlCfg class that you can access natively without requiring initialization.
# To manage multiple contexts, use the class below.

class KctlCfg:
    host = envToStr('KCTL_HOST', 'http://localhost')
    api_key = envToStr('KCTL_API_KEY')
    api_key_prefix = envToStr('KCTL_API_KEY_PREFIX', 'token:')
    api_token = envToStr('KCTL_API_TOKEN')
    username = envToStr('KCTL_API_USERNAME')
    password = envToStr('KCTL_API_PASSWORD')
    auth_prefix = envToStr('KTCL_AUTH_PREFIX', 'authorization')

    @classmethod
    @timed_cache(60)
    def get_headers(cls, username: str = None, password: str = None, api_key: str = None, api_token: str = None, auth_prefix: str = None, api_key_prefix: str = None):
        """ Logic Sequence:
            - username and password if provided
            - fallback to token if provided
            - else default headers
        """
        _headers = DefaultHeaders
        username = username or cls.username
        password = password or cls.password
        api_key = api_key or cls.api_key
        api_token = api_token or cls.api_token
        auth_prefix = auth_prefix or cls.auth_prefix
        api_key_prefix = api_key_prefix or cls.api_key_prefix
        if username and password: _headers[auth_prefix] = f'Basic {Base.b64_encode(username + ":" + password)}'
        elif api_token: _headers[auth_prefix] = f'Bearer {api_token}'
        elif api_key: _headers[auth_prefix] = f'{api_key_prefix}{api_key}'
        return _headers
    
    @classmethod
    @timed_cache(60)
    def get_config(cls, host: str = None, username: str = None, password: str = None, api_key: str = None, api_token: str = None, auth_prefix: str = None, api_key_prefix: str = None):
        """ Native Kubernetes Python Configuration
            Because of how oddly the configuration is needed to be set, this is a helper method
            to make sure its properly set up.
        """
        host = host or cls.host
        username = username or cls.username
        password = password or cls.password
        api_key = api_key or cls.api_key
        api_token = api_token or cls.api_token
        auth_prefix = auth_prefix or cls.auth_prefix
        api_key_prefix = api_key_prefix or cls.api_key_prefix
        cfg = Configuration(host=host)
        if username and password: 
            cfg.api_key_prefix[auth_prefix] =  'basic'
            cfg.api_key[auth_prefix] = Base.b64_encode(username + ":" + password)
        elif cls.api_token:
            cfg.api_key_prefix[auth_prefix] = 'bearer'
            cfg.api_key[auth_prefix] = api_token
        elif cls.api_key:
            cfg.api_key_prefix[auth_prefix] = api_key_prefix
            cfg.api_key[auth_prefix] = api_key
        return cfg

    @classproperty
    def headers(cls): return cls.get_headers()

    @classproperty
    def config(cls): return cls.get_config()
        

class RancherCtx(BaseModel):
    host: str
    cluster_name: str
    cluster_id: str
    registration_token: str 

    @property
    def cluster_url(self):
        # https://localhost/k8s/clusters/c-m-xxxx
        if self.cluster_name == 'local': return self.host
        return f'{self.host}/k8s/clusters/{self.cluster_id}'


class KctlContextCfg:
    def __init__(self,
        host: str = KctlCfg.host,
        api_version: str = 'v1',
        api_token: str = KctlCfg.api_token,
        ssl_verify: bool = True,
        strict: bool = False,
        cache_time: int = 86400,
        cache_dir: Union[Path, str] = DefaultCacheDir,
        rancher_default_cluster: str = None,
        rancher_fleet_name: str = 'fleet-default',
        clusters_enabled: List[str] = [],
        clusters_disabled: List[str] = []
        ):
        self.host = host or KctlCfg.host
        self.token = api_token or KctlCfg.api_token
        self.api_version = envToStr('KCTL_API_VERSION', api_version or 'v1')
        self.ssl_verify = envToBool('KCTL_SSL_VERIFY', str(ssl_verify))
        self.strict = envToBool('KCTL_STRICT', str(strict))
        self.cache_time = envToInt('KCTL_CACHE_TIME', cache_time)
        self.cache_dir = to_path(envToStr('KCTL_CACHE_DIR', None) or cache_dir)
        self.cache_dir.mkdir(parents = True, exist_ok = True)

        self.rancher_default_cluster = envToStr('KCTL_RANCHER_DEFAULT_CLUSTER', rancher_default_cluster)
        self.rancher_fleet_name = envToStr('KCTL_RANCHER_FLEET_NAME', rancher_fleet_name)
        # If both are empty, then it will assume all clusters are enabled.
        self.clusters_enabled = envToList('KCTL_CLUSTERS_ENABLED', clusters_enabled)
        self.clusters_disabled = envToList('KCTL_CLUSTERS_DISABLED', clusters_disabled)
        self.rancher_ctxs: Dict[str, RancherCtx] = {}
    
    def build_rancher_ctx(self, v1_client, v3_client):
        """After rancher client initialization, will populate the cluster-ids from calling the api"""
        clusters = v3_client.list_cluster()
        registration_tokens = v1_client.list_management_cattle_io_clusterregistrationtoken()
        all_enabled = not self.clusters_disabled and not self.clusters_enabled
        for cluster in clusters.data:
            if not all_enabled and (cluster.name in self.clusters_disabled or (self.clusters_enabled and cluster.name not in self.clusters_enabled)): continue
            if not self.rancher_default_cluster: self.rancher_default_cluster = cluster.name
            token = [t.status.token for t in registration_tokens.data if cluster.id in t.id]
            token = token[0] if token else ''
            self.rancher_ctxs[cluster.name] = RancherCtx(
                host = self.host,
                cluster_name = cluster.name,
                cluster_id = cluster.id,
                registration_token = token
            )
    
    def get_kctx(self, cluster_name: str = None, set_default: bool = False):
        if not cluster_name and not self.rancher_ctxs and not self.rancher_default_cluster: return None
        if not self.rancher_ctxs.get(cluster_name) and self.rancher_default_cluster:
            logger.error(f'Cannot retrieve ctx: {cluster_name}. Building Default: {self.rancher_default_cluster}')
            cluster_name = self.rancher_default_cluster        
        ctx = self.rancher_ctxs.get(cluster_name)
        if not ctx: 
            logger.error(f'No Context for {ctx} was found.')
            return None
        if ctx and set_default: self.rancher_default_cluster = ctx.cluster_name
        return ctx

    @timed_cache(60)
    def get_config(self, cluster_name: str = None):
        """ Native Kubernetes Python Configuration
            Because of how oddly the configuration is needed to be set, this is a helper method
            to make sure its properly set up.
        """
        if not self.rancher_ctxs and not self.rancher_default_cluster: return KctlCfg.config
        ctx = self.get_kctx(cluster_name)
        if not ctx: return KctlCfg.get_config(host = self.host, api_token = self.token)
        return KctlCfg.get_config(host = ctx.cluster_url, api_token = self.token)
    
    def get_url(self, cluster_name: str = None, set_default: bool = False):
        if not self.rancher_ctxs and not self.rancher_default_cluster: url = self.host
        else:
            ctx = self.get_kctx(cluster_name, set_default = set_default)
            url = ctx.cluster_url or self.host
        if not url.endswith(self.api_version): url += f'/{self.api_version}'
        return url
    
    @property
    def headers(self): return KctlCfg.get_headers(api_token = self.token)
    
    @property
    def config(self): return self.get_config()
    
    
    @property
    def url(self): return self.get_url()

    @property
    def is_enabled(self):
        return bool(self.token and self.host)

    def validate_fleet_url(self, url: str):
        if 'management.cattle.io.clusterregistrationtokens' in url: return url
        if self.api_version == 'v1' and self.rancher_fleet_name not in url: url += f'/{self.rancher_fleet_name}'
        return url




    
