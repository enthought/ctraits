#from ctraits_module import _HasTraits_monitors


#------------------------------------------------------------------------------
# Constants
#------------------------------------------------------------------------------

listener_traits = '__listener_traits__'
class_traits = '__class_traits__'
editor_property = 'editor'
class_prefix = '__prefix__'
trait_added = 'trait_added'

HASTRAITS_INITED = 0x00000001
HASTRAITS_NO_NOTIFY = 0x00000002
HASTRAITS_VETO_NOTIFY = 0x00000004

TRAIT_PROPERTY = 0x00000001
TRAIT_MODIFY_DELEGATE = 0x00000002
TRAIT_OBJECT_IDENTITY = 0x00000004
TRAIT_SETATTR_ORIGINAL_VALUE = 0x00000008
TRAIT_POST_SETATTR_ORIGINAL_VALUE = 0x00000010
TRAIT_VALUE_ALLOWED = 0x00000020
TRAIT_VALUE_PROPERTY = 0x00000040
TRAIT_IS_MAPPED = 0x00000080
TRAIT_NO_VALUE_TEST = 0x00000100


#------------------------------------------------------------------------------
# Constants which are set/initialized by the 'private' module level 
# functions (compat with the ctraits.c api)
#------------------------------------------------------------------------------

adapt = None
TraitValue = None
validate_implements = None
ctrait_type = None
trait_notification_handler = None
Undefined = None
Uninitialized = None
TraitError = None
DelegationError = None
TraitListObject = None
TraitSetObject = None
TraitDictObject = None

# Init

_HasTraits_monitors = []

#------------------------------------------------------------------------------
# CHasTraits type
#------------------------------------------------------------------------------

class CHasTraits(object):
    
    def __new__(cls, *args, **kwargs):
        has_traits_obj = super(CHasTraits, cls).__new__(cls)
        super(CHasTraits, has_traits_obj).__setattr__('_obj_dict', {})      # this can probaly be trashed along with the __dict__ property
        super(CHasTraits, has_traits_obj).__setattr__('_itrait_dict', {})
        super(CHasTraits, has_traits_obj).__setattr__('_ctrait_dict', cls.__dict__[class_traits])
        super(CHasTraits, has_traits_obj).__setattr__('_notifiers_', [])
        super(CHasTraits, has_traits_obj).__setattr__('_flags', 0x00000000)
        return has_traits_obj

    def __init__(self, *args, **kwargs):
        has_trait_listeners = self.__class__.__dict__.get(listener_traits)

        # setup any listeners
        if has_trait_listeners:
            self._init_trait_listeners()

        # set any traits specified in the constructor
        for key, value in kwargs.iteritems():
            setattr(self, key, value)

        # call post constuctor listeners
        if has_trait_listeners:
            self._post_init_trait_listeners()

        # notify any monitors that a new object has been created
        for cls, handler in _HasTraits_monitors:
            if isinstance(self, cls):
                handler(self)
        
        # call the `traits_init` method to finish up initialization
        self.traits_init()
        
        # set the flag to indicate that this trait object has been
        # initialized
        super(CHasTraits, self).__setattr__('_flags', HASTRAITS_INITED)

    def __setattr__(self, name, value):
        # need to change these to 'in' checks similar to __getattribute__
        trait = (self._itrait_dict.get(name) or 
                 self._ctrait_dict.get(name) or
                 get_prefix_trait(self, name, 1))

        if ((trait._flags & TRAIT_VALUE_ALLOWED) and
            isinstance(trait, TraitValue)):
            setattr_value(trait, self, name, value)
        else:
            trait._setattr(trait, trait, self, name, value)

    def __getattribute__(self, name):
        _obj_dict = object.__getattribute__(self, '_obj_dict')
        if name in _obj_dict:
            return _obj_dict[name]

        _itrait_dict = object.__getattribute__(self, '_itrait_dict')
        if name in _itrait_dict:
            trait = _itrait_dict[name]
            return trait._getattr(trait, self, name)

        _ctrait_dict = object.__getattribute__(self, '_ctrait_dict')
        if name in _ctrait_dict:
            trait = _ctrait_dict[name]
            return trait._getattr(trait, self, name)

        try:
            res = object.__getattribute__(self, name)
            return res
        except AttributeError:
            pass

        trait = get_prefix_trait(self, name, 0)
        
        return trait._getattr(trait, self, name)

    def _trait(self, name, instance):
        """ Returns (and optionally creates) a specified instance or class trait:
    
        The legal values for 'instance' are:
             2: Return instance trait (force creation if it does not exist)
             1: Return existing instance trait (do not create) 
             0: Return existing instance or class trait (do not create)
            -1: Return instance trait or force create class trait (i.e. prefix trait) 
            -2: Return the base trait (after all delegation has been resolved)
            
        """
        trait = get_trait(self, name, instance)
        
        if instance >= -1:
            return trait

        # follow the delegation chain until we find a non-delegated trait
        delegate = self
        daname = name
        i = 0
        while True:
            if trait._delegate_attr_name is None:
                return trait

            dct = delegate._obj_dict
            temp_delegate = (dct.get(trait._delegate_name) or 
                             has_traits_getattro(delegate, trait._delegate_name))
            
            delegate = temp_delegate

            if not isinstance(delegate, CHasTraits):
                bad_delegate_error2(self, name)

            daname2 = trait._delegate_attr_name(trait, self, daname)
            daname = daname2

            trait = (delegate._itrait_dict.get(daname) or
                     delegate._ctrait_dict.get(daname) or
                     get_prefix_trait(delegate, daname2, 0) or
                     bad_delegate_error(self, name)) # XXX - should change this to 'in' checks

            if not isinstance(trait, ctrait_type):
                fatal_trait_error()

            i += 1
            if i >= 100:
                delegation_recursion_error2(self, name)

    def _instance_traits(self):
        return self._itrait_dict

    def _notifiers(self, force_create=None):
        return self._notifiers_

    def _trait_change_notify(self, enabled=False):
        if enabled:
            self._flags &= (~HASTRAITS_NO_NOTIFY)
        else:
            self._flags |= HASTRAITS_NO_NOTIFY

    def _trait_veto_notify(self, enabled=False):
        if enabled:
            self._flags |= HASTRAITS_VETO_NOTIFY
        else:
            self._flags &= (~HASTRAITS_VETO_NOTIFY)

    def trait_property_changed(self, name, old_value, new_value=None):
        trait_property_changed(self, name, old_value, new_value)

    def trait_items_event(self, name, event_obj, event_trait):
        if not isinstance(event_trait, ctrait_type): # line 1416 ctraits.c
            bad_trait_value_error()

        if not isinstance(name, basestring):
            invalid_attribute_error()

        trait = self._itrait_dict.get(name) or self._ctrait_dict.get(name)

        if trait is None:
            self.add_trait(name, event_trait)
            trait = self._itrait_dict.get(name) or self._ctrait_dict.get(name)
            if trait is None:
                cant_set_items_error()

        if trait._setattr is setattr_disallow:
            self.add_trait(name, event_trait)
            trait = self._itrait_dict.get(name) or self._ctrait_dict.get(name)
            if trait is None:
                cant_set_items_error()

        trait._setattr(trait, trait, self, name, event_obj)

    def traits_init(self):
        pass

    def traits_inited(self, set_true=False):
        if set_true:
            self._flags |= HASTRAITS_INITED

        if self._flags & HASTRAITS_INITED:
            res = True
        else:
            res = False

        return res
       
    def get_has_traits_dict(self):
        return self._obj_dict

    def set_has_traits_dict(self, value):
        if not isinstance(value, dict):
            dictionary_error()
        self._obj_dict = value

    __dict__ = property(get_has_traits_dict, set_has_traits_dict)


#------------------------------------------------------------------------------
# CTraitMethod type
#------------------------------------------------------------------------------

def create_trait_method(name, func, self, traits, cls):
    tm_obj = object.__new__(CTraitMethod)
    tm_obj.tm_name = name
    tm_obj.tm_func = func
    tm_obj.tm_self = self
    tm_obj.tm_traits = traits
    tm_obj.tm_class = cls
    return tm_obj


class CTraitMethod(object):
    """ traitmethod(function, traits)

    Create a type checked instance method object.

    """
    __slots__ = ['tm_name', 'tm_func', 'tm_self', 'tm_traits', 'tm_class',
                 '__weakref__']

    def __new__(cls, name, func, traits):
        if not callable(func):
            raise TypeError('Second argument must be callable.')
        return create_trait_method(name, func, None, traits, None)

    def __getattribute__(self, name):
        tm_func = object.__getattribute__(self, 'tm_func')
        return getattr(tm_func, name)

    def __get__(self, obj, cls):
        tm_name = object.__getattribute__(self, 'tm_name')
        tm_func = object.__getattribute__(self, 'tm_func')
        tm_traits = object.__getattribute__(self, 'tm_traits')
        tm_self = obj if obj else None
        return create_trait_method(tm_name, tm_func, tm_self, tm_traits, cls)

    def __cmp__(self, other):
        if type(other) is not type(self):
            return -1 
        
        a_self = object.__getattribute__(self, 'tm_self')
        b_self = object.__getattribute__(other, 'tm_self')
        if a_self != b_self:
            if id(a_self) < id(b_self):
                return  -1
            else:
                return 1

        a_func = object.__getattribute__(self, 'tm_func')
        b_func = object.__getattribute__(other, 'tm_func')
        return cmp(a_func, b_func)

    def __repr__(self):
        tm_self = object.__getattribute__(self, 'tm_self')
        tm_func = object.__getattribute__(self, 'tm_func')
        tm_name = object.__getattribute__(self, 'tm_name')
        tm_class = object.__getattribute__(self, 'tm_class')
        
        func_name = tm_func.__name__
        
        if tm_class:
            class_name = tm_class.__name__
        else:
            class_name = '?'

        if tm_self:
            self_name = repr(tm_self)
            result = '<bound method %s.%s of %s>' % (class_name, func_name,  
                                                     self_name)
        else:
            result = '<unbound method %s.%s>' % (class_name, func_name)

        return result

    def __hash__(self):
        tm_self = object.__getattribute__(self, 'tm_self')
        tm_func = object.__getattribute__(self, 'tm_func')
        return hash(tm_self) ^ hash(tm_func)

    def __call__(self, *args, **kwargs):
        # XXX - the C code for this function was horrible.
        # So the layout has departed quite a bit from the 
        # original and the error handling has therefore changed.

        tm_self = object.__getattribute__(self, 'tm_self')
        tm_func = object.__getattribute__(self, 'tm_func')
        tm_name = object.__getattribute__(self, 'tm_name')
        tm_class = object.__getattribute__(self, 'tm_class')
        tm_traits = object.__getattribute__(self, 'tm_traits')

        if tm_self is None:
            if tm_class is None:
                raise TypeError("Unable to determine the class for the method "
                                "'%s'." % tm_func.__name__)
            
            if args:
                tm_self = args[0]
                args = args[1:]
    
            if not isinstance(tm_self, tm_class):
                raise TypeError("Unbound method '%s' must be called with "
                                "an instance of '%s' as the first "
                                "argument. Received '%s' instead."
                                % (tm_func.__name__, tm_class.__name__,
                                   repr(tm_self)))

        ret_trait = tm_traits[0]
        names_and_traits = zip(tm_traits[1::2], tm_traits[2::2])
        
        if len(args) > len(names_and_traits):
            raise ValueError('Too many arguments. %s %s' 
                             % (len(args), len(names_and_traits)))
        
        new_args = [tm_self]
            
        for arg, (trait_name, trait) in zip(args, names_and_traits):
            if trait_name in kwargs:
                raise ValueError('Duplicate arguments `%s`.' % trait_name)

            if trait._validate is None:
                new_args.append(arg)
            else:
                val = trait._validate(trait, tm_self, trait_name, arg)
                new_args.append(val)
        
        # Get the default value for any missing args
        for trait_name, trait in names_and_traits[len(args):]:
            if kwargs:                
                if trait_name in kwargs:
                    val = kwargs[trait_name]
                    if trait._validate is not None:
                        val = trait._validate(trait, tm_self, trait_name, val)
                    new_args.append(val)
                    del kwargs[trait_name]
                    continue
            
            default_value_type = trait._default_value_type
            
            # XXX - perhaps make a dispatch table?
            if default_value_type == 0:
                val = trait._default_value
            elif default_value_type == 1:
                raise ValueError('Missing argument.')
            elif default_value_type == 2:
                val = tm_self
            elif (default_value_type == 3) or (default_value_type == 5):
                val = list(trait._default_value)
            elif (default_value_type == 4) or (default_value_type == 6):
                val = trait._default_value.copy()
            elif default_value_type == 7:
                clbl, cargs, ckwargs = trait._default_value
                val = clbl(*cargs, **ckwargs)
            elif default_value_type == 8:
                val = trait._default_value(tm_self)
                if trait._validate is not None:
                    val = trait._validate(trait, tm_self, trait_name, val)
            else:
                raise ValueError('Bad trait value type %s.' % default_value_type)

            new_args.append(val)

        result = tm_func(*new_args, **kwargs)
        
        if ret_trait._validate is not None:
            result = ret_trait._validate(ret_trait, tm_self, None, result)

        return result


#------------------------------------------------------------------------------
# cTrait type
#------------------------------------------------------------------------------


class cTrait(object):

    base_property = property
    
    def __init__(self, kind):
        """ trait_init """
        
        if not isinstance(kind, int):
            bad_trait_error()

        if kind < 0  or kind > 8:
            bad_trait_error()

        self._getattr = getattr_handlers[kind]
        self._setattr = setattr_handlers[kind]
        
        self._post_setattr = None
        self._validate = None
        self._delegate_attr_name = None
        
        self._py_post_setattr = None
        self._py_validate = None
        self._default_value_type = None
        self._default_value = None
        self._flags = 0x00000000
        self._delegate_name = None
        self._delegate_prefix = None
        self._handler = None
        self._obj_dict = {}
        
        # create an empty list of notifiers
        self._notifiers_ = []
    

    def __getattribute__(self, name):
        _obj_dict = object.__getattribute__(self, '_obj_dict')
        if name in _obj_dict:
            return _obj_dict[name]

        try:
            res = object.__getattribute__(self, name)
            return res
        except AttributeError:
            pass

    def __getstate__(self):
        """ _trait_getstate """
        result = (getattr_handlers.index(self._getattr),
                  setattr_handlers.index(self._setattr),
                  setattr_property_handlers.index(self._post_setattr),
                  get_callable_value(self._py_post_setattr),
                  validate_handlers.index(self._validate),
                  get_callable_value(self._py_validate),
                  self._default_value_type,
                  self._default_value,
                  self._flags,
                  self._delegate_name, 
                  self._delegate_prefix,
                  delegate_attr_name_handlers.index(self._delegate_attr_name),
                  None,
                  self._handler,
                  self._obj_dict)

        return result

    def __setstate__(self, state):
        """ _trait_setstate """
        (getattr_index, setattr_index, post_setattr_index, py_post_setattr,
         validate_index, py_validate, default_value_type, default_value,
         flags, delegate_name, delegate_prefix, delegate_attr_name_index,
         ignore, handler, obj_dict) = state

        self._getattr = getattr_handlers[getattr_index]
        self._setattr = setattr_handlers[setattr_index]
        self._post_setattr = setattr_property_handlers[post_setattr_index]
        self._validate = validate_handlers[validate_index]
        self._delegate_attr_name = delegate_attr_name_handlers[delegate_attr_name_index]
        
        self._py_post_setattr = py_post_setattr
        self._py_validate = py_validate
        self._default_value_type = default_value_type
        self._default_value = default_value
        self._flags = flags
        self._delegate_name = delegate_name
        self._delegate_prefix = delegate_prefix
        self._handler = handler
        self._obj_dict = obj_dict

        temp = self._py_validate
        if isinstance(temp, int):
            self._py_validate = self._handler.validate
        elif isinstance(temp, tuple) and temp and temp[0] == 10:
            temp[2] = self._handler.validate

        if isinstance(self._py_post_setattr, int):
            self._py_post_setattr = self._handler.post_setattr

    def default_value(self, *args):
        """ _trait_default_value """
        if not args:
            if self._default_value is None:
                return (0, None)
            else:
                return (self._default_value_type, self._default_value)

        if (len(args) != 2) or (type(args[0]) != int):
            raise ValueError("If called with arguments, the call should be "
                             "of the form: default_value(value_type, value) ")

        value_type, value = args

        if (value_type < 0) or (value_type > 9):
            raise ValueError("The default value type must be 0 - 9 inclusive, "
                             "but a value of %s was specified" % value_type)

        self._default_value_type = value_type
        self._default_value = value

    def default_value_for(self, obj, name):
        """ _trait_default_value_for """
        if ((self._flags & TRAIT_PROPERTY) != 0) or has_value_for(obj, name):
            res = default_value_for(self, obj, name)
        else:
            res = self._getattr(self, obj, name)

        return res

    def set_validate(self, validate):
        """ _trait_set_validate """
        # XXX - this closure mimics a C goto, get rid of it
        def done():
            self._validate = validate_handlers[kind]
            self._py_validate = validate

        if callable(validate):
            kind = 14
            return done()

        if isinstance(validate, tuple):
            n = len(validate)
            if n > 0:
                kind = int(validate[0])
                if kind == 0:
                    if ((n <= 3) and isinstance(validate[-1], type)) and \
                       ((n == 2) or (validate[1] == None)):
                        return done()
                elif kind == 1:
                    if (n <= 3) and ((n == 2) or (validate[1] is None)):
                        return done()
                elif kind == 2:
                    if (n == 1) or ((n == 2) and (validate[1] is None)):
                        return done()
                elif kind == 3:
                    if n == 4:
                        v1, v2, v3 = validate[1:4]
                        if ((v1 is None) or isinstance(v1, int)) and \
                           ((v2 is None) or isinstance(v2, int)) and \
                           isinstance(v3, int):
                            return done()
                elif kind == 4:
                    if n == 4:
                        v1, v2, v3 = validate[1:4]
                        if ((v1 is None) or isinstance(v1, float)) and \
                           ((v2 is None) or isinstance(v2, float)) and \
                           isinstance(v3, int):
                            return done()
                elif kind == 5:
                    if n == 2:
                        if isinstance(validate[1], tuple):
                            return done()
                elif kind == 6:
                    if n == 2:
                        if isinstance(validate[1], dict):
                            return done()
                elif kind == 7:
                    if n == 2:
                        if isinstance(validate[1], tuple):
                            return done()
                # there is no 8
                elif kind == 9:
                    if n == 2:
                        if isinstance(validate[1], tuple):
                            return done()
                elif kind == 10:
                    if n == 3:
                        if isinstance(validate[1], dict):
                            return done()
                elif kind == 11:
                    if n >= 2:
                        return done()
                elif kind == 12:
                    if n == 2:
                        return done()
                elif kind == 13:
                    if n == 2:
                        if callable(validate[1]):
                            return done()
                # no 14 - 18
                elif kind == 19:
                    if n == 4:
                        if isinstance(validate[2], int) and \
                           isinstance(validate[3], bool):
                            return done()
        
        raise ValueError("The argument must be a tuple or callable")

    def get_validate(self):
        """ _trait_get_validate """
        if self._validate is not None:
            return self._py_validate
        return None

    def validate(self, obj, name, value):
        """ _trait_validate """
        if self._validate is None:
            return value
        return self._validate(self, obj, name, value)

    def delegate(self, delegate_name, delegate_prefix, prefix_type, modify_delegate):
        """ _trait_delegate """
        if modify_delegate:
            self._flags |= TRAIT_MODIFY_DELEGATE
        else:
            self._flags &= (~TRAIT_MODIFY_DELEGATE)

        self._delegate_name = delegate_name
        self._delegate_prefix = delegate_prefix

        if (prefix_type < 0) or (prefix_type > 3):
            prefix_type = 0

        self._delegate_attr_name = delegate_attr_name_handlers[prefix_type]

        
    def rich_comparison(self, rich_comparison_boolean):
        """ _trait_rich_comparison """
        self._flags &= (~(TRAIT_NOT_VALUE_TEST | TRAIT_OBJECT_IDENTITY))
        if not rich_comparison_boolean:
            self._flags |= TRAIT_OBJECT_IDENTITY

    def comparison_mode(self, comparison_mode_enum):
        """ _trait_comparison_mode """
        if not isinstance(comparison_mode_enum, int):
            raise TypeError("Comparison mode must be an integer")

        self._flags &= (~(TRAIT_NO_VALUE_TEST | TRAIT_OBJECT_IDENTITY)) 
        
        if comparison_enum_mode == 0:
            self._flags |= TRAIT_NO_VALUE_TEST
        elif comparison_enum_mode == 1:
            self._flags |= TRAIT_OBJECT_IDENTITY
            
    def value_allowed(self, value_allowed_boolean):
        """ _trait_value_allowed """
        if value_allowed_boolean:
            self._flags |= TRAIT_VALUE_ALLOWED
        else:
            self._flags &= (~TRAIT_VALUE_ALLOWED)

    def value_property(self, value_trait_boolean):
        """ _trait_value_property """
        if value_trait_boolean:
            self._flags |= TRAIT_VALUE_PROPERTY
        else:
            self._flags &= (~TRAIT_VALUE_PROPERTY)

    def setattr_original_value(self, original_value_boolean):
        """ _trait_setattr_original_value """
        if original_value_boolean:
            self._flags |= TRAIT_SETATTR_ORIGINAL_VALUE
        else:
            self._flags &= (~TRAIT_SETATTR_ORIGINAL_VALUE)

    def post_setattr_original_value(self, original_value_boolean):
        """ _trait_post_setattr_original_value """
        if original_value_boolean:
            self._flags |= TRAIT_POST_SETATTR_ORIGINAL_VALUE
        else:
            self._flags &= (~TRAIT_POST_SETATTR_ORIGINAL_VALUE)

    def is_mapped(self, is_mapped_boolean):
        """ _trait_is_mapped """
        if is_mapped_boolean:
            self._flags |= TRAIT_IS_MAPPED
        else:
            self._flags &= (~TRAIT_IS_MAPPED)

    def property(self, *args):
        """ _trait_property """
        if not args:
            return self._delegate_name, self._delegate_prefix, self._py_validate

        getter, get_n, setter, set_n, validate, validate_n = args

        if (not callable(getter) or not callable(setter) or 
            ((validate is not None) and not callable(validate)) or
            (get_n < 0) or (get_n > 3) or (set_n < 0) or (set_n > 3) or
            (validate_n < 0) or (validate_n > 3)):
            raise ValueError("Invalid arguments.")

        self._flags |= TRAIT_PROPERTY
        self._getattr = getattr_property_handlers[get_n]

        if validate is not None:
            self._setattr = setattr_validate_property 
            self._post_setattr = setattr_property_handlers[set_n]
            self._validate = setattr_validate_handlers[validate_n]
        else:
            self._setattr = setattr_property_handlers[set_n]

        self._delegate_name = getter
        self._delegate_prefix = setter
        self._py_validate = validate

    def clone(self, trait):
        """ _trait_clone """
        if not isinstance(trait, ctrait_type):
            raise TypeError('trait must be an instance of %s' % ctrait_type)

        trait_clone(self, trait)

    def cast(self, *args):
        """ _trait_cast """
        
        n_args = len(args)

        if n_args == 1:
            obj = None
            name = None
            value = args[0]
        elif n_args == 2:
            name = None
            obj = args[0]
            value = args[1]
        elif n_args == 3:
            obj = args[0]
            name = args[1]
            value = args[2]
        else:
            raise ValueError("cast takes 1, 2, or 3 arguments %s given." 
                             % n_args)

        if self._validate is None:
            return value

        try:
            res = self._validate(self, obj, name, value)
        except Exception:
            try:
                info = self._handler.info()
            except Exception:
                raise ValueError("Invalid value for trait.")
            
            raise ValueError("Invalid value for trait, the value "
                             "should be %s." % info)

        return res

    def _notifiers(self, force_create):
        """ _trait_notifiers """
        res = self._notifiers_

        if res is None and force_create:
            res = []
            self._notifiers_ = res

        return res

    def _get_trait_dict(self):
        """ get_trait_dict """
        return self._obj_dict

    def _set_trait_dict(self, value):
        """ set_trait_dict """
        if not isinstance(value, dict):
            dictionary_error()
        self._obj_dict = value

    __dict__ = base_property(_get_trait_dict, _set_trait_dict)

    def _get_trait_handler(self):
        """ get_trait_handler """
        return self._handler

    def _set_trait_handler(self, value):
        """ set_trait_handler """
        self._handler = value

    handler = base_property(_get_trait_handler, _set_trait_handler)

    def _get_trait_post_setattr(self):
        """ get_trait_post_setattr """
        return self._py_post_setattr

    def _set_trait_post_setattr(self, value):
        """ set_trait_post_setattr """
        if not callable(value):
            raise ValueError("The assigned value must be callable.")
        self._post_setattr = post_setattr_trait_python
        self._py_post_setattr = value

    post_setattr = base_property(_get_trait_post_setattr, _set_trait_post_setattr)




#------------------------------------------------------------------------------
# Module level private setter functions (purely for api compat with ctraits.c)
#------------------------------------------------------------------------------


def _adapt(adapt_func):
    global adapt
    adapt = adapt_func


def _ctrait(_ctrait_type):
    global ctrait_type
    ctrait_type = _ctrait_type


def _exceptions(trait_error, delegation_error):
    global TraitError, DelegationError
    TraitError = trait_error
    DelegationError = DelegationError


def _list_classes(list_obj, set_obj, dict_obj):
    global TraitListObject, TraitSetObject, TraitDictObject
    TraitListObject = list_obj
    TraitSetObject = set_obj
    TraitDictObject = dict_obj


def _trait_notification_handler():
    global trait_notification_handler
    trait_notification_handler


def _undefined(undefined, uninitialized):
    global Undefined, Uninitialized
    Undefined = undefined
    Uninitialized = uninitialized


def _validate_implements(validate_func):
    global validate_implements
    validate_implements = validate_func


def _value_class(trait_value):
    global TraitValue
    TraitValue = trait_value


#------------------------------------------------------------------------------
# "C-level" ctraits.c functions these are not need for api compatibility
#------------------------------------------------------------------------------

def get_callable_value(value):
    # -1 is a sentinel value
    if callable(value):
        value = -1
    elif isinstance(value, tuple) and value and value[0] == 10:
        temp = (value[0], value[1], -1)
        value = temp
    return value


def get_value(value):
    # This function in C just checked for a null pointer
    # and returned None for that case.
    return value


def has_value_for(obj, name):
    dct = obj._obj_dict
    res = name in dct
    return res

def default_value_for(trait, obj, name):
    dvt = trait._default_value_type

    if dvt == 0 or dvt == 1:
        res = trait._default_value
    elif dvt == 2:
        res = obj
    elif dvt == 3:
        res = list(trait._default_value)
    elif dvt == 4:
        res = trait._default_value.copy()
    elif dvt == 5:
        res = TraitListObject(trait._handler, obj, name, trait._default_value)
    elif dvt == 6:
        res = TraitDictObject(trait._handler, obj, name, trait._default_value)
    elif dvt == 7:
        dv = trait._default_value
        kw = dv[2]
        if kw is None:
            kw = {}
        res = dv[0](*dv[1], **kw)
    elif dvt == 8:
        temp = trait._default_value(obj)
        res = trait._validate(trait, obj, name, temp)
    elif dvt == 9:
        res = TraitSetObject(trait._handler, obj, name, trait._default_value)
    else:
        raise

    return res


def trait_clone(trait, source):
    trait._flags = source._flags
    trait._getattr = source._getattr
    trait._setattr = source._setattr
    trait._post_setattr = source._post_setattr
    trait._py_post_setattr = source._py_post_setattr
    trait._validate = source._validate
    trait._py_validate = source._py_validate
    trait._default_value_type = source._default_value_type
    trait._default_value = source._default_value
    trait._delegate_name = source._delegate_name
    trait._delegate_prefix = source._delegate_prefix
    trait._delegate_attr_name = source._delegate_attr_name
    trait._handler = source._handler


def get_trait(obj, name, instance):
    """Returns (and optionally creates) a specified instance or class trait"""

    # If there already is an instance specific version of the requested trait,
    # then return it
    if name in obj._itrait_dict:
        trait = obj._itrait_dict[name]

    # If only an instance trait can be returned (but not created), then 
    # return None
    elif instance == 1:
        return None
    
    # Otherwise, get the class specific version of the trait (creating a
    # trait class version if necessary)
    if name in obj._ctrait_dict:
        trait = obj._ctrait_dict[name]
    elif instance == 0:
        return None
    else:
        trait = get_prefix_trait(obj, name, False)
    
    # If an instance specific trait is not needed, return the class trait
    if instance <= 0:
        return trait
    
    # Otherwise, create an instance trait dictionary if it does not exist
    # XXX I think we are guaranteed instance dict
    
    # Create a new instance trait and clone the class trait into it
    itrait = cTrait(0)
    trait_clone(itrait, trait)
    itrait._obj_dict = trait._obj_dict
    
    # Copy the class trait's notifier list into the instance trait
    itrait._notifiers_ = trait._notifiers_[:]
    
    # Add the instance trait to the instance's trait dictionary and return
    # the instance trait if successful
    obj._itrait_dict[name] = itrait
    return itrait
    

def get_prefix_trait (obj, name, is_set):
    """Gets the definition of the matching prefix based trait for a specified name:
        - This should always return a trait definition unless a fatal Python error
          occurs.
        - The bulk of the work is delegated to a Python implemented method because
          the implementation is complicated in C and does not need to be executed
          very often relative to other operations.
    """
    
    trait = obj.__prefix_trait__(name, is_set)
    if trait is not None:
        obj._ctrait_dict[name] = trait
        setattr(obj, trait_added, name)
        trait = get_trait(obj, name, False)
    return trait


def has_notifiers(tnotifiers, onotifiers):
    return tnotifiers and onotifiers


def call_notifiers(tnotifiers, onotifiers, obj, name, old_value, new_value):
    """Call all notifiers for a specified trait"""
    new_value_has_traits = isinstance(new_value, CHasTraits)
    args = (obj, name, old_value, new_value)
    
    # Do nothing if the user has explicitly requested no traits notifications
    # to be sent
    if obj._flags & HASTRAITS_NO_NOTIFY:
        return
    
    tnotifiers = tnotifiers[:] # XXX why copy?
    for notifier in tnotifiers:
        if new_value_has_traits and new_value._flags & HASTRAITS_VETO_NOTIFY:
            return
        if trait_notification_handler is not None:
            result = trait_notification_handler(notifier, args)
        else:
            result = notifier(*args)
    
    onotifiers = onotifiers[:]
    for notifier in onotifiers:
        if new_value_has_traits and new_value._flags & HASTRAITS_VETO_NOTIFY:
            return
        if trait_notification_handler is not None:
            result = trait_notification_handler(notifier, args)
        else:
            result = notifier(*args)
    

#-----------------
# getattr handlers
#-----------------

def getattr_trait(trait, obj, name):
    dct = obj._obj_dict
    res = default_value_for(trait, obj, name)
    dct[name] = res
    
    if (trait._post_setattr is not None) and \
       ((trait._flags & TRAIT_IS_MAPPED) == 0):
        trait._post_setattr(trait, obj, name, res)

    tnotifiers = trait._notifiers_
    onotifiers = obj._notifiers_
    if has_notifiers(tnotifiers, onotifiers):
        call_notifiers(tnotifiers, onotifiers, obj, name, Unitialized, res)

    return res


def getattr_python(trait, obj, name):
    return object.__getattribute__(obj, name)


def getattr_event(trait, obj, name):
    raise AttributeError("The '%s' trait of a '%s' instance is an 'event' "
                         "which is write only." 
                         % (name, obj.__class__.__name__))


def getattr_delegate(trait, obj, name):
    dct = obj._obj_dict
    delegate = getattr(obj, trait._delegate_name)

    delegate_attr_name = trait._delegate_attr_name(trait, obj, name)
    return getattr(delegate, delegate_attr_name)


def getattr_disallow(trait, obj, name):
    unknown_attribute_error(obj, name)

def getattr_constant(trait, obj, name):
    return trait._default_value


def getattr_generic(trait, obj, name):
    return object.__getattribute__(obj, name)


def getattr_property0(trait, obj, name):
    return trait._delegate_name()


def getattr_property1(trait, obj, name):
    return trait._delegate_name(obj)


def getattr_property2(trait, obj, name):
    return trait._delegate_name(obj, name)


def getattr_property3(trait, obj, name):
    return trait._delegate_name(obj, name, trait)


#-----------------
# setattr handlers
#-----------------
def setattr_value(*args):
    raise NotImplementedError("implement me!")


def setattr_trait(traito, traitd, obj, name, value):
    dct = obj._obj_dict

    changed = traitd._flags & TRAIT_NO_VALUE_TEST
    
    # XXX - get rid of this closure which replaces a goto
    def notify():
        return

    if value is None:
        if name not in dct:
            return
        
        old_value = dct.pop(name)

        if (obj._flags & HASTRAITS_NO_NOTIFY) == 0:
            tnotifiers = traito._notifiers_
            onotifiers = obj._notifiers_
            if (tnotifiers is not None) or (onotifiers is not None):
                value = traito._getattr(traito, obj, name)
                if not changed:
                    changed = old_value != value
                    if changed and ((traitd._flags & TRAIT_OBJECT_IDENTITY) == 0):
                        changed = cmp(old_value, value)

                if changed:
                    if traitd._post_setattr is not None:
                        traitd._post_setattr(traitd, obj, name, value)

                    if has_notifiers(tnotifiers, onotifiers):
                        call_notifiers(tnotifiers, onotifiers, obj, name, 
                                       old_value, value)

        return

    original_value = value

    if (traitd._validate is not None) and (value != Undefined):
        value = traitd._validate(traitd, obj, name, value)

    if (traitd._flags & TRAIT_SETATTR_ORIGINAL_VALUE):
        new_value = original_value
    else:
        new_value = value

    old_value = None

    tnotifiers = traito._notifiers_
    onotifiers = obj._notifiers_
    do_notifiers = has_notifiers(tnotifiers, onotifiers)

    post_setattr = traitd._post_setattr
    
    if (post_setattr is not None) or do_notifiers:
        if name in dct:
            old_value = dct[name]
        else:
            if traitd is not traito:
                old_value = traito._getattr(traito, obj, name)
            else:
                old_value = default_value_for(traitd, obj, name)

        if not changed:
            changed = (old_value != value)
            if changed and ((traitd._flags & TRAIT_OBJECT_IDENTITY) == 0):
                changed = cmp(old_value, value)

    dct[name] = new_value

    if changed:
        if post_setattr is not None:
            if traitd_flags & TRAIT_POST_SETATTR_ORIGINAL_VALUE:
                sval = original_value
            else:
                sval = new_value
            post_setattr(traitd, obj, name, sval)
        if do_notifiers:
            call_notifiers(tnotifiers, onotifiers, obj, name, old_value,
                           new_value)

    return 


def setattr_python(traito, traitd, obj, name, value):
    # XXX - the C code for this uses a NULL pointer for value
    # to indicate that the attribute should be deleted from the dict.
    # What should we do here?
    dct = obj._obj_dict
    dct[name] = value


def setattr_event(traito, traitd, obj, name, value):
    if traitd._validate is not None:
        value = traitd._validate(traitd, obj, name, value)

    tnotifiers = traito._notifiers_
    onotifiers = obj._notifiers_

    if has_notifiers(tnotifiers, onotifiers):
        call_notifiers(tnotifiers, onotifiers, obj, name, Undefined, value)
        

def setattr_delegate(traito, traitd, obj, name, value):
    daname = name
    delegate = obj
    i = 0
    while True:
        dct = delegate._obj_dict
        if traitd._delegate_name in dct:
            delegate = dct[traitd._delegate_name]
        else:
            delegate = getattr(delegate, traitd._delegate_name)

        if not isinstance(delegate, CHasTraits):
            bad_delegate_error2(obj, name)

        daname = traitd._delegate_attr_name(traitd, obj, daname)
        
        if delegate._itrait_dict is not None:
            if daname in delegate._itrait_dict:
                traitd = delegate._itrait_dict[daname]
            elif daname in delegate._ctrait_dict:
                traitd = delegate._ctrait_dict[daname]
            else:
                traitd = get_prefix_trait(delegate, daname, 1)
                if traitd is None: # XXX - can this ever happen?
                    bad_delegate_error(obj, name)
                    
        if type(traitd) is not ctrait_type:
            fatal_trait_error()

        if traitd._delegate_attr_name is not None:
            if traito._flags & TRAIT_MODIFY_DELEGATE:
                result = traitd._setattr(traitd, traitd, delegate, daname,
                                         value)
            else:
                result = traitd._setattr(traito, traitd, obj, name, value)
                obj._remove_trait_delegate_listener(name, value)

            return result

        i += 1
        if i >= 100:
            delegation_recursion_error(obj, name)


def setattr_disallow(traito, traitd, obj, name, value):
    set_disallow_error(obj, name)

def setattr_readonly(traito, traitd, obj, name, value):
    if value is None: # XXX - what semantics do we want for deletion. It's a NULL PyObject* in C
        delete_readonly_error(obj, name)

    if traitd._default_value != Undefined:
        set_readonly_error(obj, name)

    dct = obj._obj_dict
    if (name not in dct) or (dct[name] == Undefined):
        setattr_python(traito, traitd, obj, name, value)
    else:
        set_readonly_error(obj, name)

def setattr_constant(traito, traitd, obj, name, value):
    raise TraitError("Cannot modify the constant '%s' attribute of a '%s' "
                     "object." % (name, obj.__class__.__name__))


def setattr_generic(traito, traitd, obj, name, value):
    setattr(obj, name, value)


def setattr_property0(traito, traitd, obj, name, value):
    if value is None: # XXX - what semantics do we want for deletion. It's a NULL PyObject* in C
        set_delete_property_error(obj, name)
    traitd._delegate_prefix()


def setattr_property1(traito, traitd, obj, name, value):
    if value is None: # XXX - what semantics do we want for deletion. It's a NULL PyObject* in C
        set_delete_property_error(obj, name)
    traitd._delegate_prefix(value)


def setattr_property2(traito, traitd, obj, name, value):
    if value is None: # XXX - what semantics do we want for deletion. It's a NULL PyObject* in C
        set_delete_property_error(obj, name)
    traitd._delegate_prefix(obj, value)


def setattr_property3(traito, traitd, obj, name, value):
    if value is None: # XXX - what semantics do we want for deletion. It's a NULL PyObject* in C
        set_delete_property_error(obj, name)
    traitd._delegate_prefix(obj, name, value)


def post_setattr_trait_python(trait, obj, name, value):
    trait._py_post_setattr(obj, name, value)

    
def setattr_validate0(trait, obj, name, value):
    """Validates then assigns a value to a specified property trait attribute
    
    This is the 0 argument version."""
    trait._py_validate()


def setattr_validate1(trait, obj, name, value):
    """Validates then assigns a value to a specified property trait attribute
    
    This is the 1 argument version."""
    trait._py_validate(value)


def setattr_validate2(trait, obj, name, value):
    """Validates then assigns a value to a specified property trait attribute
    
    This is the 2 argument version."""
    trait._py_validate(obj, value)


def setattr_validate3(trait, obj, name, value):
    """Validates then assigns a value to a specified property trait attribute
    
    This is the full argument version."""
    trait._py_validate(obj, name, value)


def setattr_validate_property(traito, traitd, obj, name, value):
    """Validates then assigns a value to a specified property trait attribute"""
    validated = traitd._validate(traitd, obj, name, value)
    result = traitd._post_setattr(traito, traitd, obj, name, validated)
    return result


#--------------------
# Validation Handlers
#--------------------

def validate_trait_type(trait, obj, name, value):
    type_info = trait._py_validate
    kind = len(type_info)
    if (kind == 3 and value is None) or (type(value) is type_info[-1]):
        return value
    raise_trait_error(trait, obj, name, value)


def validate_trait_instance(trait, obj, name, value):
    type_info = trait._py_validate
    kind = len(type_info)

    if (kind == 3 and value is None) or isinstance(value, type_info[-1]):
        return value
    raise_trait_error(trait, obj, name, value)


def validate_trait_self_type(trait, obj, name, value):
    type_info = trait._py_validate
    kind = len(type_info)

    if (kind == 2 and value is None) or (value is type(obj)):
        return value
    raise_trait_error(trait, obj, name, value)


def validate_trait_int(trait, obj, name, value):
    type_info = trait._py_validate
    
    if isinstance(value, int):
        int_value = value
        low, high, exclude_mask = type_info[1:4]
        
        if low is not None:
            if exclude_mask & 1:
                if int_value <= low:
                    raise
            else:
                if int_value < low:
                    raise
        
        if high is not None:
            if exclude_mask & 2:
                if int_value >= high:
                    raise
            else:
                if int_value > high:
                    raise

        return value

    raise_trait_error(trait, obj, name, value)


def validate_trait_float(trait, obj, name, value):
    type_info = trait._py_validate

    if not isinstance(value, float):
        if not isinstance(value, int):
            raise_trait_error(trait, obj, name, value)
        value = float(value)

    low, high, exclude_mask = type_info[1:4]

    if low is not None:
        if exclude_mask & 1:
            if value <= low:
                raise_trait_error(trait, obj, name, value)
        else:
            if value < low:
                raise_trait_error(trait, obj, name, value)

    if high is not None:
        if exclude_mask & 2:
            if float_value >= high:
                raise_trait_error(trait, obj, name, value)
        else:
            if float_value > high:
                raise_trait_error(trait, obj, name, value)

    return value


def validate_trait_enum(trait, obj, name, value):
    type_info = trait._py_validate
    if value in type_info[1]:
        return value
    raise_trait_error(trait, obj, name, value)


def validate_trait_map(trait, obj, name, value):
    type_info = trait._py_validate
    if value in type_info[1]:
        return value
    raise_trait_error(trait, obj, name, value)


def validate_trait_prefix_map(trait, obj, name, value):
    """Verifies a Python value is in a specified prefix map (i.e. dictionary)"""
    type_info = trait._py_validate
    if value in type_info[1]:
        mapped_value = type_info[1][value]
        return mapped_value
    else:
        # call validator
        return type_info[2](obj, name, value)


def validate_trait_complex(trait, obj, name, value):
    """Verifies a Python value satisifies a complex trait definition"""
    
    list_type_info = trait._py_validate[1]
    
    for type_info in list_type_info:
        switch = type_info[0]
        if switch == 0:
            # type check
            kind = len(type_info)
            if (kind == 3 and value == None) or isinstance(value, type_info[-1]):
                return value
            break
        elif switch == 2:
            # self type check
            if (len(type_info) == 2 and value is None) or isinstance(value, type(obj)):
                return value
            break
        elif switch == 3:
            # integer range check
            if isinstance(value, int):
                int_value = int(value) # XXX a no-op
                low, high, exclude_mask = type_info[1:4]
                if low is not None:
                    if (exclude_mask & 1) != 0:
                        if int_value <= int(low):
                            break
                    else:
                        if int_value < int(low):
                            break
                if high is not None:
                    if (exclude_mask & 2) != 0:
                        if int_value >= int(high):
                            break
                    else:
                        if int_value > int(high):
                            break
                return value
            break
        elif switch == 4:
            # floating point range check
            if not isinstance(value, float):
                # XXX drop this, and just coerce to float?
                if not isinstance(value, int):
                    break
                float_value = value = float(value)
            else:
                # XXX dumb conversion from C -> Python here
                float_value = value
            low, high, exclude_mask = type_info[1:4]
            
            if low is not None:
                if exclude_mask & 1:
                    if float_value <= low:
                        break
                else:
                    if float_value < low:
                        break
        
            if high is not None:
                if exclude_mask & 2:
                    if float_value >= high:
                        break
                else:
                    if float_value > high:
                        break
            return value
        elif switch == 5:
            # enumerated item check
            if value in type_info[1]:
                return value
            break
        elif switch == 6:
            # mapped item check
            if value in type_info[1]:
                return value
            break
        elif switch == 8:
            # Perform 'slow' validate check
            return type_info[1].slow_validate(obj, name, value)
        elif switch == 9:
            # Tuple item check
            result = validate_trait_tuple_check(type_info[1], obj, name, value)
            if result is not None:
                return result
            break
        elif switch == 10:
            # Prefix map item check
            if value in type_info[1]:
                return type_info[1][result]
            
            # call validator
            try:
                return type_info[2](obj, name, value)
            except Exception:
                break
        elif switch == 11:
            # Coercable type check
            # XXX this code is largely the same as the underlying type check
            # should remove duplication/break out into function
            break
        elif switch == 12:
            # Castable type check
            type = type_info[1]
            if isinstance(value, type):
                return value
            else:
                return type(value)
        elif switch == 13:
            # function validator check
            result = type_info[1](obj, name, value)
        # 14 is python validator check
        # 15-18 are setattr validate checks
        elif switch == 19:
            # PyProtocols 'adapt' check
            # XXX not converting just yet
            break
    else:
        raise_trait_error(trait, obj, name, value)

def validate_trait_tuple_check(traits, obj, name, value):
    """Verifies a Python value is a tuple of a specified type and content"""
    if isinstance(value, tuple):
        n = len(traits)
        tup = None
        for i in range(n):
            bitem = value[i]
            itrait = traits[i]
            if itrait._validate is None:
                aitem = bitem
            else:
                # shouldn't need to check for NULL return, as will raise instead
                aitem = itrait._validate(itrait, obj, name, bitem)
            
            if tup is not None:
                tup += (aitem,)
            elif aitem != bitem:
                tup = value[:i] + (aitem,)
                
        if tup is not None:
            return tup
        else:
            return value
    # safe to use None as a return value, as value ought to be a tuple instance
    return None


def validate_trait_tuple(trait, obj, name, value):
    """Verifies a Python value is a tuple of a specified type and content"""
    result = validate_trait_tuple_check(trait._py_validate[1], obj, name, value)
    if result is not None:
        return result
    raise_trait_error(trait, obj, name, value)

    
def validate_trait_coerce_type(trait, obj, name, value):
    """Verifies a Python value is of a specified (possibly coercable) type"""
    type_info = trait._py_validate
    type = type_info[1]
    if isinstance(value, type):
        return value
    # XXX this is a horrid interface: treat tuple up to None one way, then treat
    # things after the None a different way - CJW
    # this is fast C, bad Python
    idx = 2
    coerce = False
    
    while idx < len(type_info):
        type2 = type_info[i]
        if coerce:
            if isinstance(value, type2):
                return type(value)
        else:
            if type2 is None:
                coerce = True
                continue
            if isinstance(value, type2):
                return value

    raise_trait_error(trait, obj, name, value)


def validate_trait_cast_type(trait, obj, name, value):
    """Verifies a Python value is of a specified (possibly castable) type"""
    type_info = trait._py_validate
    type = type_info[1]
    if isinstance(value, type):
        return value

    # XXX type converter returns NULL on failure in C code,
    # I think correct behaviour is to raise an error in this code
    # we catch here and raise a trait error instead
    try:
        return type(value)
    except Exception:
        raise_trait_error(trait, obj, name, value)


def validate_trait_function(trait, obj, name, value):
    """Verifies a Python value satisifies a specified function validator"""
    # XXX NULL return should signal error, what is appropriate python idiom?
    try:
        return trait._py_validate[1](obj, name, value)
    except Exception:
        raise_trait_error(trait, obj, name, value)


def validate_trait_python(trait, obj, name, value):
    """Calls a Python-based trait validator"""
    return trait._py_validate(obj, name, value)
    

def validate_trait_adapt(trait, obj, name, value):
    """Attempts to 'adapt' an object to a specified interface"""
    
    type_info = trait._py_validate
    if value is None:
        if type_info[3]:
            return value
        raise_trait_error(trait, obj, name, value)
    
    type = type_info[1]
    mode = type_info[2]
    
    if mode == 2:
        args = (value, type, None)
    else:
        args = (value, type)
    result = adapt(*args)
    
    # the C code here is really convoluted... and I think it swallows
    # errors in the adapt function...
    if result is not None:
        if mode > 0 or result is value:
            return result
    else:
        result = validate_implements(*args)
        if result:
            return value
        else:
            return default_value_for(trait, obj, name)
        
    result = validate_implements(*args)
    if result:
        return value
    
    raise_trait_error(trait, obj, name, value)
            
    

validate_handlers = [validate_trait_type, validate_trait_instance,
                     validate_trait_self_type, validate_trait_int,
                     validate_trait_float, validate_trait_enum,
                     validate_trait_map, validate_trait_complex,
                     None, validate_trait_tuple, 
                     validate_trait_prefix_map, validate_trait_coerce_type,
                     validate_trait_cast_type, validate_trait_function,
                     validate_trait_python, setattr_validate0,
                     setattr_validate1, setattr_validate2, 
                     setattr_validate3, validate_trait_adapt]


#------------------
# Delegate handlers
#------------------
def delegate_attr_name_name(trait, obj, name):
    return name


def delegate_attr_name_prefix(trait, obj, name):
    return trait._delegate_prefix


def delegate_attr_name_prefix_name(trait, obj, name):
    return trait._delegate_prefix + name


def delegate_attr_name_class_name(trait, obj, name):
    try:
        prefix = getattr(obj.__class__, '__prefix__')
    except AttributeError:
        return name

    return prefix + name

#--------------
# Handler lists
#--------------

getattr_handlers = [getattr_trait, getattr_python, getattr_event,
                    getattr_delegate, getattr_event, getattr_disallow,
                    getattr_trait, getattr_constant, getattr_generic]


setattr_handlers = [setattr_trait, setattr_python, setattr_event,
                    setattr_delegate, setattr_event, setattr_disallow,
                    setattr_readonly, setattr_constant, setattr_generic]


getattr_property_handlers = [getattr_property0, getattr_property1,
                             getattr_property2, getattr_property3]

setattr_property_handlers = [setattr_property0, setattr_property1, 
                             setattr_property2, setattr_property3, 
                             post_setattr_trait_python, None]

setattr_validate_handlers = [setattr_validate0, setattr_validate1,
                             setattr_validate2, setattr_validate3]

validate_handlers = [validate_trait_type, validate_trait_instance,
                     validate_trait_self_type, validate_trait_int,
                     validate_trait_float, validate_trait_enum,
                     validate_trait_map, validate_trait_complex,
                     None, validate_trait_tuple, 
                     validate_trait_prefix_map, validate_trait_coerce_type,
                     validate_trait_cast_type, validate_trait_function,
                     validate_trait_python, setattr_validate0,
                     setattr_validate1, setattr_validate2, 
                     setattr_validate3, validate_trait_adapt]

delegate_attr_name_handlers = [delegate_attr_name_name, 
                               delegate_attr_name_prefix,
                               delegate_attr_name_prefix_name,
                               delegate_attr_name_class_name,
                               None]


#------------------------------------------------------------------------------
# Trait exceptions and error functions
#------------------------------------------------------------------------------

class TraitError(Exception):
    pass


class DelegationError(Exception):
    pass


def raise_trait_error(trait, obj, name, value):
    trait.handler.error(obj, nam, value)


def fatal_trait_error():
    raise TraitError('Non-trait found in trait dictionary')


def invalid_attribute_error():
    raise TypeError('Attribute name must be a string')


def bad_trait_error():
    raise TraitError('Invalid argument to a trait constructor')


def cant_set_items_error():
    raise TraitError("Can not set a collection's '_items' trait")


def bad_trait_value_error():
    raise TraitError("Result of 'as_ctrait' method was not a 'CTraits' "
                     "instance.")


def bad_delegate_error(obj, name):
    if not isinstance(name, basestring):
        invalid_attribute_error()
    raise DelegationError("The '%.s' attribute of a '%s' object delegates to "
                          "and attribute which is not a defined trait." 
                          % (name, obj.__class__.__name__))


def bad_delegate_error2(obj, name):
    if not isinstance(name, basestring):
        invalid_attribute_error()
    raise DelegationError("The '%.s' attribute of a '%s' object delegates to "
                          "and attribute which does not have traits." 
                          % (name, obj.__class__.__name__))


def delegation_recursion_error(obj, name):
    if not isinstance(name, basestring):
        invalid_attribute_error()
    raise DelegationError("Delegation recursion limit exceeded while setting "
                          "the '%s' attribute of a '%s' object". 
                          % (name, obj.__class__.__name__))


def delegation_recursion_error2(obj, name):
    if not isinstance(name, basestring):
        invalid_attribute_error()
    raise DelegationError("Delegation recursion limit exceeded while getting "
                          "the defintion of the '%s' trait of a '%s' object."
                          % (name, obj.__class__.__name__))


def delete_readonly_error(obj, name):
    if not isinstance(name, basestring):
        invalid_attribute_error()
    raise TraitError("Cannot delete the read only '%s' attribute of a '%s' "
                     "object." % (name, obj.__class__.__name__))


def set_readonly_error(obj, name):
    if not isinstance(name, basestring):
        invalid_attribute_error()
    raise TraitError("Cannot modify the read only '%s' attribute of a '%s' "
                     "object." % (name, obj.__class__.__name__))


def set_disallow_error(obj, name):
    if not isinstance(name, basestring):
        invalid_attribute_error()
    raise TraitError("Cannot set the undefined '%s' attribute of a '%s' "
                     "object." % (name, obj.__class__.__name__))


def set_delete_property_error(obj, name):
    if not isinstance(name, basestring):
        invalid_attribute_error()
    raise TraitError("Cannot delete the '%s' property of a '%s' object."
                     % (name, obj.__class__.__name__))


def unknown_attribute_error(obj, name):
    raise AttributeError("'%s' object has no attribute '%s'."
                         % (obj.__class__.__name__, name))


def dictionary_error():
    raise TypeError("__dict__ must be set to a dictionary.")


def argument_error(trait, meth, arg, obj, name, value):
    trait.handler.arg_error(meth, int(arg), obj, name, value)


def keyword_argument_error(trait, meth, obj, name, value):
    trait.handler.keyword_error(meth, obj, name, value)


def dup_argument_error(trait, meth, arg, obj, name):
    trait.handler.dup_arg_error(meth, int(arg), obj, name)


def missing_argument_error(trait, meth, arg, obj, name):
    trait.handler.missing_arg_error(meth, int(arg), obj, name)
                            

def too_many_args_error(name, wanted, received):
    if wanted == 0:
        raise TypeError("%s() takes no arguments (%s given)" 
                        % (name, received))
    elif wanted == 1:
        raise TypeError("%s() takes exactly 1 argument (%s given)"
                        % (name, received))
    else:
        raise TypeError("%s() takes exactly %s arguments (%s given)"
                        % (name, wanted, received))


def invalid_result_error(trait, meth, obj, value):
    trait.handler.return_error(meth, obj, value)


