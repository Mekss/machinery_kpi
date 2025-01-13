import random
import datetime


def random_timestamp(base_time, i):
    """
    Generate a timestamp offset by 'i' minutes (or seconds) from base_time
    """
    return (base_time + datetime.timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S")


def generate_sensor_value(sensor_tuple):
    """
    Given the sensor definition (key, sensor_name, maxVal, minVal),
    generate mostly valid data but sometimes exceed constraints by a bit.
    """
    (raw_key, sensor_name, max_val, min_val) = sensor_tuple

    # If max_val is None, we interpret the constraint as only a min constraint
    # If min_val is None, we interpret the constraint as only a max constraint
    # If both are not None, we have a range.

    exceed_chance = 0.05  # 5% chance to exceed constraints
    if max_val is not None and min_val is not None:
        # Normal range
        value = random.uniform(min_val, max_val)
        # Possibly exceed
        if random.random() < exceed_chance:
            # exceed by up to 10%
            value *= 1.1
        return value
    elif max_val is not None:
        # e.g. we have only a max
        value = random.uniform(0, max_val)
        if random.random() < exceed_chance:
            value = max_val * 1.1  # exceed by 10%
        return value
    elif min_val is not None:
        # e.g. we have only a min
        # We'll pick a random upper bound to keep it interesting
        upper_bound = min_val + 2.0  # or some big range
        value = random.uniform(min_val, upper_bound)
        if random.random() < exceed_chance:
            # go below the min or above an imaginary upper bound
            value = min_val - 0.1
        return value
    else:
        # No numeric constraint found; just return some random number
        return random.uniform(0, 100)
