from .main.views import main_bp
from .source.views import source_bp
from .chemical.views import chemical_bp
from .treatment_record.views import treatment_record_bp
from .storage_tank.views import storage_tank_bp
from .service_area.views import service_area_bp
from .pipeline.views import pipeline_bp
blueprint_list = [main_bp , source_bp , chemical_bp , treatment_record_bp , storage_tank_bp  , service_area_bp , pipeline_bp ]