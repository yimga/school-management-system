"""
Plans & entitlements bounded context.

Platform catalog CRUD (plans, add-ons, country multipliers) lives on the super
control plane (`super:plans_list`, `super:country_multipliers_list`, etc.), not
on platform `/admin/`. This module intentionally registers nothing by default.
"""
