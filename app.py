from flask import Flask, render_template, url_for, redirect, request, flash
from flask_sqlalchemy import SQLAlchemy
from preston.esi import Preston
import sqlite3
from datetime import datetime
import random
import requests
import json
import logging
import sys

# config setup
with open('config.json') as f:
    config = json.load(f)

#Create app
app = Flask(__name__, template_folder='templates')
app.config['SQLALCHEMY_DATABASE_URI'] = config['SQLALCHEMY_DATABASE_URI']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

#logging setup
app.logger.setLevel(config['LOGGING']['LEVEL']['ALL'])
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(style='{', fmt='{asctime} [{levelname}] {message}', datefmt='%Y-%m-%d %H:%M:%S')
handler.setFormatter(formatter)
handler.setLevel(config['LOGGING']['LEVEL']['CONSOLE'])
app.logger.addHandler(handler)
handler = logging.FileHandler(config['LOGGING']['FILE'])
handler.setFormatter(formatter)
handler.setLevel(config['LOGGING']['LEVEL']['FILE'])
app.logger.addHandler(handler)

#Create sqlalchemy object
db = SQLAlchemy(app)

from models import *

user_agent = 'GETIN Discord Auth app ({})'.format(config['MAINTAINER'])
# EVE CREST API connection
preston = Preston(
	user_agent=user_agent,
	client_id=config['CLIENT_ID'],
	client_secret=config['CLIENT_SECRET'],
	callback_url=config['CALLBACK_URL']
)

AUTH_CODE_LENGTH = 32

@app.route('/')
def login():
	"""Shows a user the EVE SSO link so they can log in.
	Args:
		None
	Returns;
	str: rendered template 'login.html'
	"""
	return render_template('login.html',url=preston.get_authorize_url())

@app.route('/callback')
def eve_oauth_callback():
	"""Completes the EVE SSO login. Here, hr.models.User models
	and hr.models.Member models are created for the user if they don't
	exist and the user is redirected the the page appropriate for their
	access level.
	Args:
	None
	Returns:
	str: redirect to the login endpoint if something failed, join endpoint if
	the user is a new user, or the index endpoint if they're already a member.
	"""
	if 'error' in request.path:
		app.logger.error('Error in EVE SSO callback: ' + request.url)
		flash('There was an error in EVE\'s response', 'error')
		return url_for('login')
	try:
		auth = preston.authenticate(request.args['code'])
	except Exception as e:
		app.logger.error('ESI signing error: ' + str(e))
		flash('There was an authentication error signing you in.', 'error')
		return redirect(url_for('login'))
	character_info = auth.whoami()
	character = DiscordUser.query.filter(DiscordUser.character_id == character_info['CharacterID']).first()
	#If character already exists with a discord id, inform user he is already authenticated, else
	#return his token
	if character is not None:
		if character.discord_id is not None:
			app.logger.info("User tried to authenticate with already authenticated character " + character_info['CharacterName'] + "!")
			return "Already authenticated with " + character_info['CharacterName'] + "! If you did not authenticate with that character, message a mentor!"
		app.logger.info("User retrieved existing auth code of character " + character_info['CharacterName'] + "!")
		#return "!auth " + character.auth_code
		return render_template('discord_auth_code.html',auth_code=character.auth_code)

	#Add character
	user = DiscordUser(character_info['CharacterName'],character_info['CharacterID'])
	db.session.add(user)
	db.session.commit()
	token = user.auth_code
	app.logger.info("Added user " + character_info['CharacterName'] + " with auth token " + token + "!")
	#return "!auth " + token
	return render_template('discord_auth_code.html',auth_code=character.auth_code)

if __name__ == '__main__':
	app.run()
