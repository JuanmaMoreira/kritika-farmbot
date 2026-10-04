"""Shared Sapphire pressure policy for MW investment and Stages readiness."""
SAPPHIRE_PRESSURE_LIMIT = 102

def sapphire_pressure_passes(sapphires, *, pressure_limit=SAPPHIRE_PRESSURE_LIMIT):
    if type(sapphires) is not int or sapphires < 0:
        raise ValueError('sapphires must be a non-negative integer')
    if type(pressure_limit) is not int or pressure_limit < 1:
        raise ValueError('pressure_limit must be positive')
    return max(0, (sapphires - (pressure_limit - 1) + 99) // 100)
