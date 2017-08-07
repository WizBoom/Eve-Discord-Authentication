#!/usr/bin/env python
from app import db
from models import *

#Drop all
db.drop_all()

#Create the database
db.create_all()
