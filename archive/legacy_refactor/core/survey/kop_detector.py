"""
Kick-Off Point (KOP) detection for EToolsV3.

This module provides multiple methods for detecting the kick-off point
in directional drilling surveys.
"""

from typing import Optional
import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from data.models.survey import KOPDetectionResult
from config.logging_config import get_logger
from config.settings import settings

logger = get_logger(__name__)


class KOPDetector:
    """Detects kick-off point using multiple methods and consensus."""

    def __init__(self, inclination_threshold: float = 3.0):
        """
        Initialize KOP detector.

        Args:
            inclination_threshold: Minimum inclination to consider as KOP (degrees).
        """
        self.inclination_threshold = inclination_threshold
        self.logger = logger

    def detect(self, survey_df: pd.DataFrame) -> KOPDetectionResult:
        """
        Detect KOP using multiple methods and return consensus.

        Args:
            survey_df: Survey DataFrame with measured_depth and inclination columns.

        Returns:
            KOPDetectionResult with best estimate and all candidates.
        """
        candidates = {}

        # Method 1: First deviation
        kop_first = self._method_first_deviation(survey_df)
        if kop_first is not None:
            candidates['first_deviation'] = kop_first

        # Method 2: Rate of change
        kop_roc = self._method_rate_of_change(survey_df)
        if kop_roc is not None:
            candidates['rate_of_change'] = kop_roc

        # Method 3: Moving average
        kop_ma = self._method_moving_average(survey_df)
        if kop_ma is not None:
            candidates['moving_average'] = kop_ma

        # Method 4: Curvature-based
        kop_curv = self._method_curvature(survey_df)
        if kop_curv is not None:
            candidates['curvature'] = kop_curv

        # Get consensus
        if not candidates:
            # No KOP detected, return surface
            return KOPDetectionResult(
                measured_depth=0.0,
                tvd=0.0,
                inclination=0.0,
                confidence=0.0,
                method='none',
                candidates={}
            )

        # Use median of all methods as consensus
        consensus_md = np.median(list(candidates.values()))

        # Find closest survey point to consensus
        idx = (survey_df['measured_depth'] - consensus_md).abs().idxmin()
        kop_row = survey_df.loc[idx]

        # Calculate confidence based on agreement
        std_dev = np.std(list(candidates.values()))
        max_deviation = max(candidates.values()) - min(candidates.values())
        confidence = 1.0 - min(max_deviation / consensus_md, 1.0) if consensus_md > 0 else 0.5

        self.logger.info(
            f"KOP detected at MD={consensus_md:.1f} ft, "
            f"Confidence={confidence:.2f}, "
            f"Methods: {list(candidates.keys())}"
        )

        return KOPDetectionResult(
            measured_depth=kop_row['measured_depth'],
            tvd=kop_row.get('tvd', 0.0),
            inclination=kop_row['inclination'],
            confidence=confidence,
            method='consensus',
            candidates=candidates
        )

    def _method_first_deviation(self, survey_df: pd.DataFrame) -> Optional[float]:
        """Find first point where inclination exceeds threshold."""
        mask = survey_df['inclination'] > self.inclination_threshold
        if mask.any():
            return survey_df[mask]['measured_depth'].iloc[0]
        return None

    def _method_rate_of_change(self, survey_df: pd.DataFrame) -> Optional[float]:
        """Find point with maximum rate of inclination change."""
        if len(survey_df) < 3:
            return None

        # Calculate rate of change
        inc_diff = survey_df['inclination'].diff()
        md_diff = survey_df['measured_depth'].diff()
        rate = inc_diff / md_diff

        # Find peak rate (excluding first point)
        max_idx = rate[1:].idxmax()
        return survey_df.loc[max_idx, 'measured_depth']

    def _method_moving_average(self, survey_df: pd.DataFrame, window: int = 5) -> Optional[float]:
        """Use moving average to smooth and detect KOP."""
        if len(survey_df) < window:
            return None

        # Calculate moving average of inclination
        ma = survey_df['inclination'].rolling(window=window, center=True).mean()

        # Find first point where MA exceeds threshold
        mask = ma > self.inclination_threshold
        if mask.any():
            return survey_df[mask]['measured_depth'].iloc[0]
        return None

    def _method_curvature(self, survey_df: pd.DataFrame) -> Optional[float]:
        """Detect using second derivative (curvature)."""
        if len(survey_df) < 3:
            return None

        # Calculate second derivative of inclination
        first_deriv = survey_df['inclination'].diff() / survey_df['measured_depth'].diff()
        second_deriv = first_deriv.diff()

        # Find peaks in second derivative
        peaks, _ = find_peaks(second_deriv.fillna(0), height=0)

        if len(peaks) > 0:
            # Return first significant peak
            peak_idx = peaks[0]
            return survey_df.iloc[peak_idx]['measured_depth']

        return None
