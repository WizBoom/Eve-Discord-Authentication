from app import db
from datetime import datetime
import random


def generate_unique_auth_token(code_length):
	while True:
		ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
		chars=[]
		for i in range(code_length):
			chars.append(random.choice(ALPHABET))
		token = str("".join(chars))
		q = db.session.query(DiscordUser).filter(DiscordUser.auth_code == token)
		exists = db.session.query(q.exists()).scalar()
		if not exists:
			return token

class DiscordUser(db.Model):

	__tablename__ = "discord_users"

	id = db.Column(db.Integer, primary_key=True)
	date = db.Column(db.DateTime, nullable=False)
	character_name = db.Column(db.String, unique=True, nullable = False)
	character_id = db.Column(db.Integer, unique=True, nullable = False)
	corporation_id = db.Column(db.Integer)
	alliance_id = db.Column(db.Integer)
	auth_code = db.Column(db.String, unique=True)
	discord_id = db.Column(db.String, unique=True)

	def __init__(self,character_name,character_id,corporation_id=None,alliance_id=None,discord_id=None):
		self.date = datetime.utcnow()
		self.character_name = character_name
		self.character_id = character_id
		self.corporation_id=corporation_id
		self.alliance_id=alliance_id
		self.auth_code = generate_unique_auth_token(32)
		self.discord_id = discord_id

	def __repr__(self):
		return '{},{},{},{},{},{},{},{}'.format(self.id,self.date,self.character_name,self.character_id,self.corporation_id,self.alliance_id,self.auth_code,self.discord_id)