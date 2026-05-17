"""WCRService — orchestrate WCR data fetch + Excel generation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from etools.config import settings
from etools.core.wcr import generate_wcr_excel
from etools.logging_setup import get_logger
from etools.models import WCRBundle
from etools.repositories import WCRRepository

log = get_logger(__name__)


class WCRService:
    def __init__(self, repo: WCRRepository | None = None) -> None:
        self.repo = repo or WCRRepository()

    def load_bundle(self, api: str, lateral: str = "0000") -> WCRBundle:
        return self.repo.get_bundle(api, lateral)

    def generate(
        self,
        *,
        api: str,
        lateral: str,
        summary_footages: pd.DataFrame,
        bundle: WCRBundle | None = None,
        output_dir: str | Path | None = None,
    ) -> Path:
        bundle = bundle or self.load_bundle(api, lateral)
        target_dir = Path(output_dir) if output_dir else settings.output_dir
        path = generate_wcr_excel(
            wcr_bundle=bundle,
            summary_footages=summary_footages,
            output_dir=target_dir,
        )
        log.info("wcr.generated", path=str(path))
        return path
