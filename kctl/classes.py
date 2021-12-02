from .static import *
from lazycls.serializers import Json
from lazycls.types import *
from lazycls import create_lazycls, BaseModel
from lazycls.funcs import timed_cache
from .utils import create_clskey, convert_type_name
from types import coroutine

class RestObject(object):
    def __init__(self):
        pass

    def __str__(self):
        return self.__repr__()
    
    def __repr__(self):
        data = {k: v for k, v in self.__dict__.items() if self._is_public(k, v)}
        return repr(data)

    def __getattr__(self, k):
        if self._is_list() and k in LIST_METHODS: return getattr(self.data, k)
        return getattr(self.__dict__, k)
    
    def __setattr__(self, k, v):
        self.__dict__[k] = v

    def __getitem__(self, key):
        return self.__dict__[key]

    def __iter__(self):
        if self._is_list(): return iter(self.data)
        data = {k: v for k, v in self.__dict__.items() if self._is_public(k, v)}
        return iter(data.keys())

    def __len__(self):
        if self._is_list(): return len(self.data)
        data = {k: v for k, v in self.__dict__.items() if self._is_public(k, v)}
        return len(data)

    @staticmethod
    def _is_public(k, v):
        return not callable(v)

    def _is_list(self):
        return 'data' in self.__dict__ and isinstance(self.data, list)

    def data_dict(self):
        return {k: v for k, v in self.__dict__.items() if self._is_public(k, v)}
    
    @property
    def dict(self): return self.data_dict()

    @property
    def keys(self): return self.dict.keys()

    @property
    def values(self): return self.dict.values()
        
    @property
    def json(self): return Json.dumps(self.data_dict(), ensure_ascii=False, indent=2)
    
    @timed_cache(10)
    def as_modelcls(self) -> Type[BaseModel]:
        d = self.data_dict()
        if d.get('type', '') == 'collection':
            if d.get('data'):
                rez = []
                for i in d['data']:
                    if i.get('apiVersion'):
                        clsname = create_clskey(i['apiVersion'])
                        rez.append(create_lazycls(clsname=clsname, data=i))
                d['data'] = rez
            return d
        clsname = create_clskey(d.get('apiVersion'))
        return create_lazycls(clsname=clsname, data=d)




class Schema(object):
    def __init__(self, text, obj = None):
        self.text = text
        self.types = {}
        if obj and type(obj) != coroutine: self._sync_load(obj)

    async def _async_load(self, obj):
        await obj
        for t in obj:
            if t.type != 'schema': continue
            # resource names in v1 API may contain '-' or '.'
            self.types[convert_type_name(t.id)] = t
            t.creatable = False
            try:
                if POST_METHOD in t.collectionMethods: t.creatable = True
            except AttributeError: pass
            t.updatable = False
            try:
                if PUT_METHOD in t.resourceMethods: t.updatable = True
            except AttributeError: pass
            t.deletable = False
            try:
                if DELETE_METHOD in t.resourceMethods: t.deletable = True
            except AttributeError: pass
            t.listable = False
            try:
                if GET_METHOD in t.collectionMethods: t.listable = True
            except AttributeError: pass
            if not hasattr(t, 'collectionFilters'): t.collectionFilters = {}


    def _sync_load(self, obj):
        for t in obj:
            if t.type != 'schema': continue
            # resource names in v1 API may contain '-' or '.'
            self.types[convert_type_name(t.id)] = t
            
            t.creatable = False
            try:
                if POST_METHOD in t.collectionMethods: t.creatable = True
            except AttributeError: pass

            t.updatable = False
            try:
                if PUT_METHOD in t.resourceMethods: t.updatable = True
            except AttributeError: pass

            t.deletable = False
            try:
                if DELETE_METHOD in t.resourceMethods: t.deletable = True
            except AttributeError: pass

            t.listable = False
            try:
                if GET_METHOD in t.collectionMethods: t.listable = True
            except AttributeError: pass

            if not hasattr(t, 'collectionFilters'): t.collectionFilters = {}

    def __str__(self):
        return str(self.text)

    def __repr(self):
        return repr(self.text)


class ApiError(Exception):
    def __init__(self, obj):
        self.error = obj
        try:
            msg = '{} : {}\n\t{}'.format(obj.code, obj.message, obj)
            super(ApiError, self).__init__(self, msg)
        except Exception: super(ApiError, self).__init__(self, 'API Error')


class ClientApiError(Exception):
    pass