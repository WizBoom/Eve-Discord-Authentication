from flask import Flask, render_template, url_for, redirect, request, flash, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from preston.esi import Preston
import sqlite3
from datetime import datetime
import random
import requests
import json
import logging
import sys
import os
from requests_oauthlib import OAuth2Session

# config setup
with open('config.json') as f:
    config = json.load(f)

#Create app
app = Flask(__name__, template_folder='templates')
app.config['SQLALCHEMY_DATABASE_URI'] = config['SQLALCHEMY_DATABASE_URI']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.urandom(24)

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
	client_id=config['EVE_CLIENT_ID'],
	client_secret=config['EVE_CLIENT_SECRET'],
	callback_url=config['EVE_CALLBACK_URI']
)
AVATAR_SIZE = 64
API_BASE_URL ='https://discordapp.com/api'
AUTHORIZATION_BASE_URL = API_BASE_URL + "/oauth2/authorize"
TOKEN_URL = API_BASE_URL +"/oauth2/token"

def make_session(token=None, state=None, scope=None):
    return OAuth2Session(
        client_id=config['DISCORD_CLIENT_ID'],
        token=token,
        state=state,
        scope=scope,
        redirect_uri=config['DISCORD_REDIRECT_URI'],
        auto_refresh_kwargs={
            'client_id': config['DISCORD_CLIENT_ID'],
            'client_secret': config['DISCORD_CLIENT_SECRET'],
        },
        auto_refresh_url=TOKEN_URL)

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = 'true'

@app.route('/')
def login():
	"""Shows a user the EVE SSO link so they can log in.
	Args:
		None
	Returns;
	str: rendered template 'login.html'
	"""

	if 'Linked' not in session:
		session['Linked'] = False

	scope = request.args.get('scope','identify')
	discord = make_session(scope=scope.split(' '))
	authorization_url, state = discord.authorization_url(AUTHORIZATION_BASE_URL)
	session['discord_oauth2_state'] = state
	return render_template('login.html',eve_url=preston.get_authorize_url(),discord_url=authorization_url,discord_invite=config['DISCORD_SERVER_INVITE'])

@app.route('/discord/callback')
def callback():
	"""Completes the Discord SSO login. 
	Args:
	None
	Returns:
	None
	"""
	if request.values.get('error'):
		app.logger.error('Error in Discord SSO callback: ' + request.values['error'])
		flash('There was an error in Discord\'s response', 'error')
		return redirect(url_for('login'))
	discord = make_session(state=session.get('oauth2_state'))
	token = discord.fetch_token(
		TOKEN_URL,
		client_secret=config['DISCORD_CLIENT_SECRET'],
		authorization_response=request.url)
	discord = make_session(token=token)
	user = discord.get(API_BASE_URL + '/users/@me').json()

	#Setting session stuff
	session['DiscordName'] = user['username'] + "#" + user['discriminator']
	session['DiscordID'] = user['id']
	if user['avatar'] is not None:
		session['DiscordAvatar'] = get_discord_avatar(user['id'],user['avatar'])

	if user['mfa_enabled'] == False:
		session['FA'] = False

	#See if user already is linked
	character = DiscordUser.query.filter(DiscordUser.discord_id == user['id']).first()
	#If character already exists with a discord id, inform user he is already authenticated
	if character is not None:
		session['Linked'] = True
		session['EveID'] = character.character_id
		session['EveName'] = character.character_name
		session['EveAvatar'] = get_eve_avatar(character.character_id,AVATAR_SIZE)

	return redirect(url_for('login'))

@app.route('/eve/callback')
def eve_oauth_callback():
	"""Completes the EVE SSO login. 
	Args:
	None
	Returns:
	None
	"""
	if 'error' in request.path:
		app.logger.error('Error in EVE SSO callback: ' + request.url)
		flash('There was an error in EVE\'s response', 'error')
		return redirect(url_for('login'))
	try:
		auth = preston.authenticate(request.args['code'])
	except Exception as e:
		app.logger.error('ESI signing error: ' + str(e))
		flash('There was an authentication error signing you in.', 'error')
		return redirect(url_for('login'))
	character_info = auth.whoami()
	character = DiscordUser.query.filter(DiscordUser.character_id == character_info['CharacterID']).first()
	#If character already exists with a discord id, inform user he is already authenticated
	if character is not None:
		session['Linked'] = True
		session['DiscordID'] = character.discord_id
		session['DiscordName'] = character.discord_name
		session['DiscordAvatar'] = character.discord_avatar
		if character.discord_avatar is None:
			session['DiscordAvatar'] = None

	session['EveName'] = character_info['CharacterName']
	session['EveAvatar'] = get_eve_avatar(character_info['CharacterID'],AVATAR_SIZE)
	session['EveID'] = character_info['CharacterID']
	return redirect(url_for('login'))

@app.route('/trapcard')
def remove_auth():
	"""Removes user from the database / logs them out
	Args:
	None
	Returns:
		Login page
	"""
	#DATABASE REMOVAL
	try:
		u = DiscordUser.query.filter(DiscordUser.character_id == session['EveID']).first()
		if not DiscordLinkRemoval.query.filter(DiscordLinkRemoval.discord_id == session['DiscordID']).all():
			db.session.add(DiscordLinkRemoval(session['DiscordID']))

		db.session.delete(u)
		db.session.commit()

	except Exception as e:
		app.logger.error("Failed to remove authentication. " + str(e))
		flash('Failed to remove authentication.', 'error')
		return redirect(url_for('login'))

	if 'EveName' in session:
		session.pop('EveName')

	if 'EveID' in session:
		session.pop('EveID')

	if 'EveAvatar' in session:
		session.pop('EveAvatar')

	if 'DiscordName' in session:
		session.pop('DiscordName')

	if 'DiscordID' in session:
		session.pop('DiscordID')

	if 'DiscordAvatar' in session:
		session.pop('DiscordAvatar')

	if 'Linked' in session:
		session.pop('Linked')

	if 'FA' in session:
		session.pop('FA')

	flash('Succesfully removed authentication.', 'success')
	return redirect(url_for('login'))

@app.route('/link')
def link_to_database():
	"""Links user to the database
	Args:
	None
	Returns:
		Login page
	"""
	if 'EveName' not in session or 'EveID' not in session:
		flash('Not logged into an EvE account.', 'error')
		return redirect(url_for('login')) 
	if 'DiscordName' not in session or 'DiscordID' not in session:
		flash('Not logged into an Discord account.', 'error')
		return redirect(url_for('login')) 
	if session['Linked'] == True:
		flash('Already linked!')
		return redirect(url_for('login'))

	app.logger.info("Making ESI post request to characters/affiliation endpoint with character id " + str(session['EveID']))
	r = requests.post("https://esi.tech.ccp.is/latest/characters/affiliation/?datasource=tranquility", json=[session['EveID']],
		headers = {'Content-Type': 'application/json', 'Accept':'application/json','User-Agent': 'Maintainer: ' + config['MAINTAINER']})
	result = r.json()
	if not result:
		error = "Character ID " + str(session['EveID']) + " is not valid! Message a mentor!"
		flash(error, 'error')
		return redirect(url_for('login')) 

	if 'error' in result:
		#Make different endpoint check
		app.logger.info("ESI Post failed, using names endpoint instead")
		r = requests.get("https://esi.tech.ccp.is/latest/characters/" + str(session['EveID']) + "/?datasource=tranquility", headers={
                    'User-Agent': 'Maintainer: '+ config['MAINTAINER']
                    })
		result = r.json()
		if not result:
			error = "Character ID " + str(session['EveID']) + " is not valid! Message a mentor!"
			flash(error, 'error')
			return redirect(url_for('login')) 
		data = result
	else:
		data = result[0]
	
    #Update corp and alliance in json
	alliance_id = None
	corp_id = data['corporation_id']
	if 'alliance_id' in data:
		alliance_id = data['alliance_id']

	avatar = None
	if 'DiscordAvatar' in session:
		avatar = session['DiscordAvatar']

	user = DiscordUser(session['EveName'],session['EveID'],corp_id,alliance_id,session['DiscordID'],session['DiscordName'],avatar)
	db.session.add(user)
	db.session.commit()
	app.logger.info("Added user " + session['EveName'] + " with Discord " + session['DiscordName'] + "!")
	session['Linked'] = True
	flash('Succesfully linked accounts.', 'success')
	return redirect(url_for('login')) 

def get_eve_avatar(characterID, size):
	"""Retrieves the URL for an eve avatar
	Args:
		int: the character id of the character
		int: the size of the portrait
	Returns:
		str: URL to the avatar
	"""
	return "https://image.eveonline.com/Character/" + str(characterID) + "_" + str(size) + ".jpg"

def get_discord_avatar(accountID,avatarID):
	"""Retrieves the URL for an eve avatar
	Args:
		str: the account id of the discord account
		str: the id of the avatar
	Returns:
		str: URL to the avatar
	"""
	return "https://cdn.discordapp.com/avatars/" + str(accountID) + "/" + str(avatarID) + ".png"

if __name__ == '__main__':
	app.run()
