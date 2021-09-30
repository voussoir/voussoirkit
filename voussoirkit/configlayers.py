'''
The purpose of this file is to work with JSON-based config files, where you
load a default configuration, then overlay a user-supplied configuration on
top, overwriting the matching keys and keeping default values for the rest.
The functions will then suggest that the user config needs to be re-saved if
the default key set contains keys that the user key set does not.
'''
import copy
import json

from voussoirkit import pathclass

def recursive_dict_keys(d):
    '''
    Given a dictionary, return a set containing all of its keys and the keys of
    all other dictionaries that appear as values within. The subkeys will use \\
    to indicate their lineage.

    {'hi': {'ho': 'neighbor'}}

    returns

    {'hi', 'hi\\ho'}
    '''
    keys = set(d.keys())
    for (key, value) in d.items():
        if isinstance(value, dict):
            subkeys = {f'{key}\\{subkey}' for subkey in recursive_dict_keys(value)}
            keys.update(subkeys)
    return keys

def recursive_dict_update(target, supply):
    '''
    Update target using supply, but when the value is a dictionary update the
    insides instead of replacing the dictionary itself. This prevents keys that
    exist in the target but don't exist in the supply from being erased.
    Note that we are modifying target in place.

    eg:
    target = {'hi': 'ho', 'neighbor': {'name': 'Wilson'}}
    supply = {'neighbor': {'behind': 'fence'}}

    result: {'hi': 'ho', 'neighbor': {'name': 'Wilson', 'behind': 'fence'}}
    whereas a regular dict.update would have produced:
    {'hi': 'ho', 'neighbor': {'behind': 'fence'}}
    '''
    for (key, value) in supply.items():
        if isinstance(value, dict):
            existing = target.get(key, None)
            if existing is None:
                target[key] = value
            else:
                recursive_dict_update(target=existing, supply=value)
        else:
            target[key] = value

def layer_json(target, supply):
    '''
    target is the dictionary into which the final values will be placed
    (presumably loaded from a default set), and supply is a layer being applied
    on top of the target (presumably a user-supplied set). needs_rewrite is
    True if the target contains keys that the supply did not, indicating that
    the supply is incomplete.
    '''
    target_keys = recursive_dict_keys(target)
    supply_keys = recursive_dict_keys(supply)
    needs_rewrite = len(target_keys.difference(supply_keys)) > 0
    recursive_dict_update(target=target, supply=supply)
    return (target, needs_rewrite)

def load_file(filepath, default_config):
    '''
    Given a filepath to a user-supplied config file, and a dict of default
    values, return a new dict containing the user-supplied values overlaid onto
    the defaults, and needs_rewrite indicating that the user config is missing
    some keys from the default config.
    '''
    path = pathclass.Path(filepath)
    user_config_exists = path.exists

    # This config will hold the final values. We start by loading it with the
    # defaults, so that as we go through the user's config we can overwrite the
    # user-specified keys, and the keys which the user does not specify will
    # remain default.
    final_config = copy.deepcopy(default_config)
    needs_rewrite = False

    if user_config_exists:
        with path.open('r', encoding='utf-8') as handle:
            user_config = json.load(handle)
        (final_config, needs_rewrite) = layer_json(target=final_config, supply=user_config)
    else:
        needs_rewrite = True

    return (final_config, needs_rewrite)
