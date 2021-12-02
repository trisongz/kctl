import os
import re
import json
import time
import hashlib
import collections
from lazyapi import ApiClient
from lazycls import classproperty
from .utils import *
from .classes import *
from .config import KctlContextCfg
from kubernetes.client import ApiClient as KubernetesClient

class KctlBaseClient:
    def __init__(self, host: str = "", api_version: str = None, *args, **kwargs):
        self._cfg = KctlContextCfg(host=host, api_version = api_version, *args, **kwargs)
        self.url = self._cfg.url
        self._client = ApiClient(headers = self._cfg.headers, verify = self._cfg.ssl_verify, module_name=f'kctl.{self._cfg.api_version}', default_resp = True)
        self.schema = None
        if self._cfg.is_enabled: self._load_schemas()
    
    def reset_config(self, host: str = None, api_version: str = None, reset_schema: bool = True, *args, **kwargs):
        self._cfg = KctlContextCfg(host=host, api_version = api_version, *args, **kwargs)
        self.url = self._cfg.url
        self._client = ApiClient(headers = self._cfg.headers, verify = self._cfg.ssl_verify, module_name=f'kctl.{self._cfg.api_version}', default_resp = True)
        if reset_schema: self.reload_schema()
    
    def set_cluster(self, cluster_name: str, reset_schema: bool = True):
        """ Sets the Base url property to the cluster"""
        self.url = self._cfg.get_url(cluster_name = cluster_name, set_default= True)
        if reset_schema: self.reload_schema()

    def reload_schema(self):
        self._load_schemas(force=True)
    
    def valid(self):
        return self.url is not None and self.schema is not None

    def object_hook(self, obj):
        if isinstance(obj, list): return [self.object_hook(x) for x in obj]
        if isinstance(obj, dict):
            result = RestObject()
            for k, v in obj.items():
                setattr(result, k, self.object_hook(v))

            for link in ['next', 'prev']:
                try:
                    url = getattr(result.pagination, link)
                    if url is not None: setattr(result, link, lambda url=url: self._get(url))
                except AttributeError: pass

            if hasattr(result, 'type') and isinstance(getattr(result, 'type'), str):
                if hasattr(result, 'links'):
                    for link_name, link in result.links.items():
                        def cb_link(_link=link, **kw): 
                            return self._get(_link, data=kw)
                        if hasattr(result, link_name): setattr(result, link_name + '_link', cb_link)
                        else: setattr(result, link_name, cb_link)


                if hasattr(result, 'actions'):
                    for link_name, link in result.actions.items():
                        def cb_action(_link_name=link_name, _result=result, *args, **kw):
                            return self.action(_result, _link_name, *args, **kw)
                        if hasattr(result, link_name): setattr(result, link_name + '_action', cb_action)
                        else: setattr(result, link_name, cb_action)

            return result
        return obj

    def object_pairs_hook(self, pairs):
        ret = collections.OrderedDict()
        for k, v in pairs:
            ret[k] = v
        return self.object_hook(ret)
    
    def _get(self, url: str, data=None):
        return self._unmarshall(self._get_raw(url, data=data))
    
    async def _async_get(self, url: str, data=None):
        return self._unmarshall(await self._async_get_raw(url, data=data))

    def _error(self, text):
        raise ApiError(self._unmarshall(text))
    
    @timed_url
    def _get_raw(self, url: str, data=None):
        r = self._get_response(url, data)
        return r.text
    
    @timed_url
    async def _async_get_raw(self, url: str, data=None):
        r = await self._async_get_response(url, data)
        return r.text
    
    def _get_response(self, url: str, data=None):
        r = self._client.get(url, params=data, headers=self._cfg.headers)
        if r.status_code < 200 or r.status_code >= 300: self._error(r.text)
        return r
    
    async def _async_get_response(self, url: str, data=None):
        r = await self._client.async_get(url, params=data, headers=self._cfg.headers)
        if r.status_code < 200 or r.status_code >= 300: self._error(r.text)
        return r

    @timed_url
    def _post(self, url: str, data=None):
        r = self._client.post(url, data=self._marshall(data), headers=self._cfg.headers)
        if r.status_code < 200 or r.status_code >= 300: self._error(r.text)
        return self._unmarshall(r.text)
    
    @timed_url
    async def _async_post(self, url: str, data=None):
        r = await self._client.async_post(url, data=self._marshall(data), headers=self._cfg.headers)
        if r.status_code < 200 or r.status_code >= 300: self._error(r.text)
        return self._unmarshall(r.text)

    @timed_url
    def _put(self, url, data=None):
        r = self._client.put(url, data=self._marshall(data), headers=self._cfg.headers)
        if r.status_code < 200 or r.status_code >= 300: self._error(r.text)
        return self._unmarshall(r.text)
    
    @timed_url
    async def _async_put(self, url, data=None):
        r = await self._client.async_put(url, data=self._marshall(data), headers=self._cfg.headers)
        if r.status_code < 200 or r.status_code >= 300: self._error(r.text)
        return self._unmarshall(r.text)

    @timed_url
    def _delete(self, url):
        r = self._client.delete(url, headers=self._cfg.headers)
        if r.status_code < 200 or r.status_code >= 300: self._error(r.text)
        return self._unmarshall(r.text)
    
    @timed_url
    async def _async_delete(self, url):
        r = await self._client.async_delete(url, headers=self._cfg.headers)
        if r.status_code < 200 or r.status_code >= 300: self._error(r.text)
        return self._unmarshall(r.text)
    
    def _unmarshall(self, text):
        if text is None or text == '': return text
        return json.loads(text, object_hook=self.object_hook, object_pairs_hook=self.object_pairs_hook)

    def _marshall(self, obj, indent=None, sort_keys=True):
        if obj is None: return None
        return json.dumps(self._to_dict(obj), indent=indent, sort_keys=sort_keys)

    def _load_schemas(self, force=False):
        if self.schema and not force: return
        schema_text = self._get_cached_schema()
        if force or not schema_text:
            response = self._get_response(self.url)
            schema_url = response.headers.get('X-API-Schemas')
            if schema_url is not None and self.url != schema_url: schema_text = self._get_raw(schema_url)
            else: schema_text = response.text
            self._cache_schema(schema_text)

        obj = self._unmarshall(schema_text)
        schema = Schema(schema_text, obj)

        if len(schema.types) > 0:
            self._bind_methods(schema)
            self.schema = schema    

    #############################################################################
    #                             Base Methods                                  #
    #############################################################################

    def by_id(self, type, id, **kw):
        id = str(id)
        type_name = convert_type_name(type)
        url = self.schema.types[type_name].links.collection
        if url.endswith('/'): url += id
        else: url = '/'.join([url, id])
        try: return self._get(url, self._to_dict(**kw))
        except ApiError as e:
            if e.error.status == 404: return None
            else: raise e
    
    def update_by_id(self, type, id, *args, **kw):
        type_name = convert_type_name(type)
        url = self.schema.types[type_name].links.collection
        url = url + id if url.endswith('/') else '/'.join([url, id])
        return self._put_and_retry(url, *args, **kw)

    def update(self, obj, *args, **kw):
        url = obj.links.self
        return self._put_and_retry(url, *args, **kw)

    def _put_and_retry(self, url, *args, **kw):
        retries = kw.get('retries', 3)
        for i in range(retries):
            try: return self._put(url, data=self._to_dict(*args, **kw))
            except ApiError as e:
                if i == retries-1: raise e
                if e.error.status == 409: time.sleep(.1)
                else: raise e
    
    def _post_and_retry(self, url, *args, **kw):
        retries = kw.get('retries', 3)
        for i in range(retries):
            try: return self._post(url, data=self._to_dict(*args, **kw))
            except ApiError as e:
                if i == retries-1: raise e
                if e.error.status == 409: time.sleep(.1)
                else: raise e
    
    def _validate_list(self, type, **kw):
        if not self._cfg.strict: return
        type_name = convert_type_name(type)
        collection_filters = self.schema.types[type_name].collectionFilters
        for k in kw:
            if hasattr(collection_filters, k): return
            for filter_name, filter_value in collection_filters.items():
                for m in filter_value.modifiers:
                    if k == '_'.join([filter_name, m]): return
            raise ClientApiError(k + ' is not searchable field')

    def list(self, type, **kw):
        type_name = convert_type_name(type)
        if type_name not in self.schema.types: raise ClientApiError(type_name + ' is not a valid type')
        self._validate_list(type_name, **kw)
        collection_url = self.schema.types[type_name].links.collection
        collection_url = self._cfg.validate_fleet_url(collection_url)
        return self._get(collection_url, data=self._to_dict(**kw))
    
    def reload(self, obj):
        return self.by_id(obj.type, obj.id)

    def create(self, type, *args, **kw):
        type_name = convert_type_name(type)
        collection_url = self.schema.types[type_name].links.collection
        collection_url = self._cfg.validate_fleet_url(collection_url)
        return self._post(collection_url, data=self._to_dict(*args, **kw))

    def delete(self, *args):
        for i in args:
            if isinstance(i, RestObject): return self._delete(i.links.self)

    def action(self, obj, action_name, *args, **kw):
        url = getattr(obj.actions, action_name)
        return self._post_and_retry(url, *args, **kw)
    
    #############################################################################
    #                             Async Methods                                 #
    #############################################################################

    async def async_by_id(self, type, id, **kw):
        id = str(id)
        type_name = convert_type_name(type)
        url = self.schema.types[type_name].links.collection

        if url.endswith('/'): url += id
        else: url = '/'.join([url, id])
        try: return await self._async_get(url, self._to_dict(**kw))
        except ApiError as e:
            if e.error.status == 404: return None
            else: raise e
    
    async def async_update_by_id(self, type, id, *args, **kw):
        type_name = convert_type_name(type)
        url = self.schema.types[type_name].links.collection
        url = url + id if url.endswith('/') else '/'.join([url, id])
        return await self._async_put_and_retry(url, *args, **kw)

    async def async_update(self, obj, *args, **kw):
        url = obj.links.self
        return await self._async_put_and_retry(url, *args, **kw)
    
    async def _async_put_and_retry(self, url, *args, **kw):
        retries = kw.get('retries', 3)
        for i in range(retries):
            try: return await self._async_put(url, data=self._to_dict(*args, **kw))
            except ApiError as e:
                if i == retries-1: raise e
                if e.error.status == 409: time.sleep(.1)
                else: raise e
    
    async def _async_post_and_retry(self, url, *args, **kw):
        retries = kw.get('retries', 3)
        for i in range(retries):
            try: return await self._async_post(url, data=self._to_dict(*args, **kw))
            except ApiError as e:
                if i == retries-1: raise e
                if e.error.status == 409: time.sleep(.1)
                else: raise e

    async def async_list(self, type, **kw):
        type_name = convert_type_name(type)
        if type_name not in self.schema.types: raise ClientApiError(type_name + ' is not a valid type')
        self._validate_list(type_name, **kw)
        collection_url = self.schema.types[type_name].links.collection
        collection_url = self._cfg.validate_fleet_url(collection_url)
        return await self._async_get(collection_url, data=self._to_dict(**kw))
    
    async def async_reload(self, obj):
        return await self.async_by_id(obj.type, obj.id)

    async def async_create(self, type, *args, **kw):
        type_name = convert_type_name(type)
        collection_url = self.schema.types[type_name].links.collection
        collection_url = self._cfg.validate_fleet_url(collection_url)
        return await self._async_post(collection_url, data=self._to_dict(*args, **kw))

    async def async_delete(self, *args):
        for i in args:
            if isinstance(i, RestObject): return await self._async_delete(i.links.self)

    async def async_action(self, obj, action_name, *args, **kw):
        url = getattr(obj.actions, action_name)
        return await self._async_post_and_retry(url, *args, **kw)
    
    #############################################################################
    #                             Class Funcs                                  #
    #############################################################################
    
    def _is_list(self, obj):
        if isinstance(obj, list): return True
        if isinstance(obj, RestObject) and 'type' in obj.__dict__ and obj.type == 'collection': return True
        return False

    def _to_value(self, value):
        if isinstance(value, dict):
            ret = {k: self._to_value(v) for k, v in value.items()}
            return ret

        if isinstance(value, list):
            ret = [self._to_value(v) for v in value]
            return ret

        if isinstance(value, RestObject):
            ret = {}
            for k, v in vars(value).items():
                if not isinstance(v, RestObject) and not callable(v):
                    if not k.startswith('_'): ret[k] = self._to_value(v)
                elif isinstance(v, RestObject):
                    if not k.startswith('_'): ret[k] = self._to_dict(v)
            return ret

        return value

    def _to_dict(self, *args, **kw):
        if len(kw) == 0 and len(args) == 1 and self._is_list(args[0]):
            ret = [self._to_dict(i) for i in args[0]]
            return ret

        ret = {}
        for i in args:
            value = self._to_value(i)
            if isinstance(value, dict):
                for k, v in value.items():
                    ret[k] = v

        for k, v in kw.items():
            ret[k] = self._to_value(v)

        return ret

    @staticmethod
    def _type_name_variants(name):
        ret = [name]
        python_name = re.sub(r'([a-z])([A-Z])', r'\1_\2', name)
        if python_name != name: ret.append(python_name.lower())
        return ret

    def _bind_methods(self, schema):
        bindings = [
            ('list', 'collectionMethods', GET_METHOD, self.list),
            ('by_id', 'collectionMethods', GET_METHOD, self.by_id),
            ('update_by_id', 'resourceMethods', PUT_METHOD, self.update_by_id),
            ('create', 'collectionMethods', POST_METHOD, self.create),
        ]
        async_bindings = [
            ('async_list', 'collectionMethods', GET_METHOD, self.async_list),
            ('async_by_id', 'collectionMethods', GET_METHOD, self.async_by_id),
            ('async_update_by_id', 'resourceMethods', PUT_METHOD, self.async_update_by_id),
            ('async_create', 'collectionMethods', POST_METHOD, self.async_create),
        ]

        for type_name, typ in schema.types.items():
            for name_variant in self._type_name_variants(type_name):
                for method_name, type_collection, test_method, m in bindings:
                    # double lambda for lexical binding hack, I'm sure there's
                    # a better way to do this
                    def cb_bind(type_name=type_name, method=m):
                        def _cb(*args, **kw):
                            return method(type_name, *args, **kw)
                        return _cb
                    if test_method in getattr(typ, type_collection, []): setattr(self, '_'.join([method_name, name_variant]), cb_bind())
                for method_name, type_collection, test_method, m in async_bindings:
                    def cb_bind(type_name=type_name, method=m):
                        def _cb(*args, **kw):
                            return method(type_name, *args, **kw)
                        return  _cb
                    if test_method in getattr(typ, type_collection, []): setattr(self, '_'.join([method_name, name_variant]), cb_bind())

    def _get_schema_hash(self):
        h = hashlib.new('sha1')
        h.update(self.url.encode('utf-8'))
        if self._cfg.token is not None: h.update(self._cfg.token.encode('utf-8'))
        return h.hexdigest()

    def _get_cached_schema_file_name(self):
        h = self._get_schema_hash()
        return self._cfg.cache_dir.joinpath('schema-' + h + '.json')

    def _cache_schema(self, text):
        cached_schema = self._get_cached_schema_file_name()
        if not cached_schema: return None
        cached_schema.write_text(text, encoding='utf-8')

    def _get_cached_schema(self):
        cached_schema = self._get_cached_schema_file_name()
        if not cached_schema: return None
        if os.path.exists(cached_schema):
            mod_time = os.path.getmtime(cached_schema)
            if time.time() - mod_time < self._cfg.cache_time: return cached_schema.read_text(encoding='utf-8')
        return None

    def wait_success(self, obj, timeout=-1):
        obj = self.wait_transitioning(obj, timeout)
        if obj.transitioning != 'no': raise ClientApiError(obj.transitioningMessage)
        return obj

    def wait_transitioning(self, obj, timeout=-1, sleep=0.01):
        timeout = _get_timeout(timeout)
        start = time.time()
        obj = self.reload(obj)
        while obj.transitioning == 'yes':
            time.sleep(sleep)
            sleep *= 2
            sleep = min(sleep, 2)
            obj = self.reload(obj)
            delta = time.time() - start
            if delta > timeout:
                msg = 'Timeout waiting for [{}:{}] to be done after {} seconds'
                msg = msg.format(obj.type, obj.id, delta)
                raise Exception(msg)

        return obj


class KctlClient:
    v1: KctlBaseClient = KctlBaseClient(api_version='v1')
    v3: KctlBaseClient = KctlBaseClient(api_version='v3')

    @classmethod
    def build_rancher_ctx(cls):
        cls.v1._cfg.build_rancher_ctx(v1_client=cls.v1, v3_client=cls.v3)
        cls.v3._cfg.build_rancher_ctx(v1_client=cls.v1, v3_client=cls.v3)

    @classmethod
    def reset_context(cls, host: str = None, reset_schema: bool = True, *args, **kwargs):
        cls.v1.reset_config(host = host, api_version = 'v1', reset_schema = reset_schema, *args, **kwargs)
        cls.v3.reset_config(host = host, api_version = 'v3', reset_schema = reset_schema, *args, **kwargs)

    @classmethod
    def set_cluster(cls, cluster_name: str, *args, **kwargs):
        cls.v1.set_cluster(cluster_name = cluster_name, *args, **kwargs)
        #cls.v3.set_cluster(cluster_name = cluster_name, *args, **kwargs)

    @classproperty
    def api(cls) -> KubernetesClient:
        return KubernetesClient(cls.v1._cfg.config)

