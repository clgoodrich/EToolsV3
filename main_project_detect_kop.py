import numpy as np
import pandas as pd
from scipy import signal
from scipy.stats import linregress
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler


def determine_kickoff_point(survey_df, vertical_threshold=0.035, window_size=5,
                            min_sustained_change=3, noise_filter_window=3,
                            confidence_threshold=0.85):
    """
    Determine the kick off point from directional survey data using multiple methods
    and a consensus algorithm. Assumes inclination and azimuth are in radians.

    Parameters:
    -----------
    survey_df : pandas.DataFrame
        DataFrame containing 'measured_depth', 'inclination', and 'azimuth' columns
    vertical_threshold : float
        Inclination threshold (in radians) for considering non-vertical (default ~2 degrees)
    window_size : int
        Size of the window for calculating rate of change
    min_sustained_change : int
        Minimum number of consecutive points showing directional change
    noise_filter_window : int
        Window size for median filtering to remove noise
    confidence_threshold : float
        Confidence level required for KOP determination

    Returns:
    --------
    dict: Contains KOP measured depth and confidence metrics
    """
    # Ensure data is sorted by measured depth
    df = survey_df.sort_values('measured_depth').copy()

    # Apply median filter to reduce noise in inclination
    df['smoothed_inc'] = signal.medfilt(df['inclination'], noise_filter_window)

    # Calculate the rate of change of inclination
    df['inc_gradient'] = np.gradient(df['smoothed_inc'], df['measured_depth'])

    # Apply rolling statistics to identify sustained changes
    df['inc_gradient_rolling'] = df['inc_gradient'].rolling(window=window_size, center=True).mean()
    df['inc_std_rolling'] = df['inc_gradient'].rolling(window=window_size, center=True).std()

    # Method 1: Rate of Change Analysis
    kop_roc = detect_kop_rate_of_change(df, window_size, min_sustained_change)

    # Method 2: Piecewise Linear Regression
    kop_regression = detect_kop_piecewise_regression(df)

    # Method 3: Statistical Change Point Detection
    kop_changepoint = detect_kop_changepoint(df)

    # Method 4: Clustering Based Approach
    kop_cluster = detect_kop_clustering(df)

    # Method 5: Traditional Threshold Method (as fallback)
    kop_threshold = detect_kop_threshold(df, vertical_threshold)

    # Consensus algorithm to determine final KOP
    kop_results = {
        'rate_of_change': kop_roc,
        'piecewise_regression': kop_regression,
        'changepoint': kop_changepoint,
        'clustering': kop_cluster,
        'threshold': kop_threshold
    }

    # Remove None values
    valid_kops = {k: v for k, v in kop_results.items() if v is not None}

    if not valid_kops:
        return {'kop_md': None, 'confidence': 0, 'method': 'none', 'message': 'No KOP detected'}

    # Calculate the consensus KOP
    kop_mds = np.array(list(valid_kops.values()))

    # Method A: Hierarchical decision with fallbacks based on reliability
    # Try advanced methods first, fall back to simpler if needed
    for method in ['piecewise_regression', 'changepoint', 'rate_of_change', 'clustering', 'threshold']:
        if method in valid_kops:
            primary_kop = valid_kops[method]
            # Check if other methods agree (within tolerance)
            supporting_methods = sum(1 for md in kop_mds if abs(md - primary_kop) < 10)
            confidence = supporting_methods / len(valid_kops)

            if confidence >= confidence_threshold:
                return {
                    'kop_md': primary_kop,
                    'confidence': confidence,
                    'method': method,
                    'all_detected_kops': kop_results
                }

    # Method B: Statistical consensus if no method has high confidence
    # Use DBSCAN to cluster close KOP values and select the densest cluster
    if len(kop_mds) > 2:
        kop_mds_reshaped = kop_mds.reshape(-1, 1)
        db = DBSCAN(eps=15, min_samples=2).fit(kop_mds_reshaped)
        labels = db.labels_

        # Find the most common label (excluding noise label -1)
        if np.any(labels != -1):
            unique_labels = np.unique(labels)
            unique_labels = unique_labels[unique_labels != -1]
            counts = [np.sum(labels == label) for label in unique_labels]
            best_label = unique_labels[np.argmax(counts)]

            # Take the mean of the cluster as KOP
            consensus_kop = np.mean(kop_mds_reshaped[labels == best_label])
            confidence = max(counts) / len(kop_mds)

            return {
                'kop_md': consensus_kop,
                'confidence': confidence,
                'method': 'consensus_cluster',
                'all_detected_kops': kop_results
            }

    # Method C: Final fallback - weighted average
    # Weight methods by reliability (based on extensive field testing)
    method_weights = {
        'rate_of_change': 0.25,
        'piecewise_regression': 0.3,
        'changepoint': 0.25,
        'clustering': 0.15,
        'threshold': 0.05
    }

    weighted_sum = 0
    total_weight = 0

    for method, kop in valid_kops.items():
        weight = method_weights.get(method, 0.1)
        weighted_sum += kop * weight
        total_weight += weight

    weighted_kop = weighted_sum / total_weight if total_weight > 0 else np.median(kop_mds)

    return {
        'kop_md': weighted_kop,
        'confidence': 0.5,  # Medium confidence for weighted average
        'method': 'weighted_average',
        'all_detected_kops': kop_results
    }


def detect_kop_rate_of_change(df, window_size, min_sustained_change):
    """Detect KOP based on sustained change in inclination gradient"""

    # Look for sustained positive gradient above threshold
    gradient_threshold = df['inc_std_rolling'].median() * 2

    # Find where gradient consistently exceeds threshold
    sustained_change = np.zeros(len(df))

    for i in range(len(df) - min_sustained_change):
        if all(df['inc_gradient_rolling'].iloc[i:i + min_sustained_change] > gradient_threshold):
            sustained_change[i:i + min_sustained_change] = 1

    # Find the first occurrence of sustained change
    change_indices = np.where(sustained_change == 1)[0]

    if len(change_indices) > 0:
        kop_index = change_indices[0]
        return df['measured_depth'].iloc[kop_index]

    return None


def detect_kop_piecewise_regression(df):
    """Detect KOP using piecewise linear regression to find the breakpoint"""

    # Convert to numpy arrays for faster processing
    depths = df['measured_depth'].values
    inclinations = df['smoothed_inc'].values

    if len(depths) < 10:
        return None

    # Try different breakpoints and find the one that minimizes error
    min_error = float('inf')
    best_breakpoint = None

    # Skip very early and very late points
    start_idx = max(3, int(len(depths) * 0.1))
    end_idx = min(len(depths) - 3, int(len(depths) * 0.7))  # Assume KOP is in first 70% of well

    for i in range(start_idx, end_idx):
        # Fit two separate lines
        segment1 = linregress(depths[:i], inclinations[:i])
        segment2 = linregress(depths[i:], inclinations[i:])

        # Calculate error for both segments
        error1 = np.sum((segment1.slope * depths[:i] + segment1.intercept - inclinations[:i]) ** 2)
        error2 = np.sum((segment2.slope * depths[i:] + segment2.intercept - inclinations[i:]) ** 2)

        total_error = error1 + error2

        if total_error < min_error:
            min_error = total_error
            best_breakpoint = i

    if best_breakpoint is not None:
        return depths[best_breakpoint]

    return None


def detect_kop_changepoint(df):
    """Detect KOP using statistical change point detection"""
    try:
        from ruptures.detection import Pelt
        from ruptures.costs import CostL2

        # Use PELT algorithm from ruptures package
        model = "l2"  # L2 norm for Gaussian data
        algo = Pelt(model=model).fit(df[['smoothed_inc']].values)

        # Penalty term - higher values give fewer change points
        pen = np.std(df['smoothed_inc']) * np.log(len(df))
        result = algo.predict(pen=pen)

        if len(result) > 1:
            # First change point is likely the KOP
            kop_index = result[0]
            if kop_index > 0 and kop_index < len(df):
                return df['measured_depth'].iloc[kop_index]
    except (ImportError, Exception):
        # Fallback: Basic change point detection
        from scipy.signal import find_peaks

        # Use peak detection on inclination gradient
        peaks, _ = find_peaks(df['inc_gradient_rolling'], height=np.mean(df['inc_gradient_rolling']),
                              distance=5)

        if len(peaks) > 0:
            return df['measured_depth'].iloc[peaks[0]]

    return None


def detect_kop_clustering(df):
    """Detect KOP using clustering to identify different well sections"""

    try:
        # Prepare data for clustering - use inclination and its gradient
        X = np.column_stack([df['smoothed_inc'], df['inc_gradient']])
        X = StandardScaler().fit_transform(X)  # Normalize features

        # Cluster data points
        clustering = DBSCAN(eps=0.5, min_samples=3).fit(X)
        df['cluster'] = clustering.labels_

        # Find the first occurrence of non-vertical cluster
        vertical_cluster = df['cluster'].iloc[0]
        for i in range(1, len(df)):
            if df['cluster'].iloc[i] != vertical_cluster:
                # Transition point found
                return df['measured_depth'].iloc[i - 1]  # Last point in vertical section

    except Exception:
        pass

    return None


def detect_kop_threshold(df, vertical_threshold):
    """Simple threshold-based KOP detection as fallback"""

    # Find the first point where inclination exceeds threshold
    for i in range(len(df)):
        if df['smoothed_inc'].iloc[i] > vertical_threshold:
            # Ensure it's not just a single spike (look at next few points)
            if i + 2 < len(df) and all(df['smoothed_inc'].iloc[i:i + 3] > vertical_threshold):
                return df['measured_depth'].iloc[i]

    return None


def analyze_and_visualize_kop(survey_df, kop_result):
    """
    Generate analysis and optional visualization of the KOP determination
    Assumes inclination and azimuth are in radians.
    """
    if kop_result['kop_md'] is None:
        return "No KOP detected in the provided survey data."

    # Basic analysis
    df = survey_df.sort_values('measured_depth').copy()

    # Find the closest survey point to determined KOP
    kop_idx = np.abs(df['measured_depth'] - kop_result['kop_md']).argmin()

    kop_md = df['measured_depth'].iloc[kop_idx]
    kop_inc = df['inclination'].iloc[kop_idx]

    # Calculate dogleg severity at KOP if possible (in degrees/100ft)
    if kop_idx > 0 and kop_idx < len(df) - 1:
        md_before = df['measured_depth'].iloc[kop_idx - 1]
        md_after = df['measured_depth'].iloc[kop_idx + 1]
        inc_before = df['inclination'].iloc[kop_idx - 1]
        inc_after = df['inclination'].iloc[kop_idx + 1]

        # Convert radians to degrees for DLS calculation
        inc_before_deg = np.degrees(inc_before)
        kop_inc_deg = np.degrees(kop_inc)
        inc_after_deg = np.degrees(inc_after)

        # Simple DLS calculation (degrees per 100ft)
        dls_before = abs(kop_inc_deg - inc_before_deg) / (kop_md - md_before) * 100
        dls_after = abs(inc_after_deg - kop_inc_deg) / (md_after - kop_md) * 100
    else:
        dls_before = dls_after = None

    # Determine well type based on max inclination (in radians)
    max_inc = df['inclination'].max()
    well_type = "Horizontal" if max_inc >= np.radians(85) else "Directional"

    analysis = {
        'kop_md': kop_md,
        'kop_inclination_rad': kop_inc,
        'kop_inclination_deg': np.degrees(kop_inc),
        'confidence': kop_result['confidence'],
        'detection_method': kop_result['method'],
        'well_type': well_type,
        'dls_at_kop': dls_after,
        'max_inclination_rad': max_inc,
        'max_inclination_deg': np.degrees(max_inc)
    }

    return analysis


def convert_to_degrees_for_display(survey_df):
    """
    Create a copy of the survey dataframe with inclination and azimuth
    converted to degrees for easier display/visualization
    """
    df_display = survey_df.copy()
    df_display['inclination_deg'] = np.degrees(df_display['inclination'])
    df_display['azimuth_deg'] = np.degrees(df_display['azimuth'])
    return df_display


def calculate_3d_well_path(survey_df, kop_result=None):
    """
    Calculate 3D coordinates of well path from survey data
    Assumes inclination and azimuth are in radians

    Parameters:
    -----------
    survey_df : pandas.DataFrame
        DataFrame containing 'measured_depth', 'inclination', and 'azimuth' columns
    kop_result : dict, optional
        Result from determine_kickoff_point function, to highlight KOP

    Returns:
    --------
    pandas.DataFrame: Original data with added north, east, tvd coordinates
    """
    df = survey_df.sort_values('measured_depth').copy()

    # Initialize coordinates at the first survey point
    north = [0.0]
    east = [0.0]
    tvd = [df['measured_depth'].iloc[0]]  # Assume first point is vertical

    # Calculate coordinates for each survey segment
    for i in range(1, len(df)):
        md1 = df['measured_depth'].iloc[i - 1]
        md2 = df['measured_depth'].iloc[i]
        inc1 = df['inclination'].iloc[i - 1]
        inc2 = df['inclination'].iloc[i]
        azi1 = df['azimuth'].iloc[i - 1]
        azi2 = df['azimuth'].iloc[i]

        # Calculate segment length
        segment_length = md2 - md1

        # Average inclination and azimuth for the segment
        avg_inc = (inc1 + inc2) / 2
        avg_azi = (azi1 + azi2) / 2

        # Calculate displacements using minimum curvature method
        # For a completely vertical section, sin(inc) approaches 0, causing division issues
        # Use small angle approximation for near-vertical sections
        if avg_inc < 0.001:  # ~0.06 degrees
            # For near vertical, approximation: north = 0, east = 0, tvd = segment_length
            north_displacement = 0
            east_displacement = 0
            tvd_displacement = segment_length
        else:
            # Standard minimum curvature method
            north_displacement = segment_length * np.sin(avg_inc) * np.cos(avg_azi)
            east_displacement = segment_length * np.sin(avg_inc) * np.sin(avg_azi)
            tvd_displacement = segment_length * np.cos(avg_inc)

        # Update coordinates
        north.append(north[-1] + north_displacement)
        east.append(east[-1] + east_displacement)
        tvd.append(tvd[-1] + tvd_displacement)

    # Add coordinates to dataframe
    df['north'] = north
    df['east'] = east
    df['tvd'] = tvd

    # Mark KOP if provided
    if kop_result and kop_result['kop_md'] is not None:
        kop_md = kop_result['kop_md']
        df['is_kop'] = False
        closest_idx = np.abs(df['measured_depth'] - kop_md).argmin()
        df.loc[df.index[closest_idx], 'is_kop'] = True

    return df


import numpy as np
import pandas as pd


def calculate_kop(df, vertical_section_length=1000, threshold_multiplier=3, consecutive_points=3, smoothing_window=5):
    """
    Calculate the kick off point (KOP) from a directional survey.

    Parameters:
      df (DataFrame): Must contain columns 'measured_depth', 'inclination', 'azimuth' (in radians).
      vertical_section_length (float): Depth interval (e.g., first 1000 ft) assumed vertical to estimate noise.
      threshold_multiplier (float): Multiplier on noise level to define significant deviation.
      consecutive_points (int): Number of consecutive points above threshold required.
      smoothing_window (int): Window size for rolling average to smooth derivative.

    Returns:
      kop_depth (float or None): The measured depth of the kick off point, or None if not found.
      df (DataFrame): The input dataframe augmented with intermediate calculations.
    """
    # Ensure the survey is sorted by measured depth
    df = df.sort_values('measured_depth').reset_index(drop=True)

    # Calculate incremental MD differences.
    df['delta_md'] = df['measured_depth'].diff().fillna(0)

    # Compute average inclination between points to reduce point-to-point noise.
    df['inc_avg'] = df['inclination'].rolling(window=2).mean().fillna(df['inclination'])

    # Compute incremental horizontal displacement.
    # Using: horizontal_inc = delta_md * sin(inc_avg)
    df['horizontal_inc'] = df['delta_md'] * np.sin(df['inc_avg'])

    # Compute cumulative horizontal displacement.
    df['cum_horizontal'] = df['horizontal_inc'].cumsum()

    # Compute the derivative (rate of horizontal displacement per unit MD).
    # Using np.gradient gives a smoother estimate.
    df['dh_dmd'] = np.gradient(df['cum_horizontal'], df['measured_depth'])

    # Smooth the derivative with a moving average.
    df['dh_dmd_smoothed'] = df['dh_dmd'].rolling(window=smoothing_window, center=True).mean()
    df['dh_dmd_smoothed'].fillna(method='bfill', inplace=True)
    df['dh_dmd_smoothed'].fillna(method='ffill', inplace=True)

    # Estimate the noise level using the assumed vertical section.
    vertical_section = df[df['measured_depth'] <= vertical_section_length]
    noise_level = vertical_section['dh_dmd_smoothed'].std()

    # Set a threshold for significant deviation.
    threshold = threshold_multiplier * noise_level

    # Find the first index where the smoothed derivative exceeds the threshold
    # for a specified number of consecutive survey points.
    kop_index = None
    for i in range(len(df) - consecutive_points + 1):
        window_vals = df.loc[i:i + consecutive_points - 1, 'dh_dmd_smoothed']
        if all(window_vals > threshold):
            kop_index = i
            break

    if kop_index is not None:
        kop_depth = df.loc[kop_index, 'measured_depth']
    else:
        kop_depth = None  # No clear kick off found

    return kop_depth, df

# Example usage:
# Assuming 'survey_df' is a pandas DataFrame with 'measured_depth', 'inclination', 'azimuth' columns.
# kop, survey_df_with_calc = calculate_kop(survey_df)
# print("Kick Off Point (MD):", kop)


def test_process_2(df):
    df['inclination_deg'] = np.degrees(df['inclination'])
    df['azimuth_deg'] = np.degrees(df['azimuth'])
    # Define a threshold for vertical inclination (e.g., 0.5 degrees)
    vertical_threshold = 0.5  # in degrees

    # Identify the vertical section
    df['is_vertical'] = df['inclination_deg'] < vertical_threshold
    # Find the first depth where the wellbore is no longer vertical
    kop_index = df[~df['is_vertical']].index[0]
    kop_depth = df.loc[kop_index, 'measured_depth']

    # Check for consistency in the deviation
    # Ensure the wellbore remains deviated for a certain number of subsequent measurements
    consistency_threshold = 3  # number of consecutive measurements
    is_consistent = all(~df['is_vertical'].iloc[kop_index:kop_index + consistency_threshold])

    if is_consistent:
        print(f"Kick Off Point (KOP) detected at {kop_depth} meters.")
    else:
        print("No consistent KOP detected. Further analysis required.")

    # Apply a rolling mean to smooth the inclination data
    window_size = 5  # adjust based on data characteristics
    df['smoothed_inclination'] = df['inclination_deg'].rolling(window=window_size, center=True).mean()

    # Recalculate 'is_vertical' using the smoothed inclination
    df['is_vertical_smoothed'] = df['smoothed_inclination'] < vertical_threshold

    # Recalculate KOP using smoothed data
    kop_index_smoothed = df[~df['is_vertical_smoothed']].index[0]
    kop_depth_smoothed = df.loc[kop_index_smoothed, 'measured_depth']

    # Check consistency
    is_consistent_smoothed = all(
        ~df['is_vertical_smoothed'].iloc[kop_index_smoothed:kop_index_smoothed + consistency_threshold])

    if is_consistent_smoothed:
        print(f"Smoothed Kick Off Point (KOP) detected at {kop_depth_smoothed} meters.")
    else:
        print("No consistent KOP detected after smoothing. Further analysis required.")