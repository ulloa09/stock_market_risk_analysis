"""
job_manager.py
--------------
Gestiona el ciclo de vida de cada análisis (job) lanzado por la API.

Cada job tiene:
    - job_id:     UUID único generado al crear el job
    - status:     "queued" | "running" | "done" | "error"
    - progress:   mensaje de progreso legible para el frontend
    - result:     dict con plot_paths, summary_df, report_path (cuando done)
    - error:      mensaje de error (cuando error)
    - output_dir: Path donde se guardan los archivos de este job

Almacenamiento: dict en memoria (se limpia al reiniciar el servidor).
Para producción se reemplazaría por Redis, pero para este caso es suficiente.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Directorio raíz donde se crean carpetas por job
_JOBS_BASE_DIR = Path("outputs/jobs")


@dataclass
class Job:
    job_id: str
    status: str = "queued"           # queued | running | done | error
    progress: str = "En cola..."
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    output_dir: Path = field(default_factory=Path)

    def to_status_dict(self) -> dict:
        return {
            "job_id":   self.job_id,
            "status":   self.status,
            "progress": self.progress,
            "error":    self.error,
        }


class JobManager:
    """
    Singleton que mantiene todos los jobs activos en memoria.
    Se instancia una vez en api/main.py y se comparte via dependency injection.
    """

    def __init__(self):
        self._jobs: dict[str, Job] = {}

    def create_job(self) -> Job:
        """Crea un nuevo job con UUID único y su directorio de salida."""
        job_id = str(uuid.uuid4())
        output_dir = _JOBS_BASE_DIR / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "plots").mkdir(exist_ok=True)
        (output_dir / "reports").mkdir(exist_ok=True)

        job = Job(job_id=job_id, output_dir=output_dir)
        self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def set_running(self, job_id: str, progress: str = "Procesando...") -> None:
        job = self._get_or_raise(job_id)
        job.status   = "running"
        job.progress = progress

    def set_progress(self, job_id: str, progress: str) -> None:
        job = self._get_or_raise(job_id)
        job.progress = progress

    def set_done(self, job_id: str, result: dict) -> None:
        job = self._get_or_raise(job_id)
        job.status   = "done"
        job.progress = "Análisis completado."
        job.result   = result

    def set_error(self, job_id: str, error: str) -> None:
        job = self._get_or_raise(job_id)
        job.status   = "error"
        job.progress = "Error en el análisis."
        job.error    = error

    def _get_or_raise(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"Job '{job_id}' no encontrado.")
        return job


# Instancia global — importada por las rutas de FastAPI
job_manager = JobManager()