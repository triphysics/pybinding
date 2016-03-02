"""Modifier decorators

Used to create functions which express some feature of a tight-binding model,
such as various fields, defects or geometric deformations.
"""
import inspect
import functools

import numpy as np

from . import _cpp
from .system import Sites
from .support.inspect import get_call_signature
from .utils.misc import decorator_decorator

__all__ = ['site_state_modifier', 'site_position_modifier', 'onsite_energy_modifier',
           'hopping_energy_modifier', 'constant_potential', 'force_double_precision',
           'hopping_generator']


class _AliasArray(np.ndarray):
    """Helper class for modifier arguments

    This ndarray subclass enables comparing sub_id and hop_id arrays directly with
    their friendly string identifiers. The mapping parameter translates sublattice
    or hopping names into their number IDs.

    Examples
    --------
    >>> a = _AliasArray([0, 1, 0], {'A': 0, 'B': 1})
    >>> list(a == 0)
    [True, False, True]
    >>> list(a == 'A')
    [True, False, True]
    """
    def __new__(cls, array, mapping):
        obj = np.asarray(array).view(cls)
        obj.mapping = mapping
        return obj

    def __array_finalize__(self, obj):
        if obj is None:
            return
        self.mapping = getattr(obj, 'mapping', None)

    def __eq__(self, other):
        if isinstance(other, str):
            return super().__eq__(self.mapping[other])
        else:
            return super().__eq__(other)

    def __ne__(self, other):
        return np.logical_not(self.__eq__(other))


def _make_alias_array(obj):
    if isinstance(obj, (_cpp.SubIdRef, _cpp.HopIdRef)):
        return _AliasArray(obj.ids, obj.name_map)
    else:
        return obj


def _process_modifier_args(args, keywords, requested_argnames):
    """Return only the requested modifier arguments

    Also process any special args like 'sub_id', 'hop_id' and 'sites'.
    """
    kwargs = dict(zip(keywords, args))
    if 'sub_id' in requested_argnames or 'sites' in requested_argnames:
        kwargs['sub_id'] = _make_alias_array(kwargs['sub_id'])
    if 'hop_id' in requested_argnames:
        kwargs['hop_id'] = _make_alias_array(kwargs['hop_id'])

    requested_kwargs = {name: value for name, value in kwargs.items()
                        if name in requested_argnames}

    if 'sites' in requested_argnames:
        requested_kwargs['sites'] = Sites((kwargs[k] for k in ('x', 'y', 'z')), kwargs['sub_id'])

    return requested_kwargs


def _check_modifier_spec(func, keywords, has_sites=False):
    """Make sure the arguments are specified correctly

    Parameters
    ----------
    func : callable
        The function which is to become a modifier.
    keywords : list
        Used to check that `func` arguments are correct.
    has_sites : bool
        Check for 'site' argument.
    """
    argnames = inspect.signature(func).parameters.keys()
    if has_sites:
        keywords += ["sites"]
    unexpected = ", ".join([name for name in argnames if name not in keywords])
    if unexpected:
        expected = ", ".join(keywords)
        raise RuntimeError("Unexpected argument(s) in modifier: {unexpected}\n"
                           "Arguments must be any of: {expected}".format(**locals()))


def _check_modifier_return(func, num_arguments, num_return):
    """Make sure the modifier returns the correct type and size

    Parameters
    ----------
    func : callable
        The function which is to become a modifier.
    num_arguments : int
        Expected number of modifier arguments.
    num_return : int
        Expected number of return values.
    """
    in_shape = 10,
    in_data = np.random.rand(*in_shape).astype(np.float16)

    try:
        out_data = func(*(in_data,) * num_arguments)
    except AttributeError as e:
        if "astype" in str(e):  # known issue
            raise RuntimeError("Modifier must return numpy.ndarray")
        else:  # unknown issue
            raise

    out_data = out_data if isinstance(out_data, tuple) else (out_data,)
    if len(out_data) != num_return:
        raise RuntimeError("Modifier expected to return {} ndarray(s), "
                           "but got {}".format(num_return, len(out_data)))
    if any(v.shape != in_shape for v in out_data):
        raise RuntimeError("Modifier must return the same shape ndarray as the arguments")


def _check_modifier_complex(func, num_arguments, can_be_complex):
    """A modifier is complex if it returns complex output for real input

    Parameters
    ----------
    func : callable
        The function which is to become a modifier.
    num_arguments : int
        Expected number of modifier arguments.
    can_be_complex : int
        Is this modifier allowed to have a complex return value.
    """
    dummy_args = [np.array([], dtype=np.float64)] * num_arguments
    # noinspection PyBroadException
    try:
        return_value = func(*dummy_args)
    except Exception:
        # an exception prevented checking, assume the worst case
        return can_be_complex

    is_complex = np.iscomplexobj(return_value)
    if is_complex and not can_be_complex:
        raise RuntimeError("This modifier must not return complex values")
    return is_complex


def _make_modifier(func, kind, keywords, has_sites=True, num_return=1,
                   can_be_complex=False, double=False):
    """Turn a regular function into a modifier of the desired kind

    Parameters
    ----------
    func : callable
        The function which is to become a modifier.
    kind : object
        Modifier base class.
    keywords : str
        String of comma separated names: the expected arguments of a modifier function.
    has_sites : bool
        Arguments may include the :class:`Sites` helper.
    num_return : int
        Expected number of return values.
    can_be_complex : bool
        The modifier may return a complex result even if the input is real.
    double : bool
        The modifier requires double precision floating point.

    Returns
    -------
    Modifier
    """
    keywords = [word.strip() for word in keywords.split(",")]
    _check_modifier_spec(func, keywords, has_sites)
    requested_argnames = tuple(inspect.signature(func).parameters.keys())

    def apply_func(*args):
        requested_kwargs = _process_modifier_args(args, keywords, requested_argnames)
        ret = func(**requested_kwargs)

        def cast_dtype(v):
            return v.astype(args[0].dtype, casting='same_kind', copy=False)

        try:  # cast output array to same element type as the input
            if isinstance(ret, tuple):
                return tuple(map(cast_dtype, ret))
            else:
                return cast_dtype(ret)
        except TypeError:
            return ret

    _check_modifier_return(apply_func, len(keywords), num_return)

    class Modifier(kind):
        callsig = getattr(func, 'callsig', None)
        if not callsig:
            callsig = get_call_signature()
            callsig.function = func

        def __init__(self):
            # noinspection PyArgumentList
            super().__init__(apply_func)
            self.apply = apply_func
            self.is_complex = _check_modifier_complex(apply_func, len(keywords), can_be_complex)
            self.is_double = double

        def __str__(self):
            return str(self.callsig)

        def __repr__(self):
            return repr(self.callsig)

        def __call__(self, *args, **kwargs):
            return func(*args, **kwargs)

    return Modifier()


@decorator_decorator
def site_state_modifier():
    """Modify the state (valid or invalid) of lattice sites, e.g. to create vacancies

    Notes
    -----
    The function parameters must be a combination of any number of the following:

    state : ndarray of bool
        Indicates if a lattice site is valid. Invalid sites will be removed from
        the model after all modifiers have been applied.
    x, y, z : ndarray
        Lattice site position.
    sub_id : ndarray of int
        Sublattice ID. Can be checked for equality with `lattice[sublattice_name]`.
    sites : :class:`.Sites`
        Helper object. Can be used instead of `x, y, z, sub_id`. See :class:`.Sites`.

    The function must return:

    ndarray
        A modified `state` argument or an `ndarray` of the same dtype and shape.
    """
    return functools.partial(_make_modifier, kind=_cpp.SiteStateModifier,
                             keywords="state, x, y, z, sub_id")


@decorator_decorator
def site_position_modifier():
    """Modify the position of lattice sites, e.g. to apply geometric deformations

    Notes
    -----
    The function parameters must be a combination of any number of the following:

    x, y, z : ndarray
        Lattice site position.
    sub_id : ndarray of int
        Sublattice ID. Can be checked for equality with `lattice[sublattice_name]`.
    sites : :class:`.Sites`
        Helper object. Can be used instead of `x, y, z, sub_id`. See :class:`.Sites`.

    The function must return:

    tuple of ndarray
        Modified 'x, y, z' arguments or 3 `ndarray` objects of the same dtype and shape.
    """
    return functools.partial(_make_modifier, kind=_cpp.PositionModifier,
                             keywords="x, y, z, sub_id", num_return=3)


@decorator_decorator
def onsite_energy_modifier(double=False):
    """Modify the onsite energy, e.g. to apply an electric field

    Parameters
    ----------
    double : bool
        Requires the model to use double precision floating point values.
        Default to single precision otherwise.

    Notes
    -----
    The function parameters must be a combination of any number of the following:

    energy : ndarray
        The onsite energy.
    x, y, z : ndarray
        Lattice site position.
    sub_id : ndarray of int
        Sublattice ID. Can be checked for equality with `lattice[sublattice_name]`.
    sites : :class:`.Sites`
        Helper object. Can be used instead of `x, y, z, sub_id`. See :class:`.Sites`.

    The function must return:

    ndarray
        A modified `potential` argument or an `ndarray` of the same dtype and shape.
    """
    return functools.partial(_make_modifier, kind=_cpp.OnsiteModifier, double=double,
                             keywords="energy, x, y, z, sub_id")


@decorator_decorator
def hopping_energy_modifier(double=False):
    """Modify the hopping energy, e.g. to apply a magnetic field

    Parameters
    ----------
    double : bool
        Requires the model to use double precision floating point values.
        Default to single precision otherwise.

    Notes
    -----
    The function parameters must be a combination of any number of the following:

    energy : ndarray
        The hopping energy between two sites.
    x1, y1, z1, x2, y2, z2 : ndarray
        Positions of the two lattice sites connected by the hopping parameter.
    hop_id : ndarray of int
        Hopping ID. Check for equality with `lattice(hopping_name)`.

    The function must return:

    ndarray
        A modified `hopping` argument or an `ndarray` of the same dtype and shape.
    """
    return functools.partial(_make_modifier, kind=_cpp.HoppingModifier,
                             can_be_complex=True, double=double, has_sites=False,
                             keywords="energy, x1, y1, z1, x2, y2, z2, hop_id")


def constant_potential(magnitude):
    """Apply a constant onsite energy to every lattice site

    Parameters
    ----------
    magnitude : float
        In units of eV.
    """
    @onsite_energy_modifier
    def function(energy):
        return energy + magnitude

    return function


def force_double_precision():
    """Forces the model to use double precision even if no other modifier requires it"""
    @onsite_energy_modifier(double=True)
    def mod(energy):
        return energy

    return mod


def _make_generator(func, kind, name, energy, keywords):
    """Turn a regular function into a generator of the desired kind

    Parameters
    ----------
    func : callable
        The function which is to become a modifier.
    kind : object
        Modifier base class.
    keywords : str
        String of comma separated names: the expected arguments of a modifier function.
    """
    keywords = [word.strip() for word in keywords.split(",")]
    _check_modifier_spec(func, keywords)
    requested_argnames = tuple(inspect.signature(func).parameters.keys())

    def generator_func(*args):
        requested_kwargs = _process_modifier_args(args, keywords, requested_argnames)
        return func(**requested_kwargs)

    class Generator(kind):
        callsig = getattr(func, 'callsig', None)
        if not callsig:
            callsig = get_call_signature()
            callsig.function = func

        def __init__(self):
            # noinspection PyArgumentList
            super().__init__(name, energy, generator_func)

        def __str__(self):
            return str(self.callsig)

        def __repr__(self):
            return repr(self.callsig)

        def __call__(self, *args, **kwargs):
            return func(*args, **kwargs)

    return Generator()


@decorator_decorator
def hopping_generator(name, energy):
    """Introduce a new hopping family (with new hop_id) via a list of index pairs

    This can be used to create new hoppings independent of the main :class:`Lattice` definition.
    It's especially useful for creating additional local hoppings, e.g. to model defects.

    Parameters
    ----------
    name : string
        Friendly identifier for the new hopping family.
    energy : Union[float, complex]
        Base hopping energy value.

    Notes
    -----
    The function parameters must be a combination of any number of the following:

    x, y, z : np.ndarray
        Lattice site position.
    sub_id : np.ndarray
        Sublattice ID. Can be checked for equality with `lattice[sublattice_name]`.

    The function must return:

    Tuple[np.ndarray, np.ndarray]
        Arrays of index pairs which form the new hoppings.
    """
    return functools.partial(_make_generator, kind=_cpp.HoppingGenerator,
                             name=name, energy=energy, keywords="x, y, z, sub_id")
