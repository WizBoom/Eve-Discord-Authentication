import logging
import time
import requests
import datetime
import asyncio
import json
import sys

import discord
from discord.ext import commands

from app import db
from app import app
from models import *
import sqlite3

DISCORD_AUTH_SLEEP = 3600
CHUNK_SIZE = 20

# config setup
with open('config.json') as f:
    config = json.load(f)

# bot setup
app.logger.info('Creating bot object ...')
bot = commands.Bot(command_prefix=config['COMMAND_PREFIX'], description=config['DESCRIPTION'])
app.logger.info('Setup complete')

@bot.event
async def on_ready():
    app.logger.info('Logged in')
    await bot.change_presence(game=discord.Game(name='Auth stuff'))

@bot.event
async def on_message(message):
    """
    Logs attempes to use the bot.
    Args:
        message (discord.Message) - message sent in the channel
    Returns:
        None
    """
    try:
        if message.author == bot.user:
            return
        if message.content.startswith(config['COMMAND_PREFIX']):
            app.logger.info('Command "{}" from "{}" in "{}"'.format(message.content, message.author.name, message.channel.name))
        if 'bot' in message.content.lower():
            app.logger.info('Bot in message: "{}" by "{}" in "{}"'.format(message.content, message.author.name, message.channel.name))
        await bot.process_commands(message)
    except Exception as e:
        app.logger.error('Exception in on_message(): ' + str(e))

@bot.command(
    name='auth',
    brief='Authenticate yourself onto the server',
    help='Authenticate',
    pass_context=True
)
async def command_auth(context):
    """Command - auth"""
    try:
        output = await auth(context)
        await bot.say(output)
    except Exception as e:
        app.logger.error('Exception in !auth: ' + str(e))

async def auth(context):
    """Command - auth"""
    message = context.message
    x = message.content.split()
    if len(x) <= 1:
        return "No arguments!"

    arg = message.content.split(' ', 1)[1]
    arg = arg.strip()

    #See if user already has an entry
    discordQuery = DiscordUser.query.filter(DiscordUser.discord_id == message.author.id).first()
    if discordQuery is not None:
        error = "Discord user " + discordQuery.discord_id + " is already linked to a character (" + discordQuery.character_name +") in the database!"
        app.logger.info(error)
        return error

    #Add it into the database
    auth = DiscordUser.query.filter(DiscordUser.auth_code == arg).first()
    if auth is None:
        error = "Auth code " + arg + " not found!"
        app.logger.info(error)
        return error

    #Check if the character is already authenticated
    if auth.discord_id is not None:
        error = "Already authenticated with " + auth.character_name + "! If you did not authenticate with that character, message a mentor!"
        app.logger.info(error)
        return error

    #Check corp and alliance
    app.logger.info("Making ESI post request to characters/affiliation endpoint")
    r = requests.post("https://esi.tech.ccp.is/latest/characters/affiliation/?datasource=tranquility", json=[auth.character_id],
        headers = {'Content-Type': 'application/json', 'Accept':'application/json','User-Agent': 'Maintainer: ' + config['MAINTAINER']})
    result = r.json()
    if not result:
        error = "Character ID " + auth.character_id + " is not valid! Message a mentor!"
        return error
    data = result[0]
    #Update corp and alliance in json
    alliance_id = None
    corp_id = data['corporation_id']
    ticker = ""
    if 'alliance_id' in data:
        alliance_id = data['alliance_id']
        r = requests.get("https://esi.tech.ccp.is/latest/alliances/" + str(alliance_id) + "/?datasource=tranquility", headers={
            'User-Agent': 'Maintainer: ' + config['MAINTAINER']})
        ticker = r.json()['ticker']
    else:
        r = requests.get("https://esi.tech.ccp.is/latest/corporations/" + str(corp_id) + "/?datasource=tranquility", headers={
            'User-Agent': 'Maintainer: ' + config['MAINTAINER']})
        ticker = r.json()['ticker']

    #Update nickname
    try:
        nick = "[" + ticker + "] " + auth.character_name
        app.logger.info("Changing nickname of discord account " + message.author.id + " to " + nick + "!")
        await bot.change_nickname(message.author,nick)
    except Exception as e:
        app.logger.error('Exception in change_nickname(): ' + str(e))

    #Update roles if they're in a certain corp
    rolesToGive = []
    rolesToRemove = []

    #Update auth role
    authRole = discord.utils.get(message.server.roles,name=config['BASE_AUTH_ROLE'])
    if authRole is None:
        app.logger.error("Role " + config['BASE_AUTH_ROLE'] + " not found!")
    else:
        rolesToGive.append(authRole)

    for entry in config['DISCORD_AUTH_ROLES']:
        role = discord.utils.get(message.server.roles, name=entry['role_name'])
        if role is None:
            app.logger.error("Role " + entry['role_name'] + " not found!")
            continue
        if entry['corp_id'] == corp_id:
            if role not in message.author.roles:
                app.logger.info("Giving " + message.author.nick + " the " + role.name + " role!")
                rolesToGive.append(role)
        else:
            if role in message.author.roles:
                app.logger.info("Removing " + role.name + " from " + message.author.nick + "!")
                rolesToRemove.append(role)

    #Apply roles
    if len(rolesToGive) > 0:
        try:
            await bot.add_roles(message.author,*rolesToGive)
        except Exception as e:
            app.logger.error('Exception in add_roles(): ' + str(e))

    #Remove roles
    if len(rolesToRemove) > 0:
        try:
            await bot.remove_roles(message.author,*rolesToRemove)
        except Exception as e:
            app.logger.error('Exception in remove_roles(): ' + str(e))

    #Update database
    auth.corporation_id = corp_id
    auth.alliance_id = alliance_id
    auth.discord_id = message.author.id
    app.logger.info(auth.character_name + " (" + str(auth.corporation_id) +", " + str(auth.alliance_id) + ")" +" authenticated with discord id " + auth.discord_id)
    db.session.commit()
    return "Authenticated as " + auth.character_name

async def schedule_corp_update():
    while True:
        try:
            app.logger.info('Sleeping for {} seconds'.format(DISCORD_AUTH_SLEEP))
            await asyncio.sleep(DISCORD_AUTH_SLEEP)
            app.logger.info('Updating discord names')
            result = await check_corp()
            app.logger.info(result) 
        except Exception as e:
            app.logger.error('Exception in schedule_corp_update(): ' + str(e))

async def check_corp():
    #Retrieve members in database
    data = DiscordUser.query.filter(DiscordUser.discord_id != None).all()

    #Sort the data since the return from esi is sorted too
    currentIndex = 0
    sortedData = sorted(data,key=lambda x:x.character_id)

    #Break the data into chunks, since ESI has a max amount of characters per post request
    while currentIndex < len(sortedData):
        tempList = []
        tempIndex = 0
        while tempIndex < CHUNK_SIZE:
            tempList.append(sortedData[currentIndex])
            tempIndex+=1
            currentIndex+=1
            if currentIndex >= len(sortedData):
                break 
        charIDList = [row.character_id for row in tempList]
        #Check corp and alliance
        app.logger.info("Making ESI post request to characters/affiliation endpoint")
        r = requests.post("https://esi.tech.ccp.is/latest/characters/affiliation/?datasource=tranquility", json=charIDList,
            headers = {'Content-Type': 'application/json', 'Accept':'application/json','User-Agent': 'Maintainer: ' + config['MAINTAINER']})
        data = r.json()
        sortedJSON = sorted(data,key=lambda x:x['character_id'])
        #Incase of a missmatch, remove the non-existant character IDs
        while len(sortedJSON) is not len(tempList):
            app.logger.info("Number of characters in database does not match the amount of returned characters in ESI. Checking which character is no longer valid")
            invalidList = []
            for char in charIDList:
                app.logger.info("Checking if " + str(char) + " still exists...")
                rChar = requests.get("https://esi.tech.ccp.is/latest/characters/" + str(char) + "/?datasource=tranquility", headers={
                    'User-Agent': 'Maintainer: '+ config['MAINTAINER']
                    })
                if 'error' in rChar.json():
                    invalidList.append(char)
                    app.logger.info(str(char) + " is not a valid character! Removed from list!")
            tempList = [t for t in tempList if t.character_id not in invalidList]

        for index in range(len(tempList)):
            if not tempList[index].character_id == sortedJSON[index]['character_id']:
                app.logger.error("Character id " + str(tempList[index].character_id) + " does not match the data equivelant " + str(sortedJSON[index].character_id) + "!")
                continue
            corpID_db = tempList[index].corporation_id
            allianceID_db = tempList[index].alliance_id
            allianceID = None
            if 'alliance_id' in sortedJSON[index]:
                allianceID = sortedJSON[index]['alliance_id']

            if not corpID_db == sortedJSON[index]['corporation_id'] or not allianceID_db == allianceID:
                app.logger.info(tempList[index].character_name  + " has joined a new corp / alliance! Updating ticker.")
                ticker = ""
                if allianceID is not None:
                    allianceID = sortedJSON[index]['alliance_id']
                    #Set alliance ticker
                    rTicker = requests.get("https://esi.tech.ccp.is/latest/alliances/" + str(allianceID) + "/?datasource=tranquility", headers={
                        'User-Agent': 'Maintainer: '+ config['MAINTAINER']
                        })
                    ticker = rTicker.json()['ticker']
                else:
                    #Set corp ticker
                    rTicker = requests.get("https://esi.tech.ccp.is/latest/corporations/" + str(sortedJSON[index]['corporation_id']) + "/?datasource=tranquility", headers={
                        'User-Agent': 'Maintainer: '+ config['MAINTAINER']
                        })
                    ticker = rTicker.json()['ticker']
                #Update id
                #set_corp_id_and_alliance_id_with_character_id(sortedJSON[index]['corporation_id'], allianceID, sortedJSON[index]['character_id'])
                app.logger.info("Added corp id (" + str(sortedJSON[index]['corporation_id']) + ") and alliance id (" + str(allianceID) +") to character id (" + str(sortedJSON[index]['character_id']) + ")!")
                user = DiscordUser.query.filter(DiscordUser.character_id == sortedJSON[index]['character_id']).first()
                if user is None:
                    app.logger.error("Character id " + sortedJSON[index]['character_id'] + " not found!")
                    continue
                user.corporation_id = sortedJSON[index]['corporation_id']
                user.alliance_id = allianceID
                db.session.commit()
                #Set nickname and give role
                try:
                    server = bot.get_server(config['SERVER'])
                    member = server.get_member(tempList[index].discord_id)
                    await bot.change_nickname(member,"[" + ticker + "] " + tempList[index].character_name)

                    for entry in config['DISCORD_AUTH_ROLES']:
                        role = discord.utils.get(server.roles, name=entry['role_name'])
                        if role is None:
                            app.logger.error("Role " + entry['role_name'] + " not found!")
                            continue
                        if entry['corp_id'] == sortedJSON[index]['corporation_id']:
                            if role not in member.roles:
                                try:
                                    app.logger.info("Giving " + member.nick + " the " + role.name + " role!")
                                    await bot.add_roles(member,role)
                                except Exception as e:
                                    app.logger.error('Exception in add_roles(): ' + str(e))
                        else:
                            if role in member.roles:
                                try:
                                    app.logger.info("Removing " + role.name + " from " + member.nick + "!")
                                    await bot.remove_roles(member,role)
                                except Exception as e:
                                    app.logger.error('Exception in remove_roles(): ' + str(e))
                except Exception as e:
                    app.logger.error('Exception in change_nickname(): ' + str(e))
    return "Corp check done!"

if __name__ == '__main__':
    try:
        app.logger.info('Scheduling background tasks ...')
        app.logger.info('Starting run loop ...')
        bot.loop.create_task(schedule_corp_update())
        bot.run(config['TOKEN'])
    except KeyboardInterrupt:
        app.logger.warning('Logging out ...')
        bot.loop.run_until_complete(bot.logout())
        app.logger.warning('Logged out')
    except Exception as e:
        app.logger.error('Caught unknown error: ' + str(e))
    finally:
        app.logger.warning('Closing ...')
        bot.loop.close()
        app.logger.info('Done')