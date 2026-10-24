import os
import shutil

from dotenv import load_dotenv
from prometheus_client import CollectorRegistry, multiprocess

load_dotenv()

prom_dir = os.getenv("PROMETHEUS_MULTIPROC_DIR")
if prom_dir is not None:
    shutil.rmtree(prom_dir, ignore_errors=True)
    os.makedirs(prom_dir, exist_ok=True)
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
