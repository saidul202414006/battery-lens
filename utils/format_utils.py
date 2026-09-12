def format_power_mw(mw: float) -> str:
    if mw is None:
        return "-- W"
    return f"{mw / 1000.0:.1f} W"

def format_percentage(percent: float) -> str:
    if percent is None:
        return "--%"
    return f"{percent:.1f}%"
