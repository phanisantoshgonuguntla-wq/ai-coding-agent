from flask import Blueprint, jsonify
import backend.app as main_flask
main_flask.app.register_blueprint(main_flask.bp)