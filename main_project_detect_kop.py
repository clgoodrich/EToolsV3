import numpy as np
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
