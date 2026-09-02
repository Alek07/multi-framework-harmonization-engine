"""UCM-53 - Ask the model what one control presupposes, and screen the answer.

Fails open, per control. A control the model could not be asked about comes back
`UNAVAILABLE` with a notice and an empty premise list, which is exactly what the
catalog already says about every control today — so a partial run degrades into
the status quo rather than into a wrong catalog. The script can then be re-run
for the controls that did not land, and nothing that did is lost.

This service never runs in the request path. It is imported by
`scripts/tag_presuppositions.py` and by its tests, and by nothing else.
"""

from __future__ import annotations

import logging

from pydantic_ai.messages import ModelResponse

from app.catalog.schemas import FrameworkControl
from app.core.exceptions import AppException
from app.parse.ollama import verify_model
from app.tagging.agent import TaggingAgent, tagging_agent
from app.tagging.guard import screen
from app.tagging.prompt import control_sheet, user_prompt
from app.tagging.schemas import ControlProposal, TagStatus

logger = logging.getLogger(__name__)

FAILED_NOTICE = (
    "El modelo no devolvió una lectura válida para este control. Se deja sin premisas, "
    "que es lo que el catálogo ya decía de él."
)


class ControlTaggingService:
    """Proposes what each control presupposes. One call per control, by design."""

    def __init__(self, agent: TaggingAgent | None = None):
        self.agent = agent if agent is not None else tagging_agent()

    async def tag(self, control: FrameworkControl) -> ControlProposal:
        """One control in, one reviewable proposal out. Never raises."""
        try:
            await verify_model()
        except AppException as exc:
            return self._empty(control, TagStatus.UNAVAILABLE, notice=str(exc))

        sheet = control_sheet(control.title, control.paraphrased_description)
        try:
            run = await self.agent.run(user_prompt(sheet))
        except Exception:  # noqa: BLE001 - a failed control must not end the run
            logger.exception("tagging failed for %s", control.id)
            return self._empty(control, TagStatus.UNAVAILABLE, notice=FAILED_NOTICE)

        attempts = sum(1 for message in run.all_messages() if isinstance(message, ModelResponse))
        kept, rejected = screen(
            run.output.presupposes, control.title, control.paraphrased_description
        )

        return ControlProposal(
            control_id=control.id,
            official_id=control.official_id,
            framework=control.framework,
            title=control.title,
            paraphrased_description=control.paraphrased_description,
            presupposes=kept,
            rejected=rejected,
            status=TagStatus.PROPOSED if kept else TagStatus.NONE,
            attempts=attempts,
        )

    @staticmethod
    def _empty(control: FrameworkControl, status: TagStatus, notice: str) -> ControlProposal:
        return ControlProposal(
            control_id=control.id,
            official_id=control.official_id,
            framework=control.framework,
            title=control.title,
            paraphrased_description=control.paraphrased_description,
            status=status,
            notice=notice,
        )
