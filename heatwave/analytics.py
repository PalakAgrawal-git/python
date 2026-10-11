def heat_index(temp_c, humidity):
    """NWS Rothfusz regression. Returns feel-like temperature in °C."""
    T  = temp_c * 9 / 5 + 32   # convert to °F
    rh = humidity
    HI = (-42.379
          + 2.04901523  * T
          + 10.14333127 * rh
          - 0.22475541  * T  * rh
          - 0.00683783  * T  ** 2
          - 0.05481717  * rh ** 2
          + 0.00122874  * T  ** 2 * rh
          + 0.00085282  * T  * rh ** 2
          - 0.00000199  * T  ** 2 * rh ** 2)
    return round((HI - 32) * 5 / 9, 1)   # back to °C


def linear_trend(values, steps=5):
    """Least-squares linear extrapolation; returns `steps` future values."""
    n = len(values)
    if n < 2:
        return []
    xs      = list(range(n))
    x_mean  = sum(xs) / n
    y_mean  = sum(values) / n
    denom   = sum((x - x_mean) ** 2 for x in xs)
    if denom == 0:
        return [round(y_mean, 1)] * steps
    slope     = sum((xs[i] - x_mean) * (values[i] - y_mean) for i in range(n)) / denom
    intercept = y_mean - slope * x_mean
    return [round(slope * (n + i) + intercept, 1) for i in range(steps)]
