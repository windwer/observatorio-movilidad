"""Version every assumption that affects pedestrian results and resident indices."""
import hashlib
import json

METHOD_VERSION='walk-network-anchors-v3'
WALK_PROFILE={'speed_kmh':4.5,'max_snap_m':80,'steps_factor':1.55,
              'track_factor':1.25,'unpaved_factor':1.2,'display_buffer_m':18,
              'closed_loops':'split','oneway_foot':'directed-origin-and-destination'}

def signature():
    return hashlib.sha256(json.dumps({'method':METHOD_VERSION,'profile':WALK_PROFILE},sort_keys=True).encode()).hexdigest()
