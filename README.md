# kctl
Rancher Kubernetes API compatible with  RKE, RKE2 and maybe others?

---

Documentation is WIP.

---

## Quickstart

```bash
pip install --upgrade kctl
```


## Usage

```python
from lazycls.envs import set_env_from_dict


"""
---
Primary Configuration that takes env variables first.
---

host = envToStr('KCTL_HOST', 'http://localhost')
api_key = envToStr('KCTL_API_KEY')
api_key_prefix = envToStr('KCTL_API_KEY_PREFIX', 'token:')
api_token = envToStr('KCTL_API_TOKEN')
username = envToStr('KCTL_API_USERNAME')
password = envToStr('KCTL_API_PASSWORD')
auth_prefix = envToStr('KTCL_AUTH_PREFIX', 'authorization')

---
Rancher Specific Configuration
---

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

---
Then validates against env variables during initialization, prioritizing env variables.
---

api_version = envToStr('KCTL_API_VERSION', api_version or 'v1')
ssl_verify = envToBool('KCTL_SSL_VERIFY', str(ssl_verify))
strict = envToBool('KCTL_STRICT', str(strict))
cache_time = envToInt('KCTL_CACHE_TIME', cache_time)
cache_dir = to_path(envToStr('KCTL_CACHE_DIR', None) or cache_dir)

rancher_default_cluster = envToStr('KCTL_RANCHER_DEFAULT_CLUSTER', rancher_default_cluster)
rancher_fleet_name = envToStr('KCTL_RANCHER_FLEET_NAME', rancher_fleet_name)

# If both are empty, then it will assume all clusters are enabled.
clusters_enabled = envToList('KCTL_CLUSTERS_ENABLED', clusters_enabled)
clusters_disabled = envToList('KCTL_CLUSTERS_DISABLED', clusters_disabled)

"""

data = {
    'KCTL_HOST': 'https://ranchercluster.com',
    'KCTL_API_TOKEN': 'token-xxxx:yyyyyyyyyyyyyyyyyyyyyyyyyyyy'
}

set_env_from_dict(data, override=True)
from kctl.client import KctlClient

## Rancher Specific
## This will build the object class dynamically
## enabling v1/v3 api methods.
## v3 is typically the management cluster
## v1 is cluster specific

KctlClient.build_rancher_ctx()

## KctlClient is a Class that doesnt require initialization

## Sync Method
cs = KctlClient.v3.list_cluster()

## Async Method
cs = await KctlClient.v3.async_list_cluster()

cs.data[-1].name

"""
local
"""

## Change Cluster Context

KctlClient.set_cluster('staging-cluster')

KctlClient.v1.url
"""
Now the primary api url will be called using the proper k8s path

-> https://ranchercluster.com/k8s/clusters/c-m-xxxxxx

"""

KctlClient.v1.list_apps_deployment()

"""
All v1 methods will now return the specified cluster context

{
    'type': 'collection', 
    'links': {'self': 'https://ranchercluster.com/k8s/clusters/c-m-xxxxxx/v1/apps.deployments/fleet-default'}, 
    'createTypes': {'apps.deployment': 'https://ranchercluster.com/k8s/clusters/c-m-xxxxxx/v1/apps.deployments'}, 
    'actions': {}, 
    'resourceType': 'apps.deployment', 
    'revision': '6671325', 
    'data': []
}
"""

```

---

## Enhancements

This library borrows the dynamic initialization method from the primary [rancher-client](https://github.com/rancher/client-python) python library with several enhancements.

- Async and Sync support via `httpx` / `lazyapi`, which can be initialized from a sync environment.

- All async methods are accessed with `async_` prefix of the same sync methods.

- Inclusion of [kubernetes python client](https://github.com/kubernetes-client/python) which can be called via `KctlClient.api`, allowing setting of credentials once. Although this use case has not been extensively tested. (or rather, at all.)

- Dynamic Access of downstream clusters without requiring reinitialization of the client

- Enables context switching between clusters

- Lazy caching of the api schema in `kctl/kctl/.kctlcache`

- Enables access of v1/v3 api methods within the same client.

- All returned results are objects, allowing dynamic access of object attributes, rather than strictly `dict` based.

- Adds support for `fleet` namespaces to ensure proper url handling

---

## Credits / Libraries Used

- [rancher-client](https://github.com/rancher/client-python): inspired dynamic schema initialization

- [kubernetes](https://github.com/kubernetes-client/python): included to manage credentials

- [lazyapi](https://github.com/trisongz/lazyapi): personal library that is used to create the `httpx` clients.

- [lazycls](https://github.com/trisongz/lazycls): personal library that contains a lot of utility functions that enables this library to be as slim as possible.

