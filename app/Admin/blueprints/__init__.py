from .main.views import main_bp
from .source.views import source_bp
from .chemical.views import chemical_bp
from .treatment_record.views import treatment_record_bp
from .storage_tank.views import storage_tank_bp
from .service_area.views import service_area_bp
from .pipeline.views import pipeline_bp
from .customer.views import customer_bp
from .meter.views import meter_bp
from .meter_reading.views import meter_reading_bp
from .invoice.views import invoice_bp
from .receipt.views import receipt_bp
from .reports.views import reports_bp
from .staff_account.views import staff_account_bp

blueprint_list = [main_bp, source_bp, chemical_bp, treatment_record_bp, storage_tank_bp, service_area_bp, pipeline_bp, customer_bp, meter_bp, meter_reading_bp, invoice_bp, receipt_bp, reports_bp, staff_account_bp]
