import pandas as pd
import numpy as np
from scipy import signal
from typing import Optional, Dict, Union


def predict_kickoff_point(survey_df: pd.DataFrame,
                          method: str = 'auto',
                          dls_threshold: float = 1.5,
                          inclination_threshold: float = 0.035,  # ~2 degrees in radians
                          min_depth: float = 100,
                          smoothing_window: int = 3) -> Optional[Dict[str, Union[float, str]]]:
    """
    Predict the kickoff point (KOP) in directional/horizontal well survey data.

    Args:
        survey_df (pd.DataFrame): Survey data with columns including 'measured_depth', 
                                 'inclination', 'azimuth', 'dls'
        method (str): Detection method - 'auto', 'dls', 'inclination', or 'gradient'
        dls_threshold (float): DLS threshold in degrees/100ft (default: 1.5)
        inclination_threshold (float): Inclination threshold in radians (default: ~2 degrees)
        min_depth (float): Minimum depth to consider for KOP (default: 100 ft)
        smoothing_window (int): Window size for noise reduction (default: 3)

    Returns:
        dict: KOP information with keys 'measured_depth', 'inclination', 'azimuth', 
              'method_used', 'confidence' or None if vertical well
    """

    # Input validation
    required_cols = ['measured_depth', 'inclination', 'azimuth']
    missing_cols = [col for col in required_cols if col not in survey_df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    # Clean and sort data
    df = survey_df.copy()
    df = df.sort_values('measured_depth').reset_index(drop=True)
    df = df.dropna(subset=required_cols)

    if len(df) < 3:
        return None

    # Check if well is vertical (max inclination < threshold)
    max_inclination = df['inclination'].max()
    if max_inclination < inclination_threshold:
        return None  # Vertical well

    # Apply smoothing to reduce noise
    if smoothing_window > 1:
        df['inclination_smooth'] = signal.medfilt(df['inclination'],
                                                  kernel_size=min(smoothing_window, len(df)))
    else:
        df['inclination_smooth'] = df['inclination']

    # Filter to minimum depth
    df_filtered = df[df['measured_depth'] >= min_depth].copy()
    if len(df_filtered) == 0:
        df_filtered = df.copy()

    kop_result = None

    if method == 'auto':
        # Try methods in order of preference
        if 'dls' in df.columns:
            kop_result = _detect_kop_dls(df_filtered, dls_threshold)
            if kop_result:
                kop_result['method_used'] = 'dls'

        if not kop_result:
            kop_result = _detect_kop_inclination(df_filtered, inclination_threshold)
            if kop_result:
                kop_result['method_used'] = 'inclination'

        if not kop_result:
            kop_result = _detect_kop_gradient(df_filtered, inclination_threshold)
            if kop_result:
                kop_result['method_used'] = 'gradient'

    elif method == 'dls' and 'dls' in df.columns:
        kop_result = _detect_kop_dls(df_filtered, dls_threshold)
        if kop_result:
            kop_result['method_used'] = 'dls'

    elif method == 'inclination':
        kop_result = _detect_kop_inclination(df_filtered, inclination_threshold)
        if kop_result:
            kop_result['method_used'] = 'inclination'

    elif method == 'gradient':
        kop_result = _detect_kop_gradient(df_filtered, inclination_threshold)
        if kop_result:
            kop_result['method_used'] = 'gradient'

    return kop_result


def _detect_kop_dls(df: pd.DataFrame, dls_threshold: float) -> Optional[Dict]:
    """Detect KOP using Dogleg Severity method."""
    if 'dls' not in df.columns:
        return None

    # Find first point where DLS exceeds threshold
    high_dls_points = df[df['dls'] > dls_threshold]

    if high_dls_points.empty:
        return None

    kop_idx = high_dls_points.index[0]
    kop_row = df.loc[kop_idx]

    # Calculate confidence based on DLS consistency
    confidence = min(1.0, kop_row['dls'] / (dls_threshold * 2))

    return {
        'measured_depth': float(kop_row['measured_depth']),
        'inclination': float(kop_row['inclination']),
        'azimuth': float(kop_row['azimuth']),
        'confidence': confidence
    }


def _detect_kop_inclination(df: pd.DataFrame, inc_threshold: float) -> Optional[Dict]:
    """Detect KOP using inclination threshold method."""

    # Find first point where inclination exceeds threshold
    deviated_points = df[df['inclination_smooth'] > inc_threshold]

    if deviated_points.empty:
        return None

    kop_idx = deviated_points.index[0]
    kop_row = df.loc[kop_idx]

    # Calculate confidence based on inclination magnitude
    confidence = min(1.0, kop_row['inclination'] / (inc_threshold * 3))

    return {
        'measured_depth': float(kop_row['measured_depth']),
        'inclination': float(kop_row['inclination']),
        'azimuth': float(kop_row['azimuth']),
        'confidence': confidence
    }


def _detect_kop_gradient(df: pd.DataFrame, inc_threshold: float) -> Optional[Dict]:
    """Detect KOP using inclination gradient analysis."""

    if len(df) < 3:
        return None

    # Calculate inclination gradient
    df['inc_gradient'] = np.gradient(df['inclination_smooth'], df['measured_depth'])

    # Find sustained increase in inclination
    window_size = min(5, len(df) // 3)
    df['inc_gradient_smooth'] = df['inc_gradient'].rolling(window=window_size, center=True).mean()

    # Look for first significant positive gradient
    gradient_threshold = inc_threshold / 1000  # Convert to per-foot basis

    positive_gradient = df[df['inc_gradient_smooth'] > gradient_threshold]

    if positive_gradient.empty:
        return None

    kop_idx = positive_gradient.index[0]
    kop_row = df.loc[kop_idx]

    # Calculate confidence based on gradient magnitude and consistency
    gradient_strength = kop_row['inc_gradient_smooth'] / gradient_threshold
    confidence = min(1.0, gradient_strength / 3)

    return {
        'measured_depth': float(kop_row['measured_depth']),
        'inclination': float(kop_row['inclination']),
        'azimuth': float(kop_row['azimuth']),
        'confidence': confidence
    }


def determine_well_type(survey_df: pd.DataFrame) -> str:
    """
    Determine if well is vertical, directional, or horizontal.

    Args:
        survey_df (pd.DataFrame): Survey data

    Returns:
        str: 'vertical', 'directional', or 'horizontal'
    """
    if 'inclination' not in survey_df.columns:
        return 'unknown'

    max_inc_deg = np.degrees(survey_df['inclination'].max())
    final_inc_deg = np.degrees(survey_df['inclination'].iloc[-1])

    if max_inc_deg < 5:
        return 'vertical'
    elif final_inc_deg > 80:
        return 'horizontal'
    else:
        return 'directional'


def analyze_survey(survey_df: pd.DataFrame) -> Dict:
    """
    Complete survey analysis including KOP detection, LP detection, and well type determination.

    Args:
        survey_df (pd.DataFrame): Survey data

    Returns:
        dict: Complete analysis results
    """

    well_type = determine_well_type(survey_df)

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

    # Find KOP
    kop = predict_kickoff_point(survey_df)

    # Find Landing Point
    landing_point = None
    if kop:
        landing_point = predict_landing_point(survey_df, kop_depth=kop['measured_depth'])

    # If no LP found with KOP constraint, try without constraint
    if not landing_point:
        landing_point = predict_landing_point(survey_df)

    # Calculate section lengths
    build_section_length = None
    producing_section_length = None

    if kop and landing_point:
        build_section_length = landing_point['measured_depth'] - kop['measured_depth']
        producing_section_length = survey_df['measured_depth'].max() - landing_point['measured_depth']
    elif kop:
        # If only KOP found, assume rest is build section
        build_section_length = survey_df['measured_depth'].max() - kop['measured_depth']

    result = {
        'well_type': well_type,
        'kop': kop,
        'landing_point': landing_point,
        'max_inclination_deg': np.degrees(survey_df['inclination'].max()),
        'total_depth': survey_df['measured_depth'].max(),
        'build_section_length': build_section_length,
        'producing_section_length': producing_section_length
    }

    # Add well geometry analysis
    if kop and landing_point:
        result['well_geometry'] = _analyze_well_geometry(survey_df, kop, landing_point)

    return result


def _analyze_well_geometry(survey_df: pd.DataFrame, kop: Dict, landing_point: Dict) -> Dict:
    """Analyze the geometric properties of the well sections."""

    df = survey_df.copy()

    # Section definitions
    vertical_section = df[df['measured_depth'] <= kop['measured_depth']]
    build_section = df[
        (df['measured_depth'] > kop['measured_depth']) &
        (df['measured_depth'] <= landing_point['measured_depth'])
        ]
    producing_section = df[df['measured_depth'] > landing_point['measured_depth']]

    geometry = {
        'vertical_section': {
            'length': kop['measured_depth'],
            'tvd': vertical_section['tvd'].iloc[-1] if 'tvd' in df.columns and len(vertical_section) > 0 else None
        },
        'build_section': {
            'length': landing_point['measured_depth'] - kop['measured_depth'],
            'inclination_change': np.degrees(landing_point['inclination'] - kop['inclination']),
            'avg_build_rate': None,
            'avg_dls': None
        },
        'producing_section': {
            'length': df['measured_depth'].max() - landing_point['measured_depth'],
            'avg_inclination': np.degrees(producing_section['inclination'].mean()) if len(producing_section) > 0 else None,
            'inclination_stability': None
        }
    }

    # Calculate build section statistics
    if len(build_section) > 1 and 'build_rate' in df.columns:
        geometry['build_section']['avg_build_rate'] = build_section['build_rate'].mean()

    if len(build_section) > 1 and 'dls' in df.columns:
        geometry['build_section']['avg_dls'] = build_section['dls'].mean()

    # Calculate producing section stability
    if len(producing_section) > 1:
        inc_std = producing_section['inclination'].std()
        geometry['producing_section']['inclination_stability'] = np.degrees(inc_std)

    return geometry


def predict_landing_point(survey_df: pd.DataFrame,
                          kop_depth: Optional[float] = None,
                          method: str = 'auto',
                          stability_window: int = 5,
                          dls_threshold: float = 1.0,
                          inclination_stability_threshold: float = 0.02) -> Optional[Dict[str, Union[float, str]]]:
    """
    Predict the landing point (LP) where the well transitions to producing section.

    Args:
        survey_df (pd.DataFrame): Survey data
        kop_depth (float, optional): Known KOP depth to focus search
        method (str): Detection method - 'auto', 'dls_stability', 'inclination_stability', 'target_reached'
        stability_window (int): Window size for stability analysis
        dls_threshold (float): DLS threshold for stability detection
        inclination_stability_threshold (float): Max inclination variation for stability (radians)

    Returns:
        dict: LP information or None if not found
    """

    df = survey_df.copy()
    df = df.sort_values('measured_depth').reset_index(drop=True)

    # Focus search after KOP if provided
    if kop_depth:
        df = df[df['measured_depth'] >= kop_depth].copy()

    if len(df) < stability_window:
        return None

    # Apply smoothing
    df['inclination_smooth'] = signal.medfilt(df['inclination'],
                                              kernel_size=min(3, len(df)))

    well_type = determine_well_type(survey_df)
    lp_result = None

    if method == 'auto':
        # Try methods based on well type and available data
        if well_type == 'horizontal':
            # For horizontal wells, look for target inclination achievement + stability
            lp_result = _detect_lp_horizontal_target(df, stability_window, inclination_stability_threshold)
            if lp_result:
                lp_result['method_used'] = 'horizontal_target'

        if not lp_result and 'dls' in df.columns:
            lp_result = _detect_lp_dls_stability(df, stability_window, dls_threshold)
            if lp_result:
                lp_result['method_used'] = 'dls_stability'

        if not lp_result:
            lp_result = _detect_lp_inclination_stability(df, stability_window, inclination_stability_threshold)
            if lp_result:
                lp_result['method_used'] = 'inclination_stability'

        if not lp_result:
            lp_result = _detect_lp_gradient_change(df, stability_window)
            if lp_result:
                lp_result['method_used'] = 'gradient_change'

    elif method == 'dls_stability' and 'dls' in df.columns:
        lp_result = _detect_lp_dls_stability(df, stability_window, dls_threshold)
        if lp_result:
            lp_result['method_used'] = 'dls_stability'

    elif method == 'inclination_stability':
        lp_result = _detect_lp_inclination_stability(df, stability_window, inclination_stability_threshold)
        if lp_result:
            lp_result['method_used'] = 'inclination_stability'

    elif method == 'target_reached':
        if well_type == 'horizontal':
            lp_result = _detect_lp_horizontal_target(df, stability_window, inclination_stability_threshold)
        else:
            lp_result = _detect_lp_directional_target(df, stability_window, inclination_stability_threshold)
        if lp_result:
            lp_result['method_used'] = 'target_reached'

    return lp_result


def _detect_lp_dls_stability(df: pd.DataFrame, window: int, dls_threshold: float) -> Optional[Dict]:
    """Detect LP based on DLS dropping and stabilizing (end of aggressive build)."""

    if 'dls' not in df.columns or len(df) < window:
        return None

    # Calculate rolling DLS statistics
    df['dls_rolling_mean'] = df['dls'].rolling(window=window, center=True).mean()
    df['dls_rolling_std'] = df['dls'].rolling(window=window, center=True).std()

    # Look for transition from high DLS (building) to low DLS (stable)
    high_dls_section = df[df['dls'] > dls_threshold * 1.5]  # Active building

    if high_dls_section.empty:
        return None

    # Start looking after the last high DLS point
    search_start_idx = high_dls_section.index[-1]
    search_df = df.loc[search_start_idx:].copy()

    if len(search_df) < window:
        return None

    # Find where DLS becomes consistently low
    stable_dls = search_df[
        (search_df['dls_rolling_mean'] < dls_threshold) &
        (search_df['dls_rolling_std'] < dls_threshold * 0.5)
        ]

    if stable_dls.empty:
        return None

    lp_idx = stable_dls.index[0]
    lp_row = df.loc[lp_idx]

    # Confidence based on DLS stability
    dls_consistency = 1 - min(1.0, lp_row['dls_rolling_std'] / dls_threshold)

    return {
        'measured_depth': float(lp_row['measured_depth']),
        'inclination': float(lp_row['inclination']),
        'azimuth': float(lp_row['azimuth']),
        'confidence': dls_consistency
    }


def _detect_lp_inclination_stability(df: pd.DataFrame, window: int, stability_threshold: float) -> Optional[Dict]:
    """Detect LP based on inclination stabilizing."""

    if len(df) < window:
        return None

    # Calculate inclination change rate and stability
    df['inc_gradient'] = np.gradient(df['inclination_smooth'], df['measured_depth'])
    df['inc_gradient_abs'] = np.abs(df['inc_gradient'])
    df['inc_stability'] = df['inc_gradient_abs'].rolling(window=window, center=True).mean()
    df['inc_std'] = df['inclination_smooth'].rolling(window=window, center=True).std()

    # Find regions where inclination is stable (low gradient and low variation)
    stable_regions = df[
        (df['inc_stability'] < stability_threshold / 1000) &  # Low rate of change
        (df['inc_std'] < stability_threshold) &  # Low variation
        (df['inclination_smooth'] > np.radians(5))  # Not in vertical section
        ]

    if stable_regions.empty:
        return None

    lp_idx = stable_regions.index[0]
    lp_row = df.loc[lp_idx]

    # Confidence based on stability metrics
    stability_score = 1 - min(1.0, lp_row['inc_stability'] / (stability_threshold / 1000))
    variation_score = 1 - min(1.0, lp_row['inc_std'] / stability_threshold)
    confidence = (stability_score + variation_score) / 2

    return {
        'measured_depth': float(lp_row['measured_depth']),
        'inclination': float(lp_row['inclination']),
        'azimuth': float(lp_row['azimuth']),
        'confidence': confidence
    }


def _detect_lp_horizontal_target(df: pd.DataFrame, window: int, stability_threshold: float) -> Optional[Dict]:
    """Detect LP for horizontal wells based on reaching target inclination and stabilizing."""

    target_inc = np.radians(85)  # Target horizontal inclination
    tolerance = np.radians(5)  # Tolerance around target

    # Find points near target inclination
    near_target = df[
        (df['inclination_smooth'] >= target_inc - tolerance) &
        (df['inclination_smooth'] <= target_inc + tolerance)
        ]

    if near_target.empty:
        # Fallback: find maximum inclination area
        max_inc = df['inclination_smooth'].max()
        near_target = df[df['inclination_smooth'] >= max_inc - np.radians(2)]

        if near_target.empty:
            return None

    # Among target points, find the first stable one
    if len(near_target) >= window:
        # Calculate stability in the target region
        near_target = near_target.copy()
        near_target['inc_std'] = near_target['inclination_smooth'].rolling(window=window, center=True).std()

        stable_target = near_target[near_target['inc_std'] < stability_threshold]

        if not stable_target.empty:
            lp_idx = stable_target.index[0]
            lp_row = df.loc[lp_idx]

            # High confidence for horizontal wells reaching target
            target_proximity = 1 - abs(lp_row['inclination_smooth'] - target_inc) / tolerance
            confidence = min(1.0, target_proximity)

            return {
                'measured_depth': float(lp_row['measured_depth']),
                'inclination': float(lp_row['inclination']),
                'azimuth': float(lp_row['azimuth']),
                'confidence': confidence
            }

    # If no stable point found, return first point in target range
    lp_row = near_target.iloc[0]
    confidence = 0.7  # Lower confidence without stability confirmation

    return {
        'measured_depth': float(lp_row['measured_depth']),
        'inclination': float(lp_row['inclination']),
        'azimuth': float(lp_row['azimuth']),
        'confidence': confidence
    }


def _detect_lp_directional_target(df: pd.DataFrame, window: int, stability_threshold: float) -> Optional[Dict]:
    """Detect LP for directional wells based on reaching maximum planned inclination."""

    # Find maximum inclination (likely the target)
    max_inc = df['inclination_smooth'].max()

    # Find first point reaching 90% of maximum inclination
    target_threshold = max_inc * 0.9

    target_points = df[df['inclination_smooth'] >= target_threshold]

    if target_points.empty:
        return None

    # Look for stability after reaching target
    lp_idx = target_points.index[0]

    # Check for stability in subsequent points
    if lp_idx + window < len(df):
        stability_section = df.loc[lp_idx:lp_idx + window]
        inc_variation = stability_section['inclination_smooth'].std()

        if inc_variation < stability_threshold:
            confidence = 0.8
        else:
            confidence = 0.6
    else:
        confidence = 0.5

    lp_row = df.loc[lp_idx]

    return {
        'measured_depth': float(lp_row['measured_depth']),
        'inclination': float(lp_row['inclination']),
        'azimuth': float(lp_row['azimuth']),
        'confidence': confidence
    }


def _detect_lp_gradient_change(df: pd.DataFrame, window: int) -> Optional[Dict]:
    """Detect LP based on significant change in inclination gradient (end of build phase)."""

    if len(df) < window * 2:
        return None

    # Calculate inclination gradient
    df['inc_gradient'] = np.gradient(df['inclination_smooth'], df['measured_depth'])
    df['gradient_smooth'] = df['inc_gradient'].rolling(window=window, center=True).mean()

    # Find where gradient drops significantly (end of building)
    max_gradient = df['gradient_smooth'].max()

    if max_gradient <= 0:
        return None

    # Look for gradient drop to 20% of maximum
    gradient_threshold = max_gradient * 0.2

    # Find the transition point
    high_gradient_end = df[df['gradient_smooth'] > gradient_threshold].index

    if len(high_gradient_end) == 0:
        return None

    # LP is shortly after the last high gradient point
    search_start = high_gradient_end[-1]

    if search_start + window >= len(df):
        lp_idx = len(df) - 1
    else:
        lp_idx = search_start + window // 2

    lp_row = df.loc[lp_idx]

    # Confidence based on gradient change magnitude
    gradient_drop = max_gradient - lp_row['gradient_smooth']
    confidence = min(1.0, gradient_drop / max_gradient)

    return {
        'measured_depth': float(lp_row['measured_depth']),
        'inclination': float(lp_row['inclination']),
        'azimuth': float(lp_row['azimuth']),
        'confidence': confidence
    }


def _find_landing_point(df: pd.DataFrame, horizontal_threshold: float = np.radians(85)) -> Optional[Dict]:
    """Legacy function - use predict_landing_point instead."""
    return predict_landing_point(df, method='target_reached')


# Example usage
if __name__ == "__main__":
    # Example with sample data
    sample_data = pd.DataFrame({
        'measured_depth': np.linspace(0, 8000, 100),
        'inclination': np.concatenate([
            np.zeros(20),  # Vertical section
            np.linspace(0, np.radians(90), 30),  # Build section
            np.full(50, np.radians(88))  # Horizontal section
        ]),
        'azimuth': np.full(100, np.radians(45)),
        'dls': np.concatenate([
            np.zeros(20),
            np.full(30, 2.5),  # High DLS in build
            np.full(50, 0.5)  # Low DLS in horizontal
        ])
    })

    # Analyze the survey
    result = analyze_survey(sample_data)
    print("Survey Analysis Results:")
    print(f"Well Type: {result['well_type']}")

    if result['kop']:
        print(f"KOP Depth: {result['kop']['measured_depth']:.1f} ft")
        print(f"KOP Inclination: {np.degrees(result['kop']['inclination']):.1f}°")
        print(f"Detection Method: {result['kop']['method_used']}")
        print(f"Confidence: {result['kop']['confidence']:.2f}")
    else:
        print("No KOP detected (vertical well)")
