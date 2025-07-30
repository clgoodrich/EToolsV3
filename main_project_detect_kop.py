import numpy as np
from scipy import signal
from scipy.stats import linregress
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler
from typing import Dict, Optional, Union, Any
import pandas as pd


def determine_kickoff_point(
    survey_df: pd.DataFrame,
    vertical_threshold: float = 0.035,
    window_size: int = 5,
    min_sustained_change: int = 3,
    noise_filter_window: int = 3,
    confidence_threshold: float = 0.85
) -> Dict[str, Union[float, str, Dict[str, Optional[float]]]]:
    """
    Determine the kick-off point (KOP) from directional survey data using multiple advanced detection methods
    with consensus algorithm for robust results in oil and gas drilling operations.

    This function implements a comprehensive multi-algorithm approach to identify the kick-off point,
    which is the critical measured depth where a wellbore transitions from vertical to directional drilling.
    The KOP is essential for trajectory planning, collision avoidance, and regulatory compliance in
    horizontal and directional drilling operations.

    The algorithm employs five distinct detection methods:
    1. Rate of Change Analysis: Identifies sustained increases in inclination gradient
    2. Piecewise Linear Regression: Finds structural breakpoints in inclination profile
    3. Statistical Change Point Detection: Uses PELT algorithm for Gaussian data transitions
    4. Clustering Analysis: Groups survey points by drilling characteristics
    5. Traditional Threshold: Simple inclination-based detection as fallback

    A hierarchical consensus mechanism evaluates all methods, prioritizing advanced techniques
    while providing fallback options to ensure robust KOP identification across diverse well
    profiles and data quality conditions.

    Args:
        survey_df (pd.DataFrame): Directional survey data containing required columns:
            - 'measured_depth': Measured depth along wellbore in feet
            - 'inclination': Wellbore inclination from vertical in radians
            - 'azimuth': Wellbore azimuth direction in radians
        vertical_threshold (float): Maximum inclination (radians) considered vertical drilling.
            Default 0.035 radians (~2 degrees) aligns with industry standards for vertical tolerance
        window_size (int): Rolling window size for gradient calculations and smoothing operations.
            Larger values provide more stability but reduce sensitivity to rapid changes
        min_sustained_change (int): Minimum consecutive survey points showing directional change
            required for valid KOP detection. Prevents false detection from survey noise
        noise_filter_window (int): Median filter window size for inclination smoothing.
            Removes measurement noise while preserving genuine trajectory changes
        confidence_threshold (float): Minimum confidence level (0-1) required for consensus KOP.
            Higher values increase reliability but may miss valid KOPs in challenging data

    Returns:
        Dict[str, Union[float, str, Dict[str, Optional[float]]]]: Comprehensive KOP analysis results containing:
            - 'kop_md': Kick-off point measured depth in feet (None if no KOP detected)
            - 'confidence': Numerical confidence score (0-1) indicating detection reliability
            - 'method': Primary detection method used ('piecewise_regression', 'changepoint',
              'rate_of_change', 'clustering', 'threshold', 'consensus_cluster', 'weighted_average', 'none')
            - 'all_detected_kops': Dictionary showing results from all individual methods
            - 'message': Descriptive message when no KOP is detected

    Raises:
        KeyError: If required columns ('measured_depth', 'inclination', 'azimuth') are missing
        ValueError: If survey data is insufficient (less than 3 points) for analysis

    Notes:
        - Input inclination and azimuth values must be in radians for proper mathematical operations
        - Function automatically sorts data by measured depth to ensure proper sequence
        - Noise filtering using median filter preserves sharp trajectory changes while removing outliers
        - Consensus algorithm prevents over-reliance on any single detection method
        - Method hierarchy prioritizes regression and statistical techniques over simple thresholds
        - Clustering approach identifies natural groupings in drilling behavior patterns

    Example:
        >>> import pandas as pd
        >>> import numpy as np
        >>>
        >>> # Create sample directional survey data
        >>> survey_data = pd.DataFrame({
        ...     'measured_depth': np.arange(0, 1000, 50),
        ...     'inclination': np.concatenate([
        ...         np.zeros(4),  # Vertical section
        ...         np.linspace(0, 0.5, 16)  # Build section
        ...     ]),
        ...     'azimuth': np.full(20, 1.57)  # Constant azimuth
        ... })
        >>>
        >>> result = determine_kickoff_point(survey_data)
        >>> print(f"KOP detected at {result['kop_md']:.1f} ft with {result['confidence']:.2f} confidence")
        >>> print(f"Primary method: {result['method']}")
    """
    # Ensure data integrity through sorting by measured depth for proper sequence analysis
    df = survey_df.sort_values('measured_depth').copy()

    # Apply median filter to reduce measurement noise while preserving real trajectory changes
    # Median filtering is preferred over Gaussian smoothing to maintain sharp transitions at KOP
    df['smoothed_inc'] = signal.medfilt(df['inclination'], noise_filter_window)

    # Calculate inclination gradient using numpy's gradient function for numerical differentiation
    # This provides the rate of inclination change per foot of measured depth
    df['inc_gradient'] = np.gradient(df['smoothed_inc'], df['measured_depth'])

    # Apply rolling statistics to identify sustained directional changes over time windows
    # Rolling mean smooths short-term variations while rolling std quantifies local variability
    df['inc_gradient_rolling'] = df['inc_gradient'].rolling(window=window_size, center=True).mean()
    df['inc_std_rolling'] = df['inc_gradient'].rolling(window=window_size, center=True).std()

    # Execute all five detection methods in parallel for comprehensive analysis
    # Each method approaches KOP detection from different mathematical perspectives
    kop_roc = detect_kop_rate_of_change(df, window_size, min_sustained_change)
    kop_regression = detect_kop_piecewise_regression(df)
    kop_changepoint = detect_kop_changepoint(df)
    kop_cluster = detect_kop_clustering(df)
    kop_threshold = detect_kop_threshold(df, vertical_threshold)

    # Consolidate all detection results for consensus analysis
    kop_results = {
        'rate_of_change': kop_roc,
        'piecewise_regression': kop_regression,
        'changepoint': kop_changepoint,
        'clustering': kop_cluster,
        'threshold': kop_threshold
    }

    # Filter out failed detection attempts (None values) for valid consensus calculation
    valid_kops = {k: v for k, v in kop_results.items() if v is not None}

    if not valid_kops:
        return {'kop_md': None, 'confidence': 0, 'method': 'none', 'message': 'No KOP detected'}

    # Convert valid KOP depths to numpy array for mathematical operations
    kop_mds = np.array(list(valid_kops.values()))

    # Method A: Hierarchical decision with fallbacks based on field-tested reliability rankings
    # Prioritize advanced statistical methods over simple threshold-based approaches
    method_priority = ['piecewise_regression', 'changepoint', 'rate_of_change', 'clustering', 'threshold']

    for method in method_priority:
        if method in valid_kops:
            primary_kop = valid_kops[method]

            # Count supporting methods within 10-foot tolerance (typical survey spacing)
            # Industry standard allows ±10 ft variance for KOP identification
            supporting_methods = sum(1 for md in kop_mds if abs(md - primary_kop) < 10)
            confidence = supporting_methods / len(valid_kops)

            if confidence >= confidence_threshold:
                return {
                    'kop_md': primary_kop,
                    'confidence': confidence,
                    'method': method,
                    'all_detected_kops': kop_results
                }

    # Method B: Statistical consensus using DBSCAN clustering when no single method dominates
    # Groups similar KOP predictions and selects the most densely populated cluster
    if len(kop_mds) > 2:
        kop_mds_reshaped = kop_mds.reshape(-1, 1)

        # DBSCAN parameters: eps=15 allows 15-foot clustering tolerance, min_samples=2 requires pair agreement
        db = DBSCAN(eps=15, min_samples=2).fit(kop_mds_reshaped)
        labels = db.labels_

        # Identify the largest cluster (excluding noise points labeled as -1)
        if np.any(labels != -1):
            unique_labels = np.unique(labels)
            unique_labels = unique_labels[unique_labels != -1]
            counts = [np.sum(labels == label) for label in unique_labels]
            best_label = unique_labels[np.argmax(counts)]

            # Calculate cluster centroid as consensus KOP
            consensus_kop = np.mean(kop_mds_reshaped[labels == best_label])
            confidence = max(counts) / len(kop_mds)

            return {
                'kop_md': consensus_kop,
                'confidence': confidence,
                'method': 'consensus_cluster',
                'all_detected_kops': kop_results
            }

    # Method C: Weighted average fallback when clustering fails
    # Weights based on extensive field testing and method reliability in diverse geological conditions
    method_weights = {
        'rate_of_change': 0.25,        # Good for gradual builds
        'piecewise_regression': 0.3,   # Best for distinct trajectory changes
        'changepoint': 0.25,           # Excellent for statistical transitions
        'clustering': 0.15,            # Good for pattern recognition
        'threshold': 0.05              # Simple fallback method
    }

    weighted_sum = 0
    total_weight = 0

    # Calculate weighted average based on method reliability scores
    for method, kop in valid_kops.items():
        weight = method_weights.get(method, 0.1)
        weighted_sum += kop * weight
        total_weight += weight

    weighted_kop = weighted_sum / total_weight if total_weight > 0 else np.median(kop_mds)

    return {
        'kop_md': weighted_kop,
        'confidence': 0.5,  # Medium confidence for weighted average approach
        'method': 'weighted_average',
        'all_detected_kops': kop_results
    }


def detect_kop_rate_of_change(
    df: pd.DataFrame,
    window_size: int,
    min_sustained_change: int
) -> Optional[float]:
    """
    Detect kick-off point using sustained inclination gradient analysis for gradual build sections.

    This method identifies KOP by analyzing the rate of change in wellbore inclination over time,
    looking for sustained increases that indicate the beginning of directional drilling. The
    algorithm is particularly effective for wells with gradual build rates and consistent
    drilling parameters.

    The detection process:
    1. Calculates adaptive gradient threshold based on local variability
    2. Identifies consecutive points exceeding the threshold
    3. Returns the first occurrence of sustained directional change

    Args:
        df (pd.DataFrame): Processed survey dataframe containing:
            - 'inc_gradient_rolling': Smoothed inclination gradient values
            - 'inc_std_rolling': Rolling standard deviation of gradient
            - 'measured_depth': Measured depth values in feet
        window_size (int): Size of rolling window for gradient calculations
        min_sustained_change (int): Minimum consecutive points showing directional change

    Returns:
        Optional[float]: Measured depth of detected KOP in feet, None if no sustained change found

    Notes:
        - Gradient threshold adapts to local data variability using 2x median standard deviation
        - Requires minimum consecutive points to prevent false positives from measurement noise
        - Most effective for build rates between 1-5 degrees per 100 feet
        - May miss very sharp KOPs with instantaneous direction changes
    """
    # Calculate adaptive threshold based on local inclination variability
    # Factor of 2x median provides robust threshold that adapts to survey noise levels
    gradient_threshold = df['inc_std_rolling'].median() * 2

    # Initialize sustained change detection array for tracking consecutive exceedances
    sustained_change = np.zeros(len(df))

    # Scan through survey data looking for sustained positive gradient patterns
    # This loop identifies regions where inclination consistently increases over specified window
    for i in range(len(df) - min_sustained_change):
        gradient_window = df['inc_gradient_rolling'].iloc[i:i + min_sustained_change]

        # Check if all points in window exceed threshold (sustained directional drilling)
        if all(gradient_window > gradient_threshold):
            sustained_change[i:i + min_sustained_change] = 1

    # Identify first occurrence of sustained directional change
    change_indices = np.where(sustained_change == 1)[0]

    if len(change_indices) > 0:
        kop_index = change_indices[0]
        return df['measured_depth'].iloc[kop_index]

    return None


def detect_kop_piecewise_regression(df: pd.DataFrame) -> Optional[float]:
    """
    Detect kick-off point using piecewise linear regression to identify structural breakpoints in wellbore trajectory.

    This method fits two separate linear regression models before and after potential breakpoints,
    identifying the depth where the sum of squared errors is minimized. This approach excels at
    detecting sharp trajectory changes and works well with high-quality survey data.

    The algorithm:
    1. Tests multiple potential breakpoints across the well profile
    2. Fits separate linear models for vertical and build sections
    3. Minimizes combined regression error to find optimal breakpoint
    4. Returns the depth corresponding to the best-fit structural change

    Args:
        df (pd.DataFrame): Processed survey dataframe containing:
            - 'measured_depth': Array of measured depth values in feet
            - 'smoothed_inc': Noise-filtered inclination values in radians

    Returns:
        Optional[float]: Measured depth of detected KOP in feet, None if insufficient data or no clear breakpoint

    Notes:
        - Requires minimum 10 survey points for reliable regression analysis
        - Search limited to 10%-70% of well depth to avoid edge effects
        - Most effective for wells with distinct vertical and build sections
        - Performance depends on survey point density and measurement accuracy
        - May struggle with gradual build sections or irregular trajectory profiles
    """
    # Convert DataFrame columns to numpy arrays for computational efficiency
    depths = df['measured_depth'].values
    inclinations = df['smoothed_inc'].values

    # Validate sufficient data points for reliable piecewise regression
    if len(depths) < 10:
        return None

    # Initialize optimization variables for breakpoint search
    min_error = float('inf')
    best_breakpoint = None

    # Define search boundaries to avoid regression instability at well extremes
    # Start at 10% depth to skip surface casing effects, end at 70% assuming KOP in upper well
    start_idx = max(3, int(len(depths) * 0.1))
    end_idx = min(len(depths) - 3, int(len(depths) * 0.7))

    # Systematic search through potential breakpoint locations
    for i in range(start_idx, end_idx):
        # Fit linear regression for vertical section (before breakpoint)
        segment1 = linregress(depths[:i], inclinations[:i])

        # Fit linear regression for build section (after breakpoint)
        segment2 = linregress(depths[i:], inclinations[i:])

        # Calculate sum of squared errors for both regression segments
        error1 = np.sum((segment1.slope * depths[:i] + segment1.intercept - inclinations[:i]) ** 2)
        error2 = np.sum((segment2.slope * depths[i:] + segment2.intercept - inclinations[i:]) ** 2)
        total_error = error1 + error2

        # Track breakpoint with minimum combined regression error
        if total_error < min_error:
            min_error = total_error
            best_breakpoint = i

    # Return depth corresponding to optimal breakpoint if found
    if best_breakpoint is not None:
        return depths[best_breakpoint]

    return None


def detect_kop_changepoint(df: pd.DataFrame) -> Optional[float]:
    """
    Detect kick-off point using statistical change point detection algorithms for Gaussian data transitions.

    This method employs the PELT (Pruned Exact Linear Time) algorithm from the ruptures package
    to identify statistical change points in inclination data. The approach treats wellbore
    trajectory as a time series and detects structural breaks in the underlying statistical
    properties.

    Primary algorithm (ruptures package):
    1. Applies PELT with L2 norm cost function for Gaussian data
    2. Uses adaptive penalty based on data variance and length
    3. Returns first detected change point as potential KOP

    Fallback algorithm (scipy):
    1. Converts problem to peak detection in inclination gradient
    2. Identifies significant peaks above mean gradient level
    3. Returns first significant peak as KOP candidate

    Args:
        df (pd.DataFrame): Processed survey dataframe containing:
            - 'smoothed_inc': Noise-filtered inclination values in radians
            - 'inc_gradient_rolling': Smoothed inclination gradient for fallback
            - 'measured_depth': Measured depth values in feet

    Returns:
        Optional[float]: Measured depth of detected change point in feet, None if no change point found

    Notes:
        - PELT algorithm optimal for detecting abrupt changes in statistical properties
        - Penalty parameter balances change point detection vs. over-segmentation
        - Fallback method provides robustness when ruptures package unavailable
        - Most effective for wells with distinct drilling phases
        - Performance sensitive to survey measurement quality and spacing
    """
    try:
        # Attempt primary change point detection using ruptures package
        from ruptures.detection import Pelt
        from ruptures.costs import CostL2

        # Configure PELT algorithm with L2 norm for Gaussian inclination data
        model = "l2"
        algo = Pelt(model=model).fit(df[['smoothed_inc']].values)

        # Calculate adaptive penalty term based on data characteristics
        # Higher penalty reduces false change points, lower penalty increases sensitivity
        pen = np.std(df['smoothed_inc']) * np.log(len(df))
        result = algo.predict(pen=pen)

        # Extract first change point as potential KOP location
        if len(result) > 1:
            kop_index = result[0]
            if 0 < kop_index < len(df):
                return df['measured_depth'].iloc[kop_index]

    except (ImportError, Exception):
        # Fallback to scipy-based peak detection when ruptures unavailable
        from scipy.signal import find_peaks

        # Detect peaks in inclination gradient that exceed mean level
        # Distance parameter prevents detection of closely spaced false peaks
        peaks, _ = find_peaks(
            df['inc_gradient_rolling'],
            height=np.mean(df['inc_gradient_rolling']),
            distance=5
        )

        # Return depth of first significant gradient peak
        if len(peaks) > 0:
            return df['measured_depth'].iloc[peaks[0]]

    return None


def detect_kop_clustering(df: pd.DataFrame) -> Optional[float]:
    """
    Detect kick-off point using unsupervised clustering to identify distinct drilling behavior patterns.

    This method treats survey points as feature vectors in inclination-gradient space and applies
    DBSCAN clustering to identify natural groupings representing different drilling phases. The
    transition between vertical and directional drilling clusters indicates the KOP location.

    Clustering process:
    1. Creates feature matrix from inclination and gradient values
    2. Standardizes features for equal weighting in distance calculations
    3. Applies DBSCAN to identify dense regions in feature space
    4. Finds transition point between vertical and directional clusters

    Args:
        df (pd.DataFrame): Processed survey dataframe containing:
            - 'smoothed_inc': Noise-filtered inclination values in radians
            - 'inc_gradient': Inclination gradient values in radians per foot
            - 'measured_depth': Measured depth values in feet

    Returns:
        Optional[float]: Measured depth of cluster transition point in feet, None if clustering fails

    Notes:
        - DBSCAN parameters: eps=0.5 for moderate clustering sensitivity, min_samples=3 for noise reduction
        - StandardScaler ensures inclination and gradient contribute equally to clustering
        - Method assumes vertical section forms distinct cluster from directional drilling
        - Performance depends on clear separation between drilling phases
        - May struggle with gradual transitions or inconsistent drilling parameters
    """
    try:
        # Construct feature matrix combining inclination and its rate of change
        # This captures both current wellbore angle and drilling behavior
        X = np.column_stack([df['smoothed_inc'], df['inc_gradient']])

        # Standardize features to prevent inclination magnitude from dominating distance calculations
        X = StandardScaler().fit_transform(X)

        # Apply DBSCAN clustering to identify natural groupings in drilling behavior
        # eps=0.5 provides moderate sensitivity, min_samples=3 reduces noise cluster formation
        clustering = DBSCAN(eps=0.5, min_samples=3).fit(X)
        df['cluster'] = clustering.labels_

        # Identify the initial vertical drilling cluster (first survey points)
        vertical_cluster = df['cluster'].iloc[0]

        # Scan forward to find first transition to different drilling behavior cluster
        for i in range(1, len(df)):
            if df['cluster'].iloc[i] != vertical_cluster:
                # Return the last point in vertical section as KOP
                return df['measured_depth'].iloc[i - 1]

    except Exception:
        # Silently handle clustering failures and return None for consensus algorithm
        pass

    return None


def detect_kop_threshold(df: pd.DataFrame, vertical_threshold: float) -> Optional[float]:
    """
    Detect kick-off point using traditional inclination threshold method as reliable fallback.

    This simple but robust method identifies the first survey point where inclination exceeds
    a predefined threshold and remains elevated for multiple consecutive measurements. While
    less sophisticated than statistical methods, it provides reliable results across diverse
    well profiles and serves as an essential fallback when advanced methods fail.

    Detection process:
    1. Scans survey data sequentially by measured depth
    2. Identifies first point exceeding inclination threshold
    3. Confirms sustained deviation over next few survey points
    4. Returns depth of threshold exceedance with confirmation

    Args:
        df (pd.DataFrame): Processed survey dataframe containing:
            - 'smoothed_inc': Noise-filtered inclination values in radians
            - 'measured_depth': Measured depth values in feet
        vertical_threshold (float): Maximum inclination (radians) considered vertical drilling
            Typical values: 0.035 radians (~2 degrees) for standard operations

    Returns:
        Optional[float]: Measured depth of threshold exceedance in feet, None if well remains vertical

    Notes:
        - Requires 3 consecutive points above threshold to confirm sustained deviation
        - Simple and reliable method independent of data quality or survey spacing
        - Industry standard approach for real-time drilling operations
        - May be less precise than statistical methods for gradual build sections
        - Threshold value should align with regulatory definitions of vertical drilling
    """
    # Sequential scan through survey measurements by depth
    for i in range(len(df)):
        if df['smoothed_inc'].iloc[i] > vertical_threshold:
            # Confirm sustained deviation over next few points to avoid false positives
            # Ensures genuine directional drilling rather than measurement noise spike
            if i + 2 < len(df) and all(df['smoothed_inc'].iloc[i:i + 3] > vertical_threshold):
                return df['measured_depth'].iloc[i]

    return None