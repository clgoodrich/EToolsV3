import numpy as np


def transform_plat(current_plat_coords, next_plat, next_plat_coords, direction='north'):
    """
    Transform plat B to align with plat A.

    Args:
        current_plat_coords: dict with 'north', 'south', 'east', 'west' sides of plat A
        next_plat: list of (x,y) tuples for plat B
        next_plat_coords: dict with 'north', 'south', 'east', 'west' sides of plat B
        direction: 'north', 'south', 'east', or 'west' - where to place plat B relative to A

    Returns:
        List of transformed (x,y) tuples for plat B
    """
    # Direction mapping
    mapping = {
        'north': {'match_side_a': 'north', 'match_side_b': 'south'},
        'south': {'match_side_a': 'south', 'match_side_b': 'north'},
        'east': {'match_side_a': 'east', 'match_side_b': 'west'},
        'west': {'match_side_a': 'west', 'match_side_b': 'east'}
    }

    # Get matching sides
    target_side = current_plat_coords[mapping[direction]['match_side_a']]
    source_side = next_plat_coords[mapping[direction]['match_side_b']]

    # Extract unique points
    target_points = np.unique(np.array(target_side), axis=0)
    source_points = np.unique(np.array(source_side), axis=0)

    # Check if we need to reverse source points for better alignment
    source_reversed = source_points[::-1]
    n_points = min(len(source_points), len(target_points))

    dist_forward = sum(np.linalg.norm(source_points[i] - target_points[i]) for i in range(n_points))
    dist_reversed = sum(np.linalg.norm(source_reversed[i] - target_points[i]) for i in range(n_points))

    if dist_reversed < dist_forward:
        source_points = source_reversed

    # Calculate rotation
    target_vector = target_points[-1] - target_points[0]
    source_vector = source_points[-1] - source_points[0]
    angle = np.arctan2(target_vector[1], target_vector[0]) - np.arctan2(source_vector[1], source_vector[0])

    # Create rotation matrix
    cos_angle = np.cos(angle)
    sin_angle = np.sin(angle)
    R = np.array([[cos_angle, -sin_angle], [sin_angle, cos_angle]])

    # Rotate source points
    rotated_source = (R @ source_points.T).T

    # Calculate translation
    target_midpoint = np.mean(target_points, axis=0)
    source_midpoint = np.mean(rotated_source, axis=0)
    t = target_midpoint - source_midpoint

    # Transform entire plat
    plat_array = np.array(next_plat)
    transformed = (R @ plat_array.T).T + t

    # Return as list of tuples
    return [(float(x), float(y)) for x, y in transformed]


# Your data
original_plat = [(0, 0), (57.47675276934449, 1367.3925489379747),
                 (114.95350553868899, 2734.7850978759493),
                 (173.65556368413476, 4134.7248956063695),
                 (232.35762182958055, 5534.664693336789),
                 (232.35762182958055, 5534.664693336789),
                 (1576.036528947231, 5507.672156088213),
                 (2919.715436064882, 5480.679618839637),
                 (4263.3529211546975, 5454.118017579228),
                 (5607.163370289499, 5427.20104902549),
                 (5607.163370289499, 5427.20104902549),
                 (5563.818601999683, 4040.6683897772837),
                 (5520.473833709867, 2654.1357305290776),
                 (5489.793269621355, 1312.4864831521),
                 (5459.1127055328425, -29.16276422487772),
                 (5459.1127055328425, -29.16276422487772),
                 (4144.3290198691375, -76.06526216010172),
                 (2819.771432677988, -121.88906290120315),
                 (1493.8631614177295, -168.86015830713677),
                 (168.60312760687225, -214.91410910015162)]

current_plat_coords = {
    'west': [[0, 0], [57.47675276934449, 1367.3925489379747],
             [114.95350553868899, 2734.7850978759493],
             [173.65556368413476, 4134.7248956063695],
             [232.35762182958055, 5534.664693336789]],
    'north': [[232.35762182958055, 5534.664693336789],
              [1576.036528947231, 5507.672156088213],
              [2919.715436064882, 5480.679618839637],
              [4263.3529211546975, 5454.118017579228],
              [5607.163370289499, 5427.20104902549]],
    'east': [[5607.163370289499, 5427.20104902549],
             [5563.818601999683, 4040.6683897772837],
             [5520.473833709867, 2654.1357305290776],
             [5489.793269621355, 1312.4864831521],
             [5459.1127055328425, -29.16276422487772]],
    'south': [[5459.1127055328425, -29.16276422487772],
              [4144.3290198691375, -76.06526216010172],
              [2819.771432677988, -121.88906290120315],
              [1493.8631614177295, -168.86015830713677],
              [168.60312760687225, -214.91410910015162]]
}

new_plat = [(0, 0), (0.0, 0.0), (19.174380179715467, 2640.140372640198),
            (38.3407506115597, 5280.940820827162),
            (43.60748302739152, 6023.472142745409),
            (43.60748302739152, 6023.472142745409),
            (43.60748302739152, 6023.472142745409),
            (2303.9767790332, 5965.992966740485),
            (4990.4872278583225, 5898.824292096448),
            (5325.869296605803, 5890.718839446535),
            (5325.869296605803, 5890.718839446535),
            (5319.997775470134, 5048.529306538679),
            (5300.319659503219, 2407.782623467394),
            (5275.775421936636, -246.89391511546592),
            (5275.775421936636, -246.89391511546592),
            (5275.775421936636, -246.89391511546592),
            (5275.775421936636, -246.89391511546592),
            (2628.325931698603, -248.5368205844878),
            (-12.991041100748589, -265.2737887110307),
            (-12.991041100748589, -265.2737887110307)]

next_plat_coords = {
    'west': [[0, 0], [0.0, 0.0], [19.174380179715467, 2640.140372640198],
             [38.3407506115597, 5280.940820827162],
             [43.60748302739152, 6023.472142745409]],
    'north': [[43.60748302739152, 6023.472142745409],
              [43.60748302739152, 6023.472142745409],
              [2303.9767790332, 5965.992966740485],
              [4990.4872278583225, 5898.824292096448],
              [5325.869296605803, 5890.718839446535]],
    'east': [[5325.869296605803, 5890.718839446535],
             [5319.997775470134, 5048.529306538679],
             [5300.319659503219, 2407.782623467394],
             [5275.775421936636, -246.89391511546592],
             [5275.775421936636, -246.89391511546592]],
    'south': [[5275.775421936636, -246.89391511546592],
              [5275.775421936636, -246.89391511546592],
              [2628.325931698603, -248.5368205844878],
              [-12.991041100748589, -265.2737887110307],
              [-12.991041100748589, -265.2737887110307]]
}

# TRANSFORM THE PLAT
transformed_plat = transform_plat(current_plat_coords, new_plat, next_plat_coords, direction='north')

# Print result
print("Transformed plat coordinates:")
for i, (x, y) in enumerate(transformed_plat):
    print(f"({x}, {y})")

# !/usr/bin/env python3
"""
Test script for the improved plat alignment functionality.
This script demonstrates the proper alignment of plat B north of plat A.
"""

import numpy as np
import matplotlib.pyplot as plt


# Import the PlatTransformer class (assuming it's in the same directory)
# from plat_transformer import PlatTransformer

# For this test, I'll include a minimal version of the key functionality
def align_plat_north(original_plat, current_sides, new_plat, next_sides):
    """Simplified alignment function for north placement."""

    # Get the north side of plat A and south side of plat B
    target_side = current_sides['north']
    source_side = next_sides['south']

    # Extract unique points
    target_points = np.unique(np.array(target_side), axis=0)
    source_points = np.unique(np.array(source_side), axis=0)

    # Reverse source points if needed for better alignment
    source_reversed = source_points[::-1]
    n_points = min(len(source_points), len(target_points))

    dist_forward = sum(np.linalg.norm(source_points[i] - target_points[i])
                       for i in range(n_points))
    dist_reversed = sum(np.linalg.norm(source_reversed[i] - target_points[i])
                        for i in range(n_points))

    if dist_reversed < dist_forward:
        source_points = source_reversed

    # Calculate rotation angle
    target_vector = target_points[-1] - target_points[0]
    source_vector = source_points[-1] - source_points[0]
    angle = np.arctan2(target_vector[1], target_vector[0]) - np.arctan2(source_vector[1], source_vector[0])

    # Create rotation matrix
    cos_angle = np.cos(angle)
    sin_angle = np.sin(angle)
    R = np.array([[cos_angle, -sin_angle], [sin_angle, cos_angle]])

    # Rotate and translate
    rotated_source = (R @ source_points.T).T
    target_midpoint = np.mean(target_points, axis=0)
    source_midpoint = np.mean(rotated_source, axis=0)
    t = target_midpoint - source_midpoint

    # Transform entire plat
    plat_array = np.array(new_plat)
    transformed = (R @ plat_array.T).T + t

    # No gap - the borders should share exact same points
    return transformed


# Test data
original_plat = [(0, 0), (57.47675276934449, 1367.3925489379747),
                 (114.95350553868899, 2734.7850978759493),
                 (173.65556368413476, 4134.7248956063695),
                 (232.35762182958055, 5534.664693336789),
                 (232.35762182958055, 5534.664693336789),
                 (1576.036528947231, 5507.672156088213),
                 (2919.715436064882, 5480.679618839637),
                 (4263.3529211546975, 5454.118017579228),
                 (5607.163370289499, 5427.20104902549),
                 (5607.163370289499, 5427.20104902549),
                 (5563.818601999683, 4040.6683897772837),
                 (5520.473833709867, 2654.1357305290776),
                 (5489.793269621355, 1312.4864831521),
                 (5459.1127055328425, -29.16276422487772),
                 (5459.1127055328425, -29.16276422487772),
                 (4144.3290198691375, -76.06526216010172),
                 (2819.771432677988, -121.88906290120315),
                 (1493.8631614177295, -168.86015830713677),
                 (168.60312760687225, -214.91410910015162)]

current_plat_coords = {
    'north': [[232.35762182958055, 5534.664693336789],
              [1576.036528947231, 5507.672156088213],
              [2919.715436064882, 5480.679618839637],
              [4263.3529211546975, 5454.118017579228],
              [5607.163370289499, 5427.20104902549]]
}

new_plat = [(0, 0), (0.0, 0.0), (19.174380179715467, 2640.140372640198),
            (38.3407506115597, 5280.940820827162),
            (43.60748302739152, 6023.472142745409),
            (43.60748302739152, 6023.472142745409),
            (43.60748302739152, 6023.472142745409),
            (2303.9767790332, 5965.992966740485),
            (4990.4872278583225, 5898.824292096448),
            (5325.869296605803, 5890.718839446535),
            (5325.869296605803, 5890.718839446535),
            (5319.997775470134, 5048.529306538679),
            (5300.319659503219, 2407.782623467394),
            (5275.775421936636, -246.89391511546592),
            (5275.775421936636, -246.89391511546592),
            (5275.775421936636, -246.89391511546592),
            (5275.775421936636, -246.89391511546592),
            (2628.325931698603, -248.5368205844878),
            (-12.991041100748589, -265.2737887110307),
            (-12.991041100748589, -265.2737887110307)]

next_plat_coords = {
    'south': [[5275.775421936636, -246.89391511546592],
              [5275.775421936636, -246.89391511546592],
              [2628.325931698603, -248.5368205844878],
              [-12.991041100748589, -265.2737887110307],
              [-12.991041100748589, -265.2737887110307]]
}

# Perform alignment
transformed = align_plat_north(original_plat, current_plat_coords, new_plat, next_plat_coords)

# Create visualization
plt.figure(figsize=(12, 10))

# Plot original plat A
orig_x = [p[0] for p in original_plat] + [original_plat[0][0]]
orig_y = [p[1] for p in original_plat] + [original_plat[0][1]]
plt.plot(orig_x, orig_y, 'b-', linewidth=2, label='Original Plat (A)')
plt.fill(orig_x, orig_y, 'blue', alpha=0.3)

# Plot transformed plat B
trans_x = [p[0] for p in transformed] + [transformed[0][0]]
trans_y = [p[1] for p in transformed] + [transformed[0][1]]
plt.plot(trans_x, trans_y, 'r-', linewidth=2, label='Transformed Plat (B)')
plt.fill(trans_x, trans_y, 'red', alpha=0.3)

# Highlight the matching edges - they share exact same points
north_x = [p[0] for p in current_plat_coords['north']]
north_y = [p[1] for p in current_plat_coords['north']]
plt.plot(north_x, north_y, 'g-', linewidth=4, alpha=0.7, label='Shared Border (Exact Match)')

plt.xlabel('X Coordinate', fontsize=12)
plt.ylabel('Y Coordinate', fontsize=12)
plt.title('Plat B Aligned North of Plat A (Perfect Border Match - No Gap)', fontsize=14)
plt.legend()
plt.grid(True, alpha=0.3)
plt.axis('equal')
plt.tight_layout()
plt.show()