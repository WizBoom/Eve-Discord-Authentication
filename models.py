from app import db
from datetime import datetime
import random

class DiscordUser(db.Model):

	__tablename__ = "discord_users"

	id = db.Column(db.Integer, primary_key=True)
	date = db.Column(db.DateTime, nullable=False)
	character_name = db.Column(db.String, unique=True, nullable = False)
	character_id = db.Column(db.Integer, unique=True, nullable = False)
	corporation_id = db.Column(db.Integer, nullable = False)
	alliance_id = db.Column(db.Integer)
	discord_id = db.Column(db.String, unique=True, nullable = False)
	discord_name= db.Column(db.String, unique=True, nullable = False)
	discord_avatar = db.Column(db.String)
	on_server = db.Column(db.Boolean, nullable = False)

	def __init__(self,character_name,character_id,corporation_id,alliance_id,discord_id,discord_name,discord_avatar,on_server=False):
		self.date = datetime.utcnow()
		self.character_name = character_name
		self.character_id = character_id
		self.corporation_id=corporation_id
		self.alliance_id=alliance_id
		self.discord_id = discord_id
		self.discord_name = discord_name
		self.discord_avatar = discord_avatar
		self.on_server = on_server

	def __repr__(self):
		return '{},{},{},{},{},{},{},{}'.format(self.id,self.date,self.character_name,self.character_id,self.corporation_id,self.alliance_id,self.discord_id,self.discord_name)

class DiscordLinkRemoval(db.Model):

	__tablename__ = "discord_link_removal"

	discord_id = db.Column(db.String, unique=True, nullable = False, primary_key=True)

	def __init__(self, discord_id):
		self.discord_id = discord_id

	def __repre(self):
		return '{}'.format(self.discord_id)