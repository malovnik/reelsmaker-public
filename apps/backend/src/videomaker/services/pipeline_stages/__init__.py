"""Pipeline stages — фазы выполнения job'а.

Каждая стадия принимает ``PipelineContext`` с заполненными входными и
предыдущими промежуточными артефактами, выполняет свою фазу (stages 1-4
ingest, 5.1-5.10 analysis, 6 render), возвращает обогащённый контекст.

Orchestration — в ``services.pipeline::_run_pipeline_impl``.
"""

from videomaker.services.pipeline_stages.analysis import run_analysis_stage
from videomaker.services.pipeline_stages.ingest import run_ingest_stage
from videomaker.services.pipeline_stages.render import run_render_stage

__all__ = ["run_analysis_stage", "run_ingest_stage", "run_render_stage"]
