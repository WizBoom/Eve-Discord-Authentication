from flask import Flask, render_template, url_for, redirect, request, flash
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

#logging setup
logger = logging.getLogger('discord')
logger.setLevel(config['LOGGING']['LEVEL']['ALL'])
formatter = logging.Formatter(style='{', fmt='{asctime} [{levelname}] {message}', datefmt='%Y-%m-%d %H:%M:%S')
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
handler.setLevel(config['LOGGING']['LEVEL']['CONSOLE'])
logger.addHandler(handler)
handler = logging.FileHandler(config['LOGGING']['FILE'])
handler.setFormatter(formatter)
handler.setLevel(config['LOGGING']['LEVEL']['FILE'])
logger.addHandler(handler)

app = Flask(__name__, template_folder='templates')
user_agent = 'GETIN Discord Auth app ({})'.format(config['MAINTAINER'])
# EVE CREST API connection
preston = Preston(
	user_agent=user_agent,
	client_id=config['CLIENT ID'],
	client_secret=config['CLIENT SECRET'],
	callback_url=config['CALLBACK URL']
)

AUTH_CODE_LENGTH = 32

def get_user_with_character_id(character_id):
	"""
	Retrieve a user with a certain character id
	Args:
		int: character id
	Returns:
		list: users with that char id
	"""
	connection = sqlite3.connect('data.db')
	cursor = connection.cursor()
	cursor.execute('SELECT * FROM discord_users where character_id=?',(character_id,))
	data = cursor.fetchall()
	connection.close()
	if not data:
		return []
	return data

def generate_auth_token_and_insert(character_name,character_id):
	"""
	Generate a auth token
	Args:
		str: character name
		int: character id
	Returns:
		str: auth token
	"""
	time = datetime.utcnow()
	while True:
		ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
		chars=[]
		for i in range(AUTH_CODE_LENGTH):
			chars.append(random.choice(ALPHABET))
		token = str("".join(chars))
		try:
			connection = sqlite3.connect('data.db')
			cursor = connection.cursor()
			cursor.execute('INSERT INTO discord_users VALUES(?,?,?,?,?,?,?,?)', (None,time,character_name,character_id,None, None,token,None))
			data = cursor.fetchall()
			connection.commit()
			connection.close()
			logger.info("Inserted " + character_name + " into the database with auth code " + token)
			return token
		except sqlite3.IntegrityError  as e:
			logger.error("Error on " + str(character_id) + " in generate_auth_token_and_insert(): "  +str(e) + ", auth token: " + token)

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
		#app.logger.error('Error in EVE SSO callback: ' + request.url)
		flash('There was an error in EVE\'s response', 'error')
		return url_for('login')
	try:
		auth = preston.authenticate(request.args['code'])
	except Exception as e:
		logger.error('ESI signing error: ' + str(e))
		flash('There was an authentication error signing you in.', 'error')
		return redirect(url_for('login'))
	character_info = auth.whoami()
	character = get_user_with_character_id(character_info['CharacterID'])
	if len(character) > 0:
		return "Already authenticated with " + character_info['CharacterName'] + "! If you did not authenticate with that character, message a mentor!"

	token = generate_auth_token_and_insert(character_info['CharacterName'],character_info['CharacterID'])
	return "!auth " + token

if __name__ == '__main__':
	app.run()