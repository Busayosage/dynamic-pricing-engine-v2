"""Amendment A1: pricing replay v1.4 = v1.3 with the A1 cooldown policy (SYNTHETIC; SIMULATED RESEARCH).

`replay_pricing.py` (v1.3, the frozen code behind run 20261023-233225_dynamic_pricing_evaluation) is not edited or
copied. v1.4 runs the very same compiled `simulate` loop with one name rebound: the pricing policy module `DP` becomes
`dynamic_pricing_a1` (cooldown measured from the end of the previous markdown window). Ordering, chronology, selling,
expiry, conservation, demand response and revenue booking are therefore identical to v1.3 by construction.
"""
from __future__ import annotations

import types

from dpe.decision import dynamic_pricing_a1 as DPA1
from dpe.decision import replay_pricing as RPP

SIMULATOR_VERSION = "1.4"
_globals = {**vars(RPP), "DP": DPA1, "SIMULATOR_VERSION": SIMULATOR_VERSION}
simulate = types.FunctionType(RPP.simulate.__code__, _globals, "simulate", RPP.simulate.__defaults__)
simulate.__doc__ = "v1.3 `simulate` with the A1 cooldown policy; same arguments, `params` from assumption set v8."
price_days = RPP.price_days
