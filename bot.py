import logging
import time
import requests
import datetime
import asyncio
import json
import sys

import discord
from discord.ext import commands

from Crypto.Cipher import AES
import base64

import sqlite3

DISCORD_AUTH_SLEEP = 300
CHUNK_SIZE = 20

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

# bot setup
logger.info('Creating bot object ...')
bot = commands.Bot(command_prefix=config['COMMAND_PREFIX'], description=config['DESCRIPTION'])
logger.info('Setup complete')

def get_user_with_discord_id(id):
    """
    Retrieve a user with a certain discord_id
    Args:
        str: user discord ID
    Returns:
        list: users with that discord ID
    """
    connection = sqlite3.connect('data.db')
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM discord_users WHERE discord_id=?',(id,))
    data = cursor.fetchall()
    connection.close()
    if not data:
        return []
    return data

def get_user_with_auth_code(auth_code):
    """
    Retrieve a user with a certain auth_code
    Args:
        str: user auth code
    Returns:
        list: users with that auth code
    """
    connection = sqlite3.connect('data.db')
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM discord_users WHERE auth_code=?',(auth_code,))
    data = cursor.fetchall()
    connection.close()
    if not data:
        return []
    return data

def get_all_authenticated_users():
    """
    Retrieve a user with a certain auth_code
    Args:
        /
    Returns:
        list: authenticated users
    """
    connection = sqlite3.connect('data.db')
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM discord_users where discord_id NOT NULL')
    data = cursor.fetchall()
    connection.close()
    if not data:
        return []
    return data

def set_user_discord_id_with_auth_code(auth_code, discord_id):
    """
    Set a user's discord_id
    Args:
        str: user auth code
        str: user discord id
    Returns:
        /
    """
    try:
        connection = sqlite3.connect('data.db')
        cursor = connection.cursor()
        cursor.execute('UPDATE discord_users SET discord_id=? WHERE auth_code=?', (discord_id, auth_code))
        connection.commit()
        connection.close()
        logger.info("Added discord id " + discord_id + " to the database where auth code was " + auth_code +"!")
    except Exception as e:
        logger.error('Exception in on_message(): ' + str(e))

def set_corp_id_and_alliance_id_with_character_id(corp_id, alliance_id, character_id):
    """
    Set a user's alliance and corp id
    Args:
        int: corp id
        int: alliance id
        int: character id
    Returns:
        /
    """
    try:
        connection = sqlite3.connect('data.db')
        cursor = connection.cursor()
        cursor.execute('UPDATE discord_users SET corporation_id=?,alliance_id=? WHERE character_id=?', (corp_id, alliance_id,character_id))
        connection.commit()
        connection.close()
        logger.info("Added corp id (" + str(corp_id) + ") and alliance id (" + str(alliance_id) +") to character id (" + str(character_id) + ")!")
    except Exception as e:
        logger.error('Exception in on_message(): ' + str(e))

@bot.event
async def on_ready():
    logger.info('Logged in')
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
            logger.info('Command "{}" from "{}" in "{}"'.format(message.content, message.author.name, message.channel.name))
        if 'bot' in message.content.lower():
            logger.info('Bot in message: "{}" by "{}" in "{}"'.format(message.content, message.author.name, message.channel.name))
        await bot.process_commands(message)
    except Exception as e:
        logger.error('Exception in on_message(): ' + str(e))

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
        logger.error('Exception in !auth: ' + str(e))

async def auth(context):
    """Command - auth"""
    message = context.message
    x = message.content.split()
    if len(x) <= 1:
        return "No arguments!"

    arg = message.content.split(' ', 1)[1]
    arg = arg.strip()

    #See if user already has an entry
    discordUsers = get_user_with_discord_id(message.author.id)
    if discordUsers:
        return "Discord user already in database!"

    #Add it into the database
    authUsers = get_user_with_auth_code(arg)
    if not authUsers:
        return "Auth code not found!"

    #Check if the character is already authenticated
    if authUsers[0][7] is not None:
        return "Already authenticated with " + authUsers[0][2] + "! If you did not authenticate with that character, message a mentor!"

    #Check corp and alliance
    r = requests.post("https://esi.tech.ccp.is/latest/characters/affiliation/?datasource=tranquility", json=[authUsers[0][3]],
        headers = {'Content-Type': 'application/json', 'Accept':'application/json','User-Agent': 'Maintainer: ' + config['MAINTAINER']})
    data = r.json()
    #Update corp and alliance in json
    alliance_id = None
    corp_id = data[0]['corporation_id']
    ticker = ""
    if 'alliance_id' in data[0]:
        alliance_id = data[0]['alliance_id']
        r = requests.get("https://esi.tech.ccp.is/latest/alliances/" + str(alliance_id) + "/?datasource=tranquility", headers={
            'User-Agent': 'Maintainer: ' + config['MAINTAINER']})
        ticker = r.json()['ticker']
    else:
        r = requests.get("https://esi.tech.ccp.is/latest/corporations/" + str(corp_id) + "/?datasource=tranquility", headers={
            'User-Agent': 'Maintainer: ' + config['MAINTAINER']})
        ticker = r.json()['ticker']

    #Update nickname
    try:
        await bot.change_nickname(message.author,"[" + ticker + "] " + authUsers[0][2])
    except Exception as e:
        logger.error('Exception in change_nickname(): ' + str(e))

    member = message.author
    server = message.server
    for entry in config['DISCORD_AUTH_ROLES']:
        role = discord.utils.get(server.roles, name=entry['role_name'])
        if role is None:
            logger.error("Role " + entry['role_name'] + " not found!")
            continue
        if entry['corp_id'] == corp_id:
            if role not in member.roles:
                logger.info("Giving " + member.nick + " the " + role.name + " role!")
                try:
                    await bot.add_roles(member,role)
                except Exception as e:
                    logger.error('Exception in add_roles(): ' + str(e))
            else:
                if role in member.roles:
                    logger.info("Removing " + role.name + " from " + member.nick + "!")
                    try:
                        await bot.remove_roles(member,role)
                    except Exception as e:
                        logger.error('Exception in remove_roles(): ' + str(e))

    #Update database
    set_corp_id_and_alliance_id_with_character_id(corp_id, alliance_id, authUsers[0][3])
    set_user_discord_id_with_auth_code(arg,message.author.id)
    logger.info(authUsers[0][2] + " authenticated with discord id " + message.author.id)
    return "Authenticated as " + authUsers[0][2]

async def schedule_corp_update():
    while True:
        try:
            logger.info('Sleeping for {} seconds'.format(DISCORD_AUTH_SLEEP))
            await asyncio.sleep(DISCORD_AUTH_SLEEP)
            logger.info('Updating discord names')
            result = await check_corp()
            logger.info(result) 
        except Exception as e:
            logger.error('Exception in schedule_corp_update(): ' + str(e))

#TODO: Look at using char affiliation
async def check_corp():
    #Retrieve members in database
    data= get_all_authenticated_users()

    currentIndex = 0
    sortedData = sorted(data,key=lambda x:x[3])

    while currentIndex < len(sortedData):
        tempList = []
        tempIndex = 0
        while tempIndex < CHUNK_SIZE:
            tempList.append(sortedData[currentIndex])
            tempIndex+=1
            currentIndex+=1
            if currentIndex >= len(sortedData):
                break 
        charIDList = [row[3] for row in tempList]
        #Check corp and alliance
        r = requests.post("https://esi.tech.ccp.is/latest/characters/affiliation/?datasource=tranquility", json=charIDList,
            headers = {'Content-Type': 'application/json', 'Accept':'application/json','User-Agent': 'Maintainer: ' + config['MAINTAINER']})
        data = r.json()
        sortedJSON = sorted(data,key=lambda x:x['character_id'])
        while len(sortedJSON) is not len(tempList):
            logger.info("Number of characters in database does not match the amount of returned characters in ESI. Checking which character is no longer valid")
            invalidList = []
            for char in charIDList:
                logger.info("Checking if " + str(char) + " still exists...")
                rChar = requests.get("https://esi.tech.ccp.is/latest/characters/" + str(char) + "/?datasource=tranquility", headers={
                    'User-Agent': 'Maintainer: '+ config['MAINTAINER']
                    })
                if 'error' in rChar.json():
                    invalidList.append(char)
                    logger.info(str(char) + " is not a valid character! Removed from list!")
            tempList = [t for t in tempList if t[3] not in invalidList]

        for index in range(len(tempList)):
            if not tempList[index][3] == sortedJSON[index]['character_id']:
                logger.error("Character id " + str(tempList[index][3]) + " does not match the data equivelant " + str(sortedJSON[index][3]) + "!")
                continue
            corpID_db = tempList[index][4]
            allianceID_db = tempList[index][5]
            allianceID = None
            if 'alliance_id' in sortedJSON[index]:
                allianceID = sortedJSON[index]['alliance_id']

            if not corpID_db == sortedJSON[index]['corporation_id'] or not allianceID_db == allianceID:
                logger.info(tempList[index][2]  + " has joined a new corp / alliance! Updating ticker.")
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
                set_corp_id_and_alliance_id_with_character_id(sortedJSON[index]['corporation_id'], allianceID, sortedJSON[index]['character_id'])
                #Set nickname and give role
                try:
                    server = bot.get_server(config['SERVER'])
                    member = server.get_member(tempList[index][7])
                    await bot.change_nickname(member,"[" + ticker + "] " + tempList[index][2])

                    for entry in config['DISCORD_AUTH_ROLES']:
                        role = discord.utils.get(server.roles, name=entry['role_name'])
                        if role is None:
                            logger.error("Role " + entry['role_name'] + " not found!")
                            continue
                        if entry['corp_id'] == sortedJSON[index]['corporation_id']:
                            if role not in member.roles:
                                logger.info("Giving " + member.nick + " the " + role.name + " role!")
                                try:
                                    await bot.add_roles(member,role)
                                except Exception as e:
                                    logger.error('Exception in add_roles(): ' + str(e))
                        else:
                            if role in member.roles:
                                logger.info("Removing " + role.name + " from " + member.nick + "!")
                                try:
                                    await bot.remove_roles(member,role)
                                except Exception as e:
                                    logger.error('Exception in remove_roles(): ' + str(e))
                except Exception as e:
                    logger.error('Exception in change_nickname(): ' + str(e))
    return "Corp check done!"



if __name__ == '__main__':
    try:
        logger.info('Scheduling background tasks ...')
        logger.info('Starting run loop ...')
        bot.loop.create_task(schedule_corp_update())
        bot.run(config['TOKEN'])
    except KeyboardInterrupt:
        logger.warning('Logging out ...')
        bot.loop.run_until_complete(bot.logout())
        logger.warning('Logged out')
    except Exception as e:
        logger.error('Caught unknown error: ' + str(e))
    finally:
        logger.warning('Closing ...')
        bot.loop.close()
        logger.info('Done')