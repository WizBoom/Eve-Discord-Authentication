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

DISCORD_BOT_AUTH_SLEEP = 3600
DATABASE_MEMBER_UPDATE = 86400
CHUNK_SIZE = 20

# config setup
with open('config.json') as f:
    config = json.load(f)

# bot setup
app.logger.info('Creating bot object ...')
bot = commands.Bot(command_prefix=config['DISCORD_COMMAND_PREFIX'], description=config['DISCORD_DESCRIPTION'])
app.logger.info('Setup complete')

@bot.event
async def on_ready():
    app.logger.info('Logged in')
    await bot.change_presence(game=discord.Game(name='Auth stuff'))
    #Do some more checks
    server = bot.get_server(config['DISCORD_SERVER'])
    if server is None:
        app.logger.error("Server " + config['DISCORD_SERVER'] + " not found!")
    channel = server.get_channel(config['DISCORD_PRIVATE_COMMAND_CHANNELS']['RECRUITMENT'])
    if channel is None:
        app.logger.error("Channel " + config['DISCORD_PRIVATE_COMMAND_CHANNELS']['RECRUITMENT]'] + " not found!")

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
        if message.content.startswith(config['DISCORD_COMMAND_PREFIX']):
            app.logger.info('Command "{}" from "{}" in "{}"'.format(message.content, message.author.name, message.channel.name))
        if 'bot' in message.content.lower():
            app.logger.info('Bot in message: "{}" by "{}" in "{}"'.format(message.content, message.author.name, message.channel.name))
        await bot.process_commands(message)
    except Exception as e:
        app.logger.error('Exception in on_message(): ' + str(e))

@bot.event
async def on_member_remove(member):
    """
    Event when user leaves the server
    Args:
        member (discord.Member) - member that left the server
    Returns:
        None
    """
    server = bot.get_server(config['DISCORD_SERVER'])
    channel = server.get_channel(config['DISCORD_PRIVATE_COMMAND_CHANNELS']['RECRUITMENT'])

    #Query the database to see if they're in there
    discordQuery = DiscordUser.query.filter(DiscordUser.discord_id == member.id).first()
    if discordQuery is not None:
        #Update that they are on the server
        discordQuery.on_server = False
        db.session.commit()

        await bot.send_message(channel,"User " + member.name + " ("+ discordQuery.character_name +") left the server!")
    else:
        await bot.send_message(channel,"User " + member.name + " (not authenticated) left the server!") 

@bot.event
async def on_member_join(member):
    """
    Event when user joins the server
    Args:
        member (discord.Member) - member that joined the server
    Returns:
        None
    """
    server = bot.get_server(config['DISCORD_SERVER'])
    if server is None:
        app.logger.error("Server " + config['DISCORD_SERVER'] + " not found!")
        return
    channel = server.get_channel(config['DISCORD_PRIVATE_COMMAND_CHANNELS']['RECRUITMENT'])
    if channel is None:
        app.logger.error("Channel " + config['DISCORD_PRIVATE_COMMAND_CHANNELS']['RECRUITMENT]'] + " not found!")
        return

    #Query the database to see if they're in there
    discordQuery = DiscordUser.query.filter(DiscordUser.discord_id == member.id).first()
    if discordQuery is not None:
        #If they are, give them the appropriate roles and update their roles
        #Update corp / alliance
        app.logger.info("Making ESI post request to characters/affiliation endpoint for character id "+str(discordQuery.character_id))
        r = requests.post("https://esi.tech.ccp.is/latest/characters/affiliation/?datasource=tranquility", json=[discordQuery.character_id],
            headers = {'Content-Type': 'application/json', 'Accept':'application/json','User-Agent': 'Maintainer: ' + config['MAINTAINER']})
        result = r.json()
        if not result:
            error = "Character ID " + discordQuery.character_id + " is not valid! Message a mentor!"
            app.logger.error(error)
            await bot.send_message(channel, error)
            return
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

        discordQuery.corporation_id = corp_id
        discordQuery.alliance_id = alliance_id
        discordQuery.on_server = True
        db.session.commit()

        nick = "[" + ticker + "] " + discordQuery.character_name
        await bot.send_message(channel,"User " + member.name + " joined the server as " + nick)
        try:
            await bot.change_nickname(member,nick)
        except Exception as e:
            app.logger.error('Exception in change_nickname(): ' + str(e))


        #Update roles if they're in a certain corp
        rolesToGive = []

        #Update auth role
        authRole = discord.utils.get(server.roles,name=config['BASE_AUTH_ROLE'])
        if authRole is None:
            app.logger.error("Role " + config['BASE_AUTH_ROLE'] + " not found!")
        else:
            rolesToGive.append(authRole)

        for entry in config['DISCORD_AUTH_ROLES']:
            role = discord.utils.get(server.roles, name=entry['role_name'])
            if role is None:
                app.logger.error("Role " + entry['role_name'] + " not found!")
                continue
            if entry['corp_id'] == corp_id:
                if role not in member.roles:
                    app.logger.info("Giving " + member.name + " the " + role.name + " role!")
                    rolesToGive.append(role)

        #Apply roles
        if len(rolesToGive) > 0:
            try:
                await bot.add_roles(member,*rolesToGive)
            except Exception as e:
                app.logger.error('Exception in add_roles(): ' + str(e))
    else:
        await bot.send_message(channel,"User " + member.name + " joined the server without authentication!")

async def schedule_corp_update():
    while True:
        try:
            app.logger.info('Sleeping for {} seconds'.format(DISCORD_BOT_AUTH_SLEEP))
            await asyncio.sleep(DISCORD_BOT_AUTH_SLEEP)
            app.logger.info('Updating discord names')
            result = await check_corp()
            app.logger.info(result) 
        except Exception as e:
            app.logger.error('Exception in schedule_corp_update(): ' + str(e))

async def check_corp():
    #Retrieve members in database
    server = bot.get_server(config['DISCORD_SERVER'])                 
    data = DiscordUser.query.filter(DiscordUser.on_server == True).all()

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
            member = server.get_member(tempList[index].discord_id)
            if not tempList[index].character_id == sortedJSON[index]['character_id']:
                app.logger.error("Character id " + str(tempList[index].character_id) + " does not match the data equivelant " + str(sortedJSON[index].character_id) + "!")
                continue
            corpID_db = tempList[index].corporation_id
            allianceID_db = tempList[index].alliance_id
            allianceID = None
            if 'alliance_id' in sortedJSON[index]:
                allianceID = sortedJSON[index]['alliance_id']

            if not corpID_db == sortedJSON[index]['corporation_id'] or not allianceID_db == allianceID or member.nick is None or member.nick.find(tempList[index].character_name) == -1:
                app.logger.info(tempList[index].character_name  + "'s nickname needs to be changed due to change in corp / alliance / invalid username")
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

async def schedule_remove_auth_roles():
    while True:
        try:
            await asyncio.sleep(1)
            await remove_auth_user_roles()
        except Exception as e:
            app.logger.error('Exception in schedule_remove_auth_roles(): ' + str(e))

async def remove_auth_user_roles():
    """
    Remove all roles related to authentication
    Args:
        None
    Returns:
        None
    """
    dlList = DiscordLinkRemoval.query.all()
    server = bot.get_server(config['DISCORD_SERVER'])
    for discordID in dlList:
        roleList = []

        member = server.get_member(discordID.discord_id)
        if member is None:
            app.logger.error("Member " + discordID.discord_id + " not found in remove_auth_user_roles()!")
            db.session.delete(discordID)
            db.session.commit()
            continue

        authRole = discord.utils.get(server.roles,name=config['BASE_AUTH_ROLE'])
        if authRole is None:
            app.logger.error("Role " + config['BASE_AUTH_ROLE'] + " not found!")
        else:
            roleList.append(authRole)

        #Check if the user hasn't been re-authenticated
        duq = DiscordUser.query.filter(DiscordUser.discord_id == discordID.discord_id).first()
        if duq:
            db.session.delete(discordID)
            db.session.commit()
            continue

        for entry in config['DISCORD_AUTH_ROLES']:
            role = discord.utils.get(server.roles, name=entry['role_name'])
            if role is None:
                    app.logger.error("Role " + entry['role_name'] + " not found!")
                    continue
            elif role in member.roles:
                roleList.append(role)

        try:
            await bot.remove_roles(member,*roleList)
            await bot.change_nickname(member,None)
            db.session.delete(discordID)
            app.logger.info(discordID.discord_id + ' has been unauthenticated!')
            db.session.commit()

        except Exception as e:
            app.logger.error('Exception in remove_roles(): ' + str(e))
        

async def schedule_update_on_server():
    while True:
        try:
            app.logger.info('Sleeping for {} seconds'.format(DATABASE_MEMBER_UPDATE))
            await asyncio.sleep(DATABASE_MEMBER_UPDATE)
            app.logger.info('Updating server connected users')
            dq = DiscordUser.query.filter(DiscordUser.on_server == False).all()
            server = bot.get_server(config['DISCORD_SERVER'])
            if server is None:
                app.logger.error("Server " + config['DISCORD_SERVER'] + " not found!")
                return
            for m in server.members:
                for r in dq:
                    if m.id == r.discord_id:
                        app.logger.info("User " + m.name + " was on the server but was not marked being so!")
                        await on_member_join(m)
                        break
        except Exception as e:
            app.logger.error('Exception in schedule_update_on_server(): ' + str(e))

if __name__ == '__main__':
    try:
        app.logger.info('Scheduling background tasks ...')
        app.logger.info('Starting run loop ...')
        bot.loop.create_task(schedule_corp_update())
        bot.loop.create_task(schedule_remove_auth_roles())
        bot.loop.create_task(schedule_update_on_server())
        bot.run(config['DISCORD_TOKEN'])
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
