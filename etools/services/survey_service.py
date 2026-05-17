"""SurveyService — orchestrates the survey-processing workflow.

Takes the raw surveys and well headers loaded by ``WellService`` and produces
a processed-survey set keyed by ``(citing_type, frame)`` — the same surface
shape the legacy ``drl_df_true_dx`` etc. dictionary exposed.
"""

from __future__ import annotations

from dataclasses import dataclass

from etools.core.survey import detect_kop, detect_landing_point, process_survey
from etools.core.survey.kop import KOPResult
from etools.logging_setup import get_logger
from etools.models import ProcessedSurvey, SurveyFrame, WellHeader

log = get_logger(__name__)


@dataclass(slots=True)
class SurveyResult:
    """Per-citing-type processed output, with KOP/landing annotations."""

    citing_type: str
    header: WellHeader
    frames: dict[SurveyFrame, ProcessedSurvey]
    kop: KOPResult
    landing_md: float | None

    def primary(self, frame: SurveyFrame = SurveyFrame.TRUE) -> ProcessedSurvey:
        return self.frames[frame]


class SurveyService:
    def process(
        self,
        headers: list[WellHeader],
        surveys: dict[str, "object"],
    ) -> dict[str, SurveyResult]:
        """Process every available citing type into both true + grid frames."""
        out: dict[str, SurveyResult] = {}
        for citing_type, raw in surveys.items():
            header = _match_header(headers, citing_type)
            if header.surface_lat is None or header.surface_lon is None:
                log.warning("survey.skip", citing=citing_type, reason="missing SHL coords")
                continue

            frames = process_survey(
                raw,
                surface_lat=header.surface_lat,
                surface_lon=header.surface_lon,
                surface_elevation_ft=header.surface_elevation or 0.0,
                north_reference=header.north_reference,
                citing_type=citing_type,
                api=header.api,
                lateral=header.lateral,
                grid_scale_factor=header.grid_scale_factor,
            )
            kop = detect_kop(frames[SurveyFrame.TRUE].points)
            landing = detect_landing_point(frames[SurveyFrame.TRUE].points, kop_md=kop.md)
            out[citing_type] = SurveyResult(
                citing_type=citing_type,
                header=header,
                frames=frames,
                kop=kop,
                landing_md=landing,
            )
            log.info(
                "survey.process.done",
                citing=citing_type,
                kop_md=kop.md,
                kop_method=kop.method,
                landing_md=landing,
            )
        return out


def _match_header(headers: list[WellHeader], citing_type: str) -> WellHeader:
    """Find the header row whose ``citing_type`` matches the survey we're processing."""
    norm = (citing_type or "").lower()
    for h in headers:
        if (h.citing_type or "").lower() == norm:
            return h
    # Fall back to first header if no exact match (data quality issue, but recoverable).
    return headers[0]
