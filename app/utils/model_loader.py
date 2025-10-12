# app/utils/model_loader.py
import pkgutil
import importlib

def import_submodules(package, submodule_name="models"):
    """
    Automatically import <package>.<child>.<submodule_name> for every subpackage.
    Example: import_submodules(app.Admin.blueprints, "models")
    """
    for _, module_name, _ in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
        try:
            importlib.import_module(f"{module_name}.{submodule_name}")
        except ModuleNotFoundError:
            # Skip packages that don’t have models.py
            continue
