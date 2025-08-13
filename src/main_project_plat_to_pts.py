import pandas as pd
import utm
from geopy.distance import geodesic
import math


def dataConverterPlatToUtm(data):
    """Main conversion function"""
    # Convert DataFrame to list format expected by the functions
    data_list = dataframe_to_list(data)

    # Convert to decimal degrees (azimuths)
    data_converted = convertToDecimal2(data_list)

    # Calculate UTM points
    utm_points = calculate_next_utm_points(data_converted)

    return utm_points, data_converted


def dataframe_to_list(df):
    """Convert DataFrame to list format for processing"""
    data_list = []
    for _, row in df.iterrows():
        if 'bearing' not in row:
            row['bearing'] = use_if_bearing_gone(row)
        data_list.append([
            row['side'],
            row['length'],
            row['degrees'],
            row['minutes'],
            row['seconds'],
            row['bearing'] if 'bearing' in row else '',  # This is the quadrant number (1=NE, 2=SE, 3=SW, 4=NW)
            row['bearing_str'] if 'bearing_str' in row else ''
        ])

    return data_list


def use_if_bearing_gone(row):
    quad = row['bearing_str']
    alignment = {'SE': 1, 'NE': 2, 'SW': 3, 'NW': 4}
    if quad != '':
        return alignment[quad]
    return ""


def convertToDecimal2(data):
    """Convert bearing and distance data to azimuth format"""
    data_converted = []

    for item in data:
        side = item[0]
        distance = float(item[1])
        deg = float(item[2])
        min = float(item[3])
        sec = float(item[4])
        quadrant = int(item[5])  # 1=NE, 2=SE, 3=SW, 4=NW
        bearing_str = item[6] if len(item) > 6 else ''

        # Convert DMS to decimal degrees
        angle = deg + min / 60 + sec / 3600

        # First, convert the bearing to its primary azimuth
        # NE (1): azimuth = angle
        # SE (2): azimuth = 180 - angle
        # SW (3): azimuth = 180 + angle
        # NW (4): azimuth = 360 - angle

        if quadrant == 1 or bearing_str == 'NE':  # NE
            primary_azimuth = angle
        elif quadrant == 2 or bearing_str == 'SE':  # SE
            primary_azimuth = 180 - angle
        elif quadrant == 3 or bearing_str == 'SW':  # SW
            primary_azimuth = 180 + angle
        elif quadrant == 4 or bearing_str == 'NW':  # NW
            primary_azimuth = 360 - angle
        else:
            primary_azimuth = angle

        # Now determine actual direction of travel based on which side we're on
        # For a clockwise traverse starting from SW corner:
        travel_azimuth = determine_travel_direction(side, primary_azimuth)

        data_converted.append([side, distance, travel_azimuth])

    return data_converted


def determine_travel_direction(side, bearing_azimuth):
    """
    Determine actual travel direction for clockwise traverse.
    The bearing gives us the alignment of the line, but we need to determine
    which direction to travel along that line.
    """
    side_lower = side.lower()

    # For clockwise traverse starting at SW corner:
    # - West side: travel NORTH (from S to N)
    # - North side: travel EAST (from W to E)
    # - East side: travel SOUTH (from N to S)
    # - South side: travel WEST (from E to W)

    # A line with bearing azimuth can be traveled in two directions:
    # - Forward: bearing_azimuth
    # - Reverse: (bearing_azimuth + 180) % 360

    if 'west' in side_lower:
        # West side travels north
        # Check if bearing is pointing generally north (315-45 or 135-225)
        if (315 <= bearing_azimuth <= 360) or (0 <= bearing_azimuth <= 45):
            # Bearing already points north, use as-is
            return bearing_azimuth
        else:
            # Bearing points south, reverse it
            return (bearing_azimuth + 180) % 360

    elif 'north' in side_lower:
        # North side travels east
        # Check if bearing is pointing generally east (45-135)
        if 45 <= bearing_azimuth <= 135:
            # Bearing already points east, use as-is
            return bearing_azimuth
        else:
            # Bearing points west, reverse it
            return (bearing_azimuth + 180) % 360

    elif 'east' in side_lower:
        # East side travels south
        # Check if bearing is pointing generally south (135-225)
        if 135 <= bearing_azimuth <= 225:
            # Bearing already points south, use as-is
            return bearing_azimuth
        else:
            # Bearing points north, reverse it
            return (bearing_azimuth + 180) % 360

    elif 'south' in side_lower:
        # South side travels west
        # Check if bearing is pointing generally west (225-315)
        if 225 <= bearing_azimuth <= 315:
            # Bearing already points west, use as-is
            return bearing_azimuth
        else:
            # Bearing points east, reverse it
            return (bearing_azimuth + 180) % 360

    return bearing_azimuth


def reorder_for_traverse(data):
    """Reorder data for clockwise traverse starting from bottom-left corner"""
    # Create a dictionary for easy lookup
    side_dict = {}
    for item in data:
        side_dict[item[0]] = item

    # Clockwise order starting from bottom-left (SW corner)
    # Starting at SW corner, going clockwise:
    traverse_order = [
        'west_down_2', 'west_down_1', 'west_up_1', 'west_up_2',  # West side (S to N)
        'north_left_2', 'north_left_1', 'north_right_1', 'north_right_2',  # North side (W to E)
        'east_up_2', 'east_up_1', 'east_down_1', 'east_down_2',  # East side (N to S)
        'south_right_2', 'south_right_1', 'south_left_1', 'south_left_2'  # South side (E to W)
    ]

    ordered_data = []
    for side_name in traverse_order:
        if side_name in side_dict:
            ordered_data.append(side_dict[side_name])

    return ordered_data


def calculate_next_utm_points(data):
    """Calculate UTM points following the traverse"""
    # Reorder data for proper traverse
    data = reorder_for_traverse(data)

    # Start at origin (0, 0) in local coordinates
    current_x = 0.0
    current_y = 0.0
    points = [(0.0, 0.0)]

    for item in data:
        side, distance, azimuth = item

        # Convert azimuth to radians
        azimuth_rad = math.radians(azimuth)

        # Calculate change in position
        # In surveying: North is +Y, East is +X
        dx = distance * math.sin(azimuth_rad)
        dy = distance * math.cos(azimuth_rad)

        # Update current position
        current_x += dx
        current_y += dy

        points.append((current_x, current_y))


    return points


def calculate_utm_with_geodesic(data, starting_utm=(500000, 5360194.4), zone_number=12, zone_letter='T'):
    """Alternative calculation using geodesic for more accurate long-distance calculations"""
    # Reorder data for proper traverse
    data = reorder_for_traverse(data)

    current_point = starting_utm
    utm_points = [starting_utm]

    for item in data:
        side, distance, azimuth = item

        # Convert feet to meters
        distance_m = distance * 0.3048

        # Convert UTM to lat/lon
        lat, lon = utm.to_latlon(*current_point, zone_number=zone_number, zone_letter=zone_letter)
        start_point = (lat, lon)

        # Calculate destination using geodesic
        destination = geodesic(kilometers=distance_m / 1000).destination(start_point, azimuth)

        # Convert back to UTM
        destination_utm = utm.from_latlon(destination.latitude, destination.longitude)[:2]
        utm_points.append(destination_utm)
        current_point = destination_utm

    # Convert to relative coordinates (feet from origin)
    relative_points = []
    origin = utm_points[0]
    for point in utm_points:
        x_ft = (point[0] - origin[0]) / 0.3048
        y_ft = (point[1] - origin[1]) / 0.3048
        relative_points.append((x_ft, y_ft))

    return relative_points


def check_closure(points, tolerance=1.0):
    """Check if the traverse closes properly"""
    start = points[0]
    end = points[-1]

    closure_error = math.sqrt((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2)


    # Calculate perimeter
    perimeter = 0
    for i in range(len(points) - 1):
        dx = points[i + 1][0] - points[i][0]
        dy = points[i + 1][1] - points[i][1]
        perimeter += math.sqrt(dx * dx + dy * dy)

    # print(f"Relative error: 1:{perimeter / closure_error:.0f}" if closure_error > 0 else "Perfect closure")
    #
    # if closure_error <= tolerance:
    #     return True
    # else:
    #     return False


# Example usage with your data
def process_survey_data(df):
    """Process survey DataFrame and return polygon points"""

    # Method 1: Simple planar calculation (good for small areas)
    points_planar, azimuths = dataConverterPlatToUtm(df)

    # Method 2: Geodesic calculation (more accurate for larger areas)
    # Prepare data for geodesic calculation
    data_list = dataframe_to_list(df)
    data_with_azimuths = convertToDecimal2(data_list)
    points_geodesic = calculate_utm_with_geodesic(data_with_azimuths)

    # Check closure
    # check_closure(points_planar)

    # check_closure(points_geodesic)
    points_geodesic = [list(i) for i in points_geodesic]
    points_planar = [list(i) for i in points_planar]

    return points_planar, points_geodesic


# Debug function to verify azimuth conversions
def debug_bearings(df):
    """Debug function to check bearing conversions"""
    # print("\nBearing Conversion and Travel Direction Debug:")
    # print("-" * 100)
    # print(f"{'Side':<20} {'Bearing Input':<25} {'Primary Azimuth':<15} {'Travel Direction':<15} {'Travel Azimuth':<15}")
    # print("-" * 100)

    data_list = dataframe_to_list(df)

    for item in data_list:
        side = item[0]
        deg = float(item[2])
        min = float(item[3])
        sec = float(item[4])
        quadrant = int(item[5])
        bearing_str = item[6] if len(item) > 6 else ['', 'NE', 'SE', 'SW', 'NW'][quadrant] if quadrant in [1, 2, 3,
                                                                                                           4] else ''

        angle = deg + min / 60 + sec / 3600

        # Calculate primary azimuth
        if quadrant == 1 or bearing_str == 'NE':
            primary_azimuth = angle
        elif quadrant == 2 or bearing_str == 'SE':
            primary_azimuth = 180 - angle
        elif quadrant == 3 or bearing_str == 'SW':
            primary_azimuth = 180 + angle
        elif quadrant == 4 or bearing_str == 'NW':
            primary_azimuth = 360 - angle
        else:
            primary_azimuth = angle

        # Determine travel direction
        travel_azimuth = determine_travel_direction(side, primary_azimuth)

        # Determine cardinal direction for travel
        if 337.5 <= travel_azimuth or travel_azimuth < 22.5:
            travel_dir = "North"
        elif 22.5 <= travel_azimuth < 67.5:
            travel_dir = "Northeast"
        elif 67.5 <= travel_azimuth < 112.5:
            travel_dir = "East"
        elif 112.5 <= travel_azimuth < 157.5:
            travel_dir = "Southeast"
        elif 157.5 <= travel_azimuth < 202.5:
            travel_dir = "South"
        elif 202.5 <= travel_azimuth < 247.5:
            travel_dir = "Southwest"
        elif 247.5 <= travel_azimuth < 292.5:
            travel_dir = "West"
        else:
            travel_dir = "Northwest"

        bearing_input = f"{deg:3.0f}°{min:02.0f}'{sec:02.0f}\" {bearing_str}"
        # print(f"{side:<20} {bearing_input:<25} {primary_azimuth:<15.2f} {travel_dir:<15} {travel_azimuth:<15.2f}")


def visualize_traverse(points):
    """Create a simple visualization of the traverse"""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 10))

    # Extract x and y coordinates
    x_coords = [p[0] for p in points]
    y_coords = [p[1] for p in points]

    # Plot the traverse
    ax.plot(x_coords, y_coords, 'b-', linewidth=2, label='Traverse')
    ax.plot(x_coords, y_coords, 'ro', markersize=5)

    # Mark start/end point
    ax.plot(x_coords[0], y_coords[0], 'go', markersize=10, label='Start/End')

    # Add point labels
    for i, (x, y) in enumerate(points[:-1]):  # Skip the last point (duplicate of first)
        ax.annotate(f'{i}', (x, y), xytext=(5, 5), textcoords='offset points', fontsize=8)

    # Set equal aspect ratio
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    ax.set_xlabel('Easting (feet)')
    ax.set_ylabel('Northing (feet)')
    ax.set_title('Section Survey Traverse')
    ax.legend()

    plt.tight_layout()
    plt.show()

    return fig
