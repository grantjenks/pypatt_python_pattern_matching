"""Functional Python Pattern Matching

Python pattern matching using a function-based approach.

Python Pattern Matching contributions:

* API for matching: __match__ and Matcher object for state
* Method of binding values to names
* Algorithm for patterns (generic regex)
* New match rule for "types"

TODO:

* Add __match__ predicate and refactor cases
* Improve docstrings with examples.
* Bug: validate group against previous bindings:
  match([1, 2, 3, 2], anyone * repeat + [anyone * group('value'), 2, anyone * group('value')])
* Add Set predicate and action?
  def set_predicate(matcher, value, pattern):
      return isinstance(pattern, Set)

  def set_action(matcher, value, pattern):
      value_sequence = tuple(value)
      for permutation in itertools.permutations(pattern):
          try:
              matcher.names.push()
              matcher.visit(value_sequence, permutation)
              matcher.names.pull()
              return
          except Mismatch:
              matcher.names.undo()
      else:
          raise Mismatch
* Add Mapping predicate and action?
* Add Start and End to patterns
* Add Name support as anyone * group('name') to patterns
* Add Like support with backtracking to patterns

"""

from collections import Sequence, Mapping
from functools import wraps
from sys import hexversion

infinity = float('inf')


class Record(object):
    """Mutable "named tuple"-like base class."""
    __slots__ = ()

    def __init__(self, *args):
        for field, value in zip(self.__slots__, args):
            setattr(self, field, value)

    def __getitem__(self, index):
        return getattr(self, self.__slots__[index])

    def __eq__(self, that):
        if not isinstance(that, type(self)):
            return NotImplemented
        return (self.__slots__ == that.__slots__
                and all(item == iota for item, iota in zip(self, that)))

    def __repr__(self):
        args = ', '.join(repr(item) for item in self)
        return '%s(%s)' % (type(self).__name__, args)

    def __getstate__(self):
        return tuple(self)

    def __setstate__(self, state):
        self.__init__(*state)


class Case(Record):
    """Three-ple of `name`, `predicate`, and `action`.

    `Matcher` objects successively try a sequence of `Case` predicates. When a
    match is found, the `Case` action is applied.

    """
    __slots__ = 'name', 'predicate', 'action'

base_cases = []


class Mismatch(Exception):
    "Raised by `action` functions of `Case` records to abort on mismatch."
    pass


class Details(Sequence):
    """Abstract base class extending `Sequence` to define equality and hashing.

    Defines one slot, `_details`, for comparison and hashing.

    Used by `Pattern` and `PatternMixin` types.

    """
    __slots__ = '_details',

    def __eq__(self, that):
        return self._details == that._details

    def __ne__(self, that):
        return self._details != that._details

    def __hash__(self):
        return hash(self._details)


def make_tuple(value):
    """Return value as tuple.

    >>> make_tuple((1, 2, 3))
    (1, 2, 3)
    >>> make_tuple('abc')
    ('a', 'b', 'c')
    >>> make_tuple([4, 5, 6])
    (4, 5, 6)
    >>> make_tuple(None)
    (None,)

    """
    if isinstance(value, tuple):
        return value
    elif isinstance(value, Sequence):
        return tuple(value)
    else:
        return (value,)


class Pattern(Details):
    """Wrap tuple to extend addition operator.

    >>> Pattern()
    Pattern()
    >>> Pattern([1, 2, 3])
    Pattern(1, 2, 3)
    >>> Pattern() + [1, 2, 3]
    Pattern(1, 2, 3)
    >>> None + Pattern()
    Pattern(None)
    >>> list(Pattern(4, 5, 6))
    [4, 5, 6]

    """
    def __init__(self, *args):
        self._details = make_tuple(args[0] if len(args) == 1 else args)

    def __getitem__(self, index):
        return self._details[index]

    def __len__(self):
        return len(self._details)

    def __add__(self, that):
        return Pattern(self._details + make_tuple(that))

    def __radd__(self, that):
        return Pattern(make_tuple(that) + self._details)

    def __repr__(self):
        args = ', '.join(repr(value) for value in self._details)
        return '%s(%s)' % (type(self).__name__, args)


def sequence(value):
    """Return value as sequence.

    >>> sequence('abc')
    'abc'
    >>> sequence(1)
    (1,)
    >>> sequence([1])
    [1]

    """
    return value if isinstance(value, Sequence) else (value,)


class PatternMixin(Details):
    """Abstract base class to wrap a tuple to extend multiplication and
    addition.

    """
    def __getitem__(self, index):
        if index == 0:
            return self
        else:
            raise IndexError

    def __len__(self):
        return 1

    def __add__(self, that):
        return Pattern(self) + that

    def __radd__(self, that):
        return that + Pattern(self)

    def __mul__(self, that):
        return that.__rmul__(self)

    def __getattr__(self, name):
        return getattr(self._details, name)

    def __repr__(self):
        pairs = zip(self._details.__slots__, self._details)
        tokens = ('%s=%s' % (name, repr(value)) for name, value in pairs)
        return '%s(%s)' % (type(self).__name__, ', '.join(tokens))


###############################################################################
# Match Case: anyone
###############################################################################

class Anyone(PatternMixin):
    """Match any one thing.

    >>> Anyone()
    anyone
    >>> match('blah', Anyone())
    True
    >>> anyone + [1, 2, 3]
    Pattern(anyone, 1, 2, 3)
    >>> (4, 5) + anyone + None
    Pattern(4, 5, anyone, None)

    """
    def __init__(self):
        self._details = ()

    def __repr__(self):
        return 'anyone'


anyone = Anyone()

def anyone_predicate(matcher, value, pattern):
    "Return True if `pattern` is an instance of `Anyone`."
    return isinstance(pattern, Anyone)

def anyone_action(matcher, value, anyone):
    "Return `value` because `anyone` matches any one thing."
    return value

base_cases.append(Case('anyone', anyone_predicate, anyone_action))


###############################################################################
# Match Case: names
###############################################################################

class Name(Record):
    """Name objects simply wrap a `value` to be used as a name.

    >>> match([1, 2, 3], [Name('head'), 2, 3])
    True
    >>> bound.head == 1
    True

    """
    __slots__ = 'value',

class Binder(object):
    """Binder objects return Name objects on attribute lookup.

    A few attributes behave specially:

    * `bind.any` returns an `Anyone` object.
    * `bind.push`, `bind.pop`, and `bind.restore` raise an AttributeError
      because the names would conflict with `Bounder` attributes.

    >>> bind = Binder()
    >>> bind.head
    Name('head')
    >>> bind.tail
    Name('tail')
    >>> bind.any
    anyone
    >>> bind.push
    Traceback (most recent call last):
        ...
    AttributeError

    """
    def __getattr__(self, name):
        if name == 'any':
            return anyone
        elif name in ('push', 'pop', 'restore'):
            raise AttributeError
        else:
            return Name(name)

bind = Binder()

def name_predicate(matcher, value, pattern):
    "Return True if `pattern` is an instance of `Name`."
    return isinstance(pattern, Name)

def name_store(matcher, name, value):
    """Store `value` in `matcher.names` with given `name`.

    If `name` is already present in `matcher.names` then raise `Mismatch` on
    inequality between `value` and stored value.

    """
    if name in matcher.names:
        if value == matcher.names[name]:
            pass  # Prefer equality comparison to inequality.
        else:
            raise Mismatch
    matcher.names[name] = value

def name_action(matcher, value, name):
    "Store `value` in `matcher` with name, `name.value`."
    name_store(matcher, name.value, value)
    return value

base_cases.append(Case('names', name_predicate, name_action))


###############################################################################
# Match Case: likes
###############################################################################

class Like(Record):
    __slots__ = 'pattern', 'name'

def like(pattern, name='match'):
    """Return `Like` object with given `pattern` and `name`, default "match".

    >>> like('abc.*')
    Like('abc.*', 'match')
    >>> like('abc.*', 'prefix')
    Like('abc.*', 'prefix')

    """
    return Like(pattern, name)

def like_predicate(matcher, value, pattern):
    "Return True if `pattern` is an instance of `Like`."
    return isinstance(pattern, Like)

import re

if hexversion > 0x03000000:
    unicode = str

like_errors = (
    AttributeError, LookupError, NotImplementedError, TypeError, ValueError
)

def like_action(matcher, value, pattern):
    """Apply `pattern` as callable to `value` and store result in `matcher`.

    Given `pattern` is expected as `Like` instance and deconstructed by
    attribute into `name` and `pattern`.

    When `pattern` is text then it is used as a regular expression.

    When `name` is None then the result is not stored in `matcher.names`.

    Raises `Mismatch` if callable raises exception in `like_errors` or result
    is falsy.

    >>> match('abcdef', like('abc.*'))
    True
    >>> match(123, like(lambda num: num % 2 == 0))
    False

    """
    name = pattern.name
    pattern = pattern.pattern

    if isinstance(pattern, (str, unicode)):
        if not isinstance(value, (str, unicode)):
            raise Mismatch
        func = lambda value: re.match(pattern, value)
    else:
        func = pattern

    try:
        result = func(value)
    except like_errors:
        raise Mismatch

    if not result:
        raise Mismatch

    if name is not None:
        name_store(matcher, name, result)

    return result

base_cases.append(Case('likes', like_predicate, like_action))


###############################################################################
# Match Case: types
###############################################################################

def type_predicate(matcher, value, pattern):
    "Return True if `pattern` is an instance of `type`."
    return isinstance(pattern, type)

def type_action(matcher, value, pattern):
    """Match `value` as subclass or instance of `pattern`.

    >>> match(1, int)
    True
    >>> match(True, bool)
    True
    >>> match(True, int)
    True
    >>> match(bool, int)
    True
    >>> match(0.0, int)
    False
    >>> match(float, int)
    False

    """
    if isinstance(value, type) and issubclass(value, pattern):
        return value
    elif isinstance(value, pattern):
        return value
    else:
        raise Mismatch

base_cases.append(Case('types', type_predicate, type_action))


###############################################################################
# Match Case: literals
###############################################################################

if hexversion < 0x03000000:
    literal_types = (type(None), bool, int, float, long, complex, basestring)
else:
    literal_types = (type(None), bool, int, float, complex, str, bytes)

def literal_predicate(matcher, value, pattern):
    "Return True if `value` and `pattern` instance of `literal_types`."
    literal_pattern = isinstance(pattern, literal_types)
    return literal_pattern and isinstance(value, literal_types)

def literal_action(matcher, value, pattern):
    """Match `value` as equal to `pattern`.

    >>> match(1, 1)
    True
    >>> match('abc', 'abc')
    True
    >>> match(1, 1.0)
    True
    >>> match(1, True)
    True

    """
    if value == pattern:
        return value
    else:
        raise Mismatch

base_cases.append(Case('literals', literal_predicate, literal_action))


###############################################################################
# Match Case: equality
###############################################################################

def equality_predicate(matcher, value, pattern):
    "Return True if `value` equals `pattern`."
    try:
        return value == pattern
    except Exception:
        return False

def equality_action(matcher, value, pattern):
    """Match `value` as equal to `pattern`.

    >>> identity = lambda value: value
    >>> match(identity, identity)
    True
    >>> match('abc', 'abc')
    True
    >>> match(1, 1.0)
    True
    >>> match(1, True)
    True

    """
    return value

base_cases.append(Case('equality', equality_predicate, equality_action))


###############################################################################
# Match Case: sequences
###############################################################################

def sequence_predicate(matcher, value, pattern):
    """Return True if `value` is instance of type of `pattern` and `pattern` is
    instance of Sequence and lengths are equal.

    """
    return (
        isinstance(value, type(pattern))
        and isinstance(pattern, Sequence)
        and len(value) == len(pattern)
    )

if hexversion < 0x03000000:
    from itertools import izip as zip

def sequence_action(matcher, value, pattern):
    """Iteratively match items of `pattern` with `value` in sequence.

    Return tuple of results of matches.

    >>> match([0, 'abc', {}], [int, str, dict])
    True
    >>> match((0, True, bool), (0.0, 1, int))
    True
    >>> match([], ())
    False

    """
    pairs = zip(value, pattern)
    return tuple(matcher.visit(item, iota) for item, iota in pairs)

base_cases.append(Case('sequences', sequence_predicate, sequence_action))


###############################################################################
# Match Case: patterns
###############################################################################

class _Repeat(Record):
    __slots__ = 'pattern', 'min', 'max', 'greedy'

class Repeat(PatternMixin):
    """Pattern specifying repetition with min/max count and greedy parameters.

    Inherits from `PatternMixin` which defines multiplication operators to
    capture patterns.

    >>> Repeat()
    Repeat(pattern=(), min=0, max=inf, greedy=True)
    >>> repeat = Repeat()
    >>> repeat(max=1)
    Repeat(pattern=(), min=0, max=1, greedy=True)
    >>> maybe = repeat(max=1)
    >>> Repeat(anyone)
    Repeat(pattern=anyone, min=0, max=inf, greedy=True)
    >>> anyone * repeat
    Repeat(pattern=anyone, min=0, max=inf, greedy=True)
    >>> anything = anyone * repeat
    >>> anyone * repeat(min=1)
    Repeat(pattern=anyone, min=1, max=inf, greedy=True)
    >>> something = anyone * repeat(min=1)
    >>> padding = anyone * repeat(greedy=False)

    """
    def __init__(self, pattern=(), min=0, max=infinity, greedy=True):
        self._details = _Repeat(pattern, min, max, greedy)

    def __rmul__(self, that):
        return type(self)(sequence(that), *tuple(self._details)[1:])

    def __call__(self, min=0, max=infinity, greedy=True, pattern=()):
        return type(self)(pattern, min, max, greedy)

repeat = Repeat()
maybe = repeat(max=1)
anything = anyone * repeat
something = anyone * repeat(min=1)
padding = anyone * repeat(greedy=False)


class _Group(Record):
    __slots__ = 'pattern', 'name'

class Group(PatternMixin):
    """Pattern specifying a group with name parameter.

    Inherits from `PatternMixin` which defines multiplication operators to
    capture patterns.

    >>> Group()
    Group(pattern=(), name=None)
    >>> Group(['red', 'blue', 'yellow'], 'color')
    Group(pattern=['red', 'blue', 'yellow'], name='color')
    >>> group = Group()
    >>> ['red', 'blue', 'yellow'] * group('color')
    Group(pattern=['red', 'blue', 'yellow'], name='color')

    """
    def __init__(self, pattern=(), name=None):
        self._details = _Group(pattern, name)

    def __rmul__(self, that):
        return type(self)(sequence(that), *tuple(self._details)[1:])

    def __call__(self, name=None, pattern=()):
        return type(self)(pattern, name)

group = Group()


class _Options(Record):
    __slots__ = 'options',

class Options(PatternMixin):
    "Pattern specifying a sequence of options to match."
    def __init__(self, *options):
        self._details = _Options(tuple(map(sequence, options)))

    def __call__(self, *options):
        return type(self)(*options)

    def __rmul__(self, that):
        return type(self)(*sequence(that))

    def __repr__(self):
        args = ', '.join(map(repr, self._details.options))
        return '%s(%s)' % (type(self).__name__, args)


class Either(Options):
    "Pattern specifying that any of options may match."
    pass

either = Either()


class Exclude(Options):
    "Pattern specifying that none of options may match."
    pass

exclude = Exclude()


NONE = object()

def pattern_predicate(matcher, value, pattern):
    "Return True if `pattern` is an instance of `Pattern` or `PatternMixin`."
    return isinstance(pattern, (Pattern, PatternMixin))

def pattern_action(matcher, sequence, pattern):
    """Match `pattern` to `sequence` with `Pattern` semantics.

    The `Pattern` type is used to define semantics like regular expressions.

    >>> match([0, 1, 2], [0, 1] + anyone)
    True
    >>> match([0, 0, 0, 0], 0 * repeat)
    True
    >>> match('blue', either('red', 'blue', 'yellow'))
    True
    >>> match([2, 4, 6], exclude(like(lambda num: num % 2)) * repeat(min=3))
    True

    """
    names = matcher.names
    len_sequence = len(sequence)

    def visit(pattern, index, offset, count):
        len_pattern = len(pattern)

        if index == len_pattern:
            yield offset
            return

        while True:
            item = pattern[index]

            if isinstance(item, Repeat):
                if count > item.max:
                    return

                if item.greedy:
                    if offset < len_sequence:
                        for end in visit(item.pattern, 0, offset, count):
                            for stop in visit(pattern, index, end, count + 1):
                                yield stop

                    if count >= item.min:
                        for stop in visit(pattern, index + 1, offset, 0):
                            yield stop
                else:
                    if count >= item.min:
                        for stop in visit(pattern, index + 1, offset, 0):
                            yield stop

                    if offset < len_sequence:
                        for end in visit(item.pattern, 0, offset, count):
                            for stop in visit(pattern, index, end, count + 1):
                                yield stop

                return

            elif isinstance(item, Group):
                for end in visit(item.pattern, 0, offset, 0):
                    if item.name is not None:
                        prev = names.pop(item.name, NONE)
                        names[item.name] = sequence[offset:end]

                    for stop in visit(pattern, index + 1, end, 0):
                        yield stop

                    if item.name is not None and prev is not NONE:
                        names[item.name] = prev

                return

            elif isinstance(item, Either):
                for option in item.options:
                    for end in visit(option, 0, offset, 0):
                        for stop in visit(pattern, index + 1, end, 0):
                            yield stop
                return

            elif isinstance(item, Exclude):
                for option in item.options:
                    for end in visit(option, 0, offset, 0):
                        return

            else:
                if offset >= len_sequence:
                    return
                else:
                    try:
                        matcher.visit(sequence[offset], item)
                    except Mismatch:
                        return

            index += 1
            offset += 1

            if index == len_pattern:
                yield offset
                return

    for end in visit(pattern, 0, 0, 0):
        return sequence[:end]
    else:
        raise Mismatch

base_cases.append(Case('patterns', pattern_predicate, pattern_action))


###############################################################################
# Store bound names in a stack.
###############################################################################

class Bounder(object):
    """Stack for storing names bound to values for `Matcher`.

    >>> Bounder()
    Bounder([])
    >>> bound = Bounder([{'foo': 0}])
    >>> bound.foo
    0
    >>> len(bound)
    1
    >>> bound.pop()
    {'foo': 0}
    >>> len(bound)
    0
    >>> bound.push({'bar': 1})
    >>> len(bound)
    1

    """
    def __init__(self, maps=()):
        self._maps = list(maps)

    def __getattr__(self, attr):
        try:
            return self._maps[-1][attr]
        except IndexError, KeyError:
            raise AttributeError(attr)

    def __getitem__(self, key):
        try:
            return self._maps[-1][key]
        except IndexError:
            raise KeyError(key)

    def __eq__(self, that):
        return self._maps[-1] == that

    def __ne__(self, that):
        return self._maps[-1] != that

    def __iter__(self):
        return iter(self._maps[-1])

    def __len__(self):
        return len(self._maps)

    def push(self, mapping):
        self._maps.append(mapping)

    def pop(self):
        return self._maps.pop()

    def reset(self, func=None):
        if func is None:
            del self._maps[:]
        else:
            @wraps(func)
            def wrapper(*args, **kwargs):
                start = len(self._maps)
                try:
                    return func(*args, **kwargs)
                finally:
                    while len(self._maps) > start:
                        self.pop()
            return wrapper

    def __repr__(self):
        return '%s(%r)' % (type(self).__name__, self._maps)


###############################################################################
# Stack of mappings.
###############################################################################

class MapStack(Mapping):
    def __init__(self, maps=()):
        self._maps = list(maps) or [{}]

    def push(self):
        self._maps.append({})

    def pull(self):
        _maps = self._maps
        mapping = _maps.pop()
        accumulator = _maps[-1]
        accumulator.update(mapping)

    def undo(self):
        return self._maps.pop()

    def __getitem__(self, key):
        for mapping in reversed(self._maps):
            if key in mapping:
                return mapping[key]
        else:
            raise KeyError(key)

    def __setitem__(self, key, value):
        self._maps[-1][key] = value

    def __delitem__(self, key):
        del self._maps[-1][key]

    def pop(self, key, default=None):
        return self._maps[-1].pop(key, default)

    def __iter__(self):
        return iter(set().union(*self._maps))

    def __len__(self):
        return len(set().union(*self._maps))

    def __repr__(self):
        return '%s(%r)' % (type(self).__name__, self._maps)

    def get(self, key, default=None):
        return self[key] if key in self else default

    def __contains__(self, key):
        return any(key in mapping for mapping in self._maps)

    def __bool__(self):
        return any(self._maps)

    def copy(self):
        return dict(self)

    def reset(self):
        del self._maps[1:]
        self._maps[0].clear()


###############################################################################
# Matcher objects put it all together.
###############################################################################

class Matcher(object):
    """Container for match function state with list of pattern cases.

    >>> matcher = Matcher()
    >>> matcher.match(None, None)
    True
    >>> matcher.match(0, int)
    True
    >>> match = matcher.match
    >>> match([1, 2, 3], [1, bind.middle, 3])
    True
    >>> matcher.bound.middle
    2
    >>> bound = matcher.bound
    >>> match([(1, 2, 3), 4, 5], [bind.any, 4, bind.tail])
    True
    >>> bound.tail
    5

    """
    def __init__(self, cases=base_cases):
        self.cases = cases
        self.bound = Bounder()
        self.names = MapStack()

    def match(self, value, pattern):
        names = self.names
        try:
            self.visit(value, pattern)
        except Mismatch:
            return False
        else:
            self.bound.push(names.copy())
        finally:
            names.reset()
        return True

    def visit(self, value, pattern):
        for name, predicate, action in self.cases:
            if predicate(self, value, pattern):
                return action(self, value, pattern)
        raise Mismatch


matcher = Matcher()
match = matcher.match
bound = matcher.bound
