import pandas as pd
import numpy as np
from scipy import signal
from typing import Optional, Dict, Union, List

# --- Main Analysis Functions ---

def analyze_survey(survey_df: pd.DataFrame) -> Dict[str, Union[str, float, None, Dict]]:
    """
    Performs a complete analysis of well survey data, including well type
    determination, Kickoff Point (KOP) detection, and Landing Point (LP) prediction.

    This function serves as the main entry point for a comprehensive well trajectory analysis.
    It orchestrates calls to determine the well's classification, predict critical
    geometric points (KOP and LP), and calculates key metrics for each section of the well.

    Args:
        survey_df (pd.DataFrame): A DataFrame containing the well survey data.
            Must include 'measured_depth', 'inclination', and 'azimuth' columns.
            'tvd', 'dls', and 'build_rate' are optional but enhance the analysis.

    Returns:
        Dict[str, Union[str, float, None, Dict]]: A dictionary containing a
            comprehensive analysis of the well, including:
            - 'well_type': 'vertical', 'directional', or 'horizontal'.
            - 'kop': A dictionary with KOP details, or None.
            - 'landing_point': A dictionary with LP details, or None.
            - 'max_inclination_deg': The maximum inclination reached in degrees.
            - 'total_depth': The maximum measured depth of the well.
            - 'build_section_length': The calculated length of the build section.
            - 'producing_section_length': The calculated length of the producing section.
            - 'well_geometry': A nested dictionary with geometric analysis of each section.
    """
    well_type = determine_well_type(survey_df)

    # For vertical wells, return a simplified analysis
    if well_type == 'vertical':
        return {
            'well_type': well_type,
            'kop': None,
            'landing_point': None,
            'max_inclination_deg': np.degrees(survey_df['inclination'].max()),
            'total_depth': survey_df['measured_depth'].max(),
            'build_section_length': None,
            'producing_section_length': None
        }

    # Predict KOP and Landing Point for deviated wells
    kop = predict_kickoff_point(survey_df)
    landing_point = predict_landing_point(survey_df, kop_depth=kop['measured_depth'] if kop else None)

    # If LP isn't found with KOP constraint, try again without it
    if not landing_point:
        landing_point = predict_landing_point(survey_df)

    # Calculate the lengths of the build and producing sections
    build_section_length = None
    producing_section_length = None
    if kop and landing_point:
        build_section_length = landing_point['measured_depth'] - kop['measured_depth']
        producing_section_length = survey_df['measured_depth'].max() - landing_point['measured_depth']
    elif kop:
        # If only KOP is found, assume the rest of the well is the build section
        build_section_length = survey_df['measured_depth'].max() - kop['measured_depth']

    result = {
        'well_type': well_type,
        'kop': kop,
        'landing_point': landing_point,
        'max_inclination_deg': np.degrees(survey_df['inclination'].max()),
        'total_depth': survey_df['measured_depth'].max(),
        'build_section_length': build_section_length,
        'producing_section_length': producing_section_length,
        'well_geometry': None
    }

    # Perform detailed geometric analysis if both KOP and LP are found
    if kop and landing_point:
        result['well_geometry'] = _analyze_well_geometry(survey_df, kop, landing_point)

    return result


def predict_kickoff_point(
    survey_df: pd.DataFrame,
    method: str = 'auto',
    dls_threshold: float = 1.5,
    inclination_threshold: float = 0.035,
    min_depth: float = 100,
    smoothing_window: int = 3
) -> Optional[Dict[str, Union[float, str]]]:
    """
    Identifies the Kickoff Point (KOP) in directional or horizontal well survey data.

    The KOP is the depth at which the well begins to intentionally deviate from vertical.
    This function uses one of three methods or an 'auto' mode that tries them in sequence.

    Args:
        survey_df (pd.DataFrame): Survey data with 'measured_depth', 'inclination', 'azimuth'.
        method (str): Detection method: 'auto', 'dls', 'inclination', or 'gradient'.
        dls_threshold (float): Dogleg Severity (DLS) threshold in degrees/100ft.
        inclination_threshold (float): Inclination threshold in radians (approx. 2 degrees).
        min_depth (float): Minimum depth to consider for the KOP to avoid surface deviations.
        smoothing_window (int): Window size for the median filter to reduce signal noise.

    Returns:
        Optional[Dict[str, Union[float, str]]]: A dictionary with KOP details
            ('measured_depth', 'inclination', 'azimuth', 'method_used', 'confidence')
            or None if the well is determined to be vertical or KOP is not found.
    """
    required_cols = ['measured_depth', 'inclination', 'azimuth']
    if missing_cols := [col for col in required_cols if col not in survey_df.columns]:
        raise ValueError(f"Missing required columns: {missing_cols}")

    df = survey_df.copy().sort_values('measured_depth').reset_index(drop=True).dropna(subset=required_cols)

    if len(df) < 3: return None
    if df['inclination'].max() < inclination_threshold: return None # Vertical well

    # Apply a median filter to smooth inclination data and reduce noise
    df['inclination_smooth'] = signal.medfilt(
        df['inclination'],
        kernel_size=min(smoothing_window, len(df))
    ) if smoothing_window > 1 else df['inclination']

    df_filtered = df[df['measured_depth'] >= min_depth].copy()
    if df_filtered.empty:
        df_filtered = df.copy()

    kop_result = None
    if method == 'auto':
        # Attempt detection methods in order of reliability: DLS, Inclination, Gradient
        if 'dls' in df.columns and (kop_result := _detect_kop_dls(df_filtered, dls_threshold)):
            kop_result['method_used'] = 'dls'
        if not kop_result and (kop_result := _detect_kop_inclination(df_filtered, inclination_threshold)):
            kop_result['method_used'] = 'inclination'
        if not kop_result and (kop_result := _detect_kop_gradient(df_filtered, inclination_threshold)):
            kop_result['method_used'] = 'gradient'

    elif method == 'dls' and 'dls' in df.columns:
        if kop_result := _detect_kop_dls(df_filtered, dls_threshold):
            kop_result['method_used'] = 'dls'
    elif method == 'inclination':
        if kop_result := _detect_kop_inclination(df_filtered, inclination_threshold):
            kop_result['method_used'] = 'inclination'
    elif method == 'gradient':
        if kop_result := _detect_kop_gradient(df_filtered, inclination_threshold):
            kop_result['method_used'] = 'gradient'

    return kop_result


def predict_landing_point(
    survey_df: pd.DataFrame,
    kop_depth: Optional[float] = None,
    method: str = 'auto',
    stability_window: int = 5,
    dls_threshold: float = 1.0,
    inclination_stability_threshold: float = 0.02
) -> Optional[Dict[str, Union[float, str]]]:
    """
    Predicts the Landing Point (LP) where the well transitions from the build
    section to the final producing section.

    The LP marks the end of the build-up phase, where the well path stabilizes
    at the target inclination.

    Args:
        survey_df (pd.DataFrame): The survey data.
        kop_depth (Optional[float]): The known KOP depth to narrow the search area.
        method (str): Detection method: 'auto', 'dls_stability',
            'inclination_stability', 'target_reached'.
        stability_window (int): Window size for rolling stability calculations.
        dls_threshold (float): DLS threshold to define a stable trajectory.
        inclination_stability_threshold (float): Maximum inclination standard
            deviation (in radians) to be considered stable.

    Returns:
        Optional[Dict[str, Union[float, str]]]: A dictionary with LP details or None.
    """
    df = survey_df.copy().sort_values('measured_depth').reset_index(drop=True)
    if kop_depth:
        df = df[df['measured_depth'] >= kop_depth].copy()

    if len(df) < stability_window: return None

    df['inclination_smooth'] = signal.medfilt(df['inclination'], kernel_size=min(3, len(df)))
    well_type = determine_well_type(survey_df)
    lp_result = None

    if method == 'auto':
        # Try methods based on well type and data availability
        if well_type == 'horizontal' and (lp_result := _detect_lp_horizontal_target(df, stability_window, inclination_stability_threshold)):
            lp_result['method_used'] = 'horizontal_target'
        if not lp_result and 'dls' in df.columns and (lp_result := _detect_lp_dls_stability(df, stability_window, dls_threshold)):
            lp_result['method_used'] = 'dls_stability'
        if not lp_result and (lp_result := _detect_lp_inclination_stability(df, stability_window, inclination_stability_threshold)):
            lp_result['method_used'] = 'inclination_stability'
        if not lp_result and (lp_result := _detect_lp_gradient_change(df, stability_window)):
            lp_result['method_used'] = 'gradient_change'

    elif method == 'dls_stability' and 'dls' in df.columns:
        if lp_result := _detect_lp_dls_stability(df, stability_window, dls_threshold):
            lp_result['method_used'] = 'dls_stability'
    elif method == 'inclination_stability':
        if lp_result := _detect_lp_inclination_stability(df, stability_window, inclination_stability_threshold):
            lp_result['method_used'] = 'inclination_stability'
    elif method == 'target_reached':
        lp_result = _detect_lp_horizontal_target(df, stability_window, inclination_stability_threshold) if well_type == 'horizontal' else _detect_lp_directional_target(df, stability_window, inclination_stability_threshold)
        if lp_result: lp_result['method_used'] = 'target_reached'

    return lp_result


def determine_well_type(survey_df: pd.DataFrame) -> str:
    """
    Determines if a well is vertical, directional, or horizontal based on inclination.

    Args:
        survey_df (pd.DataFrame): Survey data with an 'inclination' column (in radians).

    Returns:
        str: 'vertical', 'directional', 'horizontal', or 'unknown'.
    """
    if 'inclination' not in survey_df.columns: return 'unknown'

    max_inc_deg = np.degrees(survey_df['inclination'].max())
    final_inc_deg = np.degrees(survey_df['inclination'].iloc[-1])

    if max_inc_deg < 5: return 'vertical'
    if final_inc_deg > 80: return 'horizontal'
    return 'directional'


# --- Internal Helper Functions ---

def _analyze_well_geometry(
    survey_df: pd.DataFrame,
    kop: Dict[str, Union[float, str]],
    landing_point: Dict[str, Union[float, str]]
) -> Dict[str, Dict]:
    """
    Analyzes and calculates geometric properties for the vertical, build, and
    producing sections of a well. This is an internal function called by analyze_survey.

    Args:
        survey_df (pd.DataFrame): The full survey dataset.
        kop (Dict): The Kickoff Point data dictionary.
        landing_point (Dict): The Landing Point data dictionary.

    Returns:
        Dict[str, Dict]: A nested dictionary with geometric details for each section.
    """
    df = survey_df.copy()
    kop_depth = kop['measured_depth']
    lp_depth = landing_point['measured_depth']

    # Define data slices for each well section
    vertical_section = df[df['measured_depth'] <= kop_depth]
    build_section = df[(df['measured_depth'] > kop_depth) & (df['measured_depth'] <= lp_depth)]
    producing_section = df[df['measured_depth'] > lp_depth]

    geometry = {
        'vertical_section': {
            'length': kop_depth,
            'tvd': vertical_section['tvd'].iloc[-1] if 'tvd' in df.columns and not vertical_section.empty else None
        },
        'build_section': {
            'length': lp_depth - kop_depth,
            'inclination_change': np.degrees(landing_point['inclination'] - kop['inclination']),
            'avg_build_rate': build_section['build_rate'].mean() if 'build_rate' in df.columns and not build_section.empty else None,
            'avg_dls': build_section['dls'].mean() if 'dls' in df.columns and not build_section.empty else None
        },
        'producing_section': {
            'length': df['measured_depth'].max() - lp_depth,
            'avg_inclination': np.degrees(producing_section['inclination'].mean()) if not producing_section.empty else None,
            'inclination_stability': np.degrees(producing_section['inclination'].std()) if not producing_section.empty else None
        }
    }
    return geometry


def _detect_kop_dls(df: pd.DataFrame, dls_threshold: float) -> Optional[Dict[str, float]]:
    """
    Detects KOP by finding the first point where Dogleg Severity (DLS)
    exceeds a specified threshold. For internal use.

    Args:
        df (pd.DataFrame): The filtered and sorted survey data.
        dls_threshold (float): The DLS value that indicates intentional deviation.

    Returns:
        Optional[Dict[str, float]]: KOP data or None if not found.
    """
    if 'dls' not in df.columns: return None
    if not (high_dls_points := df[df['dls'] > dls_threshold]).empty:
        kop_row = high_dls_points.iloc[0]
        confidence = min(1.0, kop_row['dls'] / (dls_threshold * 2))
        return {
            'measured_depth': float(kop_row['measured_depth']),
            'inclination': float(kop_row['inclination']),
            'azimuth': float(kop_row['azimuth']),
            'confidence': confidence
        }
    return None


def _detect_kop_inclination(df: pd.DataFrame, inc_threshold: float) -> Optional[Dict[str, float]]:
    """
    Detects KOP by finding the first point where inclination exceeds a
    threshold. For internal use.

    Args:
        df (pd.DataFrame): The filtered and sorted survey data.
        inc_threshold (float): The inclination (in radians) that indicates deviation.

    Returns:
        Optional[Dict[str, float]]: KOP data or None if not found.
    """
    if not (deviated_points := df[df['inclination_smooth'] > inc_threshold]).empty:
        kop_row = df.loc[deviated_points.index[0]]
        confidence = min(1.0, kop_row['inclination'] / (inc_threshold * 3))
        return {
            'measured_depth': float(kop_row['measured_depth']),
            'inclination': float(kop_row['inclination']),
            'azimuth': float(kop_row['azimuth']),
            'confidence': confidence
        }
    return None


def _detect_kop_gradient(df: pd.DataFrame, inc_threshold: float) -> Optional[Dict[str, float]]:
    """
    Detects KOP by analyzing the gradient of the inclination, identifying where
    it shows a sustained increase. For internal use.

    Args:
        df (pd.DataFrame): The filtered and sorted survey data.
        inc_threshold (float): Base inclination threshold to derive a gradient threshold.

    Returns:
        Optional[Dict[str, float]]: KOP data or None if not found.
    """
    if len(df) < 3: return None
    df['inc_gradient'] = np.gradient(df['inclination_smooth'], df['measured_depth'])
    df['inc_gradient_smooth'] = df['inc_gradient'].rolling(window=min(5, len(df) // 3), center=True).mean()

    gradient_threshold = inc_threshold / 1000 # Convert to a per-foot basis
    if not (positive_gradient := df[df['inc_gradient_smooth'] > gradient_threshold]).empty:
        kop_row = df.loc[positive_gradient.index[0]]
        confidence = min(1.0, (kop_row['inc_gradient_smooth'] / gradient_threshold) / 3)
        return {
            'measured_depth': float(kop_row['measured_depth']),
            'inclination': float(kop_row['inclination']),
            'azimuth': float(kop_row['azimuth']),
            'confidence': confidence
        }
    return None


def _detect_lp_dls_stability(df: pd.DataFrame, window: int, dls_threshold: float) -> Optional[Dict[str, float]]:
    """
    Detects LP by finding where a high DLS (active building) transitions to a
    consistently low DLS (stable trajectory). For internal use.

    Args:
        df (pd.DataFrame): Survey data post-KOP.
        window (int): Rolling window size for statistics.
        dls_threshold (float): DLS value defining stability.

    Returns:
        Optional[Dict[str, float]]: LP data or None if not found.
    """
    if 'dls' not in df.columns or len(df) < window: return None
    df['dls_rolling_mean'] = df['dls'].rolling(window=window, center=True).mean()
    df['dls_rolling_std'] = df['dls'].rolling(window=window, center=True).std()

    if (high_dls_section := df[df['dls'] > dls_threshold * 1.5]).empty: return None

    search_df = df.loc[high_dls_section.index[-1]:].copy()
    if len(search_df) < window: return None

    stable_dls = search_df[(search_df['dls_rolling_mean'] < dls_threshold) & (search_df['dls_rolling_std'] < dls_threshold * 0.5)]
    if stable_dls.empty: return None

    lp_row = df.loc[stable_dls.index[0]]
    confidence = 1 - min(1.0, lp_row['dls_rolling_std'] / dls_threshold)
    return {
        'measured_depth': float(lp_row['measured_depth']),
        'inclination': float(lp_row['inclination']),
        'azimuth': float(lp_row['azimuth']),
        'confidence': confidence
    }


def _detect_lp_inclination_stability(df: pd.DataFrame, window: int, stability_threshold: float) -> Optional[Dict[str, float]]:
    """
    Detects LP by finding where the inclination itself stabilizes (i.e., has a
    low rate of change and low variability). For internal use.

    Args:
        df (pd.DataFrame): Survey data post-KOP.
        window (int): Rolling window size for statistics.
        stability_threshold (float): Inclination standard deviation for stability.

    Returns:
        Optional[Dict[str, float]]: LP data or None if not found.
    """
    if len(df) < window: return None
    df['inc_gradient'] = np.gradient(df['inclination_smooth'], df['measured_depth'])
    df['inc_stability'] = np.abs(df['inc_gradient']).rolling(window=window, center=True).mean()
    df['inc_std'] = df['inclination_smooth'].rolling(window=window, center=True).std()

    stable_regions = df[(df['inc_stability'] < stability_threshold / 1000) & (df['inc_std'] < stability_threshold) & (df['inclination_smooth'] > np.radians(5))]
    if stable_regions.empty: return None

    lp_row = df.loc[stable_regions.index[0]]
    stability_score = 1 - min(1.0, lp_row['inc_stability'] / (stability_threshold / 1000))
    variation_score = 1 - min(1.0, lp_row['inc_std'] / stability_threshold)
    confidence = (stability_score + variation_score) / 2
    return {
        'measured_depth': float(lp_row['measured_depth']),
        'inclination': float(lp_row['inclination']),
        'azimuth': float(lp_row['azimuth']),
        'confidence': confidence
    }


def _detect_lp_horizontal_target(df: pd.DataFrame, window: int, stability_threshold: float) -> Optional[Dict[str, float]]:
    """
    Detects LP specifically for horizontal wells by finding where the inclination
    reaches ~85-90 degrees and stabilizes. For internal use.

    Args:
        df (pd.DataFrame): Survey data post-KOP.
        window (int): Rolling window size for stability.
        stability_threshold (float): Inclination standard deviation for stability.

    Returns:
        Optional[Dict[str, float]]: LP data or None if not found.
    """
    target_inc, tolerance = np.radians(85), np.radians(5)
    near_target = df[(df['inclination_smooth'] >= target_inc - tolerance) & (df['inclination_smooth'] <= target_inc + tolerance)]
    if near_target.empty:
        max_inc = df['inclination_smooth'].max()
        near_target = df[df['inclination_smooth'] >= max_inc - np.radians(2)]
        if near_target.empty: return None

    if len(near_target) >= window:
        near_target = near_target.copy()
        near_target['inc_std'] = near_target['inclination_smooth'].rolling(window=window, center=True).std()
        if not (stable_target := near_target[near_target['inc_std'] < stability_threshold]).empty:
            lp_row = df.loc[stable_target.index[0]]
            confidence = min(1.0, 1 - abs(lp_row['inclination_smooth'] - target_inc) / tolerance)
            return {
                'measured_depth': float(lp_row['measured_depth']),
                'inclination': float(lp_row['inclination']),
                'azimuth': float(lp_row['azimuth']),
                'confidence': confidence
            }
    # Fallback to first point in target range if no stable point found
    lp_row = near_target.iloc[0]
    return {
        'measured_depth': float(lp_row['measured_depth']),
        'inclination': float(lp_row['inclination']),
        'azimuth': float(lp_row['azimuth']),
        'confidence': 0.7
    }


def _detect_lp_directional_target(df: pd.DataFrame, window: int, stability_threshold: float) -> Optional[Dict[str, float]]:
    """
    Detects LP for directional (non-horizontal) wells by finding the point
    where the inclination first approaches its maximum value. For internal use.

    Args:
        df (pd.DataFrame): Survey data post-KOP.
        window (int): Rolling window size for stability check.
        stability_threshold (float): Inclination standard deviation for stability.

    Returns:
        Optional[Dict[str, float]]: LP data or None if not found.
    """
    max_inc = df['inclination_smooth'].max()
    target_points = df[df['inclination_smooth'] >= max_inc * 0.9]
    if target_points.empty: return None

    lp_idx = target_points.index[0]
    confidence = 0.5
    if lp_idx + window < len(df):
        inc_variation = df.loc[lp_idx:lp_idx + window, 'inclination_smooth'].std()
        confidence = 0.8 if inc_variation < stability_threshold else 0.6

    lp_row = df.loc[lp_idx]
    return {
        'measured_depth': float(lp_row['measured_depth']),
        'inclination': float(lp_row['inclination']),
        'azimuth': float(lp_row['azimuth']),
        'confidence': confidence
    }


def _detect_lp_gradient_change(df: pd.DataFrame, window: int) -> Optional[Dict[str, float]]:
    """
    Detects LP by finding where the inclination gradient, after peaking, drops
    significantly, indicating the end of the build phase. For internal use.

    Args:
        df (pd.DataFrame): Survey data post-KOP.
        window (int): Rolling window size for smoothing the gradient.

    Returns:
        Optional[Dict[str, float]]: LP data or None if not found.
    """
    if len(df) < window * 2: return None
    df['inc_gradient'] = np.gradient(df['inclination_smooth'], df['measured_depth'])
    df['gradient_smooth'] = df['inc_gradient'].rolling(window=window, center=True).mean()

    if (max_gradient := df['gradient_smooth'].max()) <= 0: return None

    gradient_threshold = max_gradient * 0.2
    high_gradient_end = df[df['gradient_smooth'] > gradient_threshold].index
    if len(high_gradient_end) == 0: return None

    search_start = high_gradient_end[-1]
    lp_idx = len(df) - 1 if search_start + window >= len(df) else search_start + window // 2
    lp_row = df.loc[lp_idx]

    confidence = min(1.0, (max_gradient - lp_row['gradient_smooth']) / max_gradient)
    return {
        'measured_depth': float(lp_row['measured_depth']),
        'inclination': float(lp_row['inclination']),
        'azimuth': float(lp_row['azimuth']),
        'confidence': confidence
    }

# def _find_landing_point(df: pd.DataFrame, horizontal_threshold: float = np.radians(85)) -> Optional[Dict]:
#     """Legacy function - use predict_landing_point instead."""
#     return predict_landing_point(df, method='target_reached')


# # --- Example Usage ---
# if __name__ == "__main__":
#     # Create a realistic sample dataset for a horizontal well
#     sample_data = pd.DataFrame({
#         'measured_depth': np.linspace(0, 8000, 160),
#         'inclination': np.concatenate([
#             np.zeros(40),
#             np.linspace(0, np.radians(90), 60),
#             np.full(60, np.radians(88)) + np.random.normal(0, np.radians(0.5), 60)
#         ]),
#         'azimuth': np.full(160, np.radians(45)),
#         'dls': np.concatenate([
#             np.zeros(40),
#             np.full(60, 3.0),
#             np.random.uniform(0.1, 0.5, 60)
#         ])
#     })
#
