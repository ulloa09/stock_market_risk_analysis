"""
job_manager.py
--------------
Gestor del ciclo de vida de los procesos asíncronos de análisis
crediticio (jobs) ejecutados por la API.

Rol en la arquitectura:
------------------------
Actúa como capa de estado en memoria que permite:
    - Crear identificadores únicos por ejecución.
    - Monitorear progreso del pipeline cuantitativo.
    - Almacenar resultados intermedios y finales.
    - Reportar errores controlados al frontend.

Cada job representa una ejecución completa del análisis:
    - Cálculo Z-Score (Altman)
    - Estimación estructural Merton (DD y PD)
    - Generación de reporte Markdown
    - Conversión a PDF

Persistencia:
-------------
Actualmente en memoria (dict).
En entorno productivo debería reemplazarse por Redis o base de datos.
"""
import uuid
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Any

# Directorio base donde cada job crea su estructura aislada de archivos
_JOBS_BASE_DIR = Path("outputs/jobs")


@dataclass
class Job:
    """
    Representa una unidad de trabajo individual dentro del sistema.

    Atributos:
    ----------
    job_id : str
        Identificador único (UUID).
    status : str
        Estado actual del pipeline.
    progress : str
        Mensaje descriptivo para monitoreo en frontend.
    result : dict | None
        Resultados finales cuando el estado es 'done'.
    error : str | None
        Mensaje descriptivo cuando el estado es 'error'.
    output_dir : Path
        Carpeta aislada donde se almacenan plots y reportes.
    """
    job_id: str
    status: str = "queued"           # queued | running | done | error
    progress: str = "En cola..."
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    output_dir: Path = field(default_factory=Path)

    # Serializa únicamente información relevante para monitoreo
    def to_status_dict(self) -> dict:
        return {
            "job_id":   self.job_id,
            "status":   self.status,
            "progress": self.progress,
            "error":    self.error,
        }


class JobManager:
    """
    Gestor centralizado de todos los jobs activos.

    Funciona como un registry en memoria que permite:
        - Creación de jobs.
        - Consulta por ID.
        - Actualización de estado.
        - Manejo controlado de errores.

    No es thread-safe para escenarios distribuidos.
    Adecuado para despliegues simples o entornos académicos.
    """

    def __init__(self):
        self._jobs: dict[str, Job] = {}

    def create_job(self) -> Job:
        """
        Crea un nuevo job y su estructura de carpetas asociada.

        Estructura generada:
            outputs/jobs/<job_id>/
                ├── plots/
                └── reports/

        Retorna la instancia Job recién creada.
        """
        # Generación de identificador único universal (UUID4)
        job_id = str(uuid.uuid4())
        output_dir = _JOBS_BASE_DIR / job_id
        # Creación de estructura física en disco para aislar resultados
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "plots").mkdir(exist_ok=True)
        (output_dir / "reports").mkdir(exist_ok=True)

        job = Job(job_id=job_id, output_dir=output_dir)
        # Registro del job en memoria
        self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    # Transición de estado: queued → running
    def set_running(self, job_id: str, progress: str = "Procesando...") -> None:
        job = self._get_or_raise(job_id)
        job.status   = "running"
        job.progress = progress

    # Actualización incremental de mensaje de progreso
    def set_progress(self, job_id: str, progress: str) -> None:
        job = self._get_or_raise(job_id)
        job.progress = progress

    # Transición de estado: running → done
    def set_done(self, job_id: str, result: dict) -> None:
        job = self._get_or_raise(job_id)
        job.status   = "done"
        job.progress = "Análisis completado."
        job.result   = result

    # Transición de estado: running → error
    def set_error(self, job_id: str, error: str) -> None:
        job = self._get_or_raise(job_id)
        job.status   = "error"
        job.progress = "Error en el análisis."
        job.error    = error

    # Métod0 interno para validación estricta de existencia del job
    def _get_or_raise(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"Job '{job_id}' no encontrado.")
        return job


# Instancia singleton utilizada por los routers de FastAPI
job_manager = JobManager()