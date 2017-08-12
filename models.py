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

	def __init__(self,character_name,character_id,corporation_id,alliance_id,discord_id,discord_name,discord_avatar):
		self.date = datetime.utcnow()
		self.character_name = character_name
		self.character_id = character_id
		self.corporation_id=corporation_id
		self.alliance_id=alliance_id
		self.discord_id = discord_id
		self.discord_name = discord_name
		self.discord_avatar = discord_avatar

	def __repr__(self):
		return '{},{},{},{},{},{},{},{},{}'.format(self.id,self.date,self.character_name,self.character_id,self.corporation_id,self.alliance_id,self.auth_code,self.discord_id,self.discord_name)