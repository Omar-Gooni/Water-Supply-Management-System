

from .blueprints import blueprint_list 

def register_web_blueprints(app):
    for bp in blueprint_list:
        app.register_blueprint(bp) 
