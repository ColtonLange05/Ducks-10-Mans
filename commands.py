"""This file holds all bot commands. <prefix><function_name> is the full command for each function."""

import asyncio
import os
import copy  # To make a copy of player_mmr
import random

import discord
from discord.ext import commands
import requests
from table2ascii import table2ascii as t2a, PresetStyle
import wcwidth

from database import users, all_matches, mmr_collection, tdm_mmr_collection
from stats_helper import update_stats
from views.captains_drafting_view import CaptainsDraftingView
from views.mode_vote_view import ModeVoteView
from views.signup_view import SignupView
from views.leaderboard_view import (
    LeaderboardView,
    LeaderboardViewKD,
    LeaderboardViewACS,
    LeaderboardViewWins,
    truncate_by_display_width
)


# Initialize API
api_key = os.getenv("api_key")
headers = {
    "Authorization": api_key,
}

# FOR TESTING ONLY, REMEMBER TO SET WINNER AND total_rounds
mock_match_data = {
    "players": [
        {
            "name": "Samurai",
            "tag": "Mai",
            "team_id": "red",
            "stats": {"score": 8136, "kills": 29, "deaths": 16, "assists": 8},
        },
        {
            "name": "WaffIes",
            "tag": "NA1",
            "team_id": "red",
            "stats": {"score": 6048, "kills": 20, "deaths": 20, "assists": 6},
        },
        {
            "name": "DeagleG",
            "tag": "Y33T",
            "team_id": "red",
            "stats": {"score": 5928, "kills": 24, "deaths": 14, "assists": 13},
        },
        {
            "name": "TheAlphaEw0k",
            "tag": "MST",
            "team_id": "red",
            "stats": {"score": 5688, "kills": 21, "deaths": 18, "assists": 3},
        },
        {
            "name": "dShocc1",
            "tag": "LNEUP",
            "team_id": "red",
            "stats": {"score": 1368, "kills": 3, "deaths": 15, "assists": 12},
        },
        {
            "name": "Nisom",
            "tag": "zia",
            "team_id": "blue",
            "stats": {"score": 8424, "kills": 30, "deaths": 19, "assists": 5},
        },
        {
            "name": "mizu",
            "tag": "yor",
            "team_id": "blue",
            "stats": {"score": 7368, "kills": 26, "deaths": 20, "assists": 3},
        },
        {
            "name": "Duck",
            "tag": "MST",
            "team_id": "blue",
            "stats": {"score": 3528, "kills": 11, "deaths": 19, "assists": 5},
        },
        {
            "name": "twentytwo",
            "tag": "4249",
            "team_id": "blue",
            "stats": {"score": 3240, "kills": 12, "deaths": 16, "assists": 3},
        },
        {
            "name": "mintychewinggum",
            "tag": "8056",
            "team_id": "blue",
            "stats": {"score": 1656, "kills": 4, "deaths": 21, "assists": 11},
        },
    ],
    "teams": [
        {"team_id": "red", "won": True, "rounds_won": 13, "rounds_lost": 11},
        {"team_id": "blue", "won": False, "rounds_won": 11, "rounds_lost": 13},
    ],
}


class BotCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.dev_mode = False
        self.leaderboard_message = None
        self.leaderboard_view = None
        self.refresh_task = None

        # Store chosen_mode and selected_map as state
        # chosen_mode will be either "Balanced" or "Captains"
        # selected_map will be set after map vote
        self.bot.chosen_mode = None
        self.bot.selected_map = None
        self.bot.match_not_reported = False
        self.bot.match_ongoing = False
        self.bot.player_names = {}
        self.bot.signup_active = False
        self.bot.queue = []
        self.bot.captain1 = None
        self.bot.captain2 = None
        self.bot.team1 = []
        self.bot.team2 = []
        print("[DEBUG] Checking the last match document in 'matches' DB for total rounds via 'rounds' array:")
        last_match_doc = all_matches.find_one(sort=[("_id", -1)])  # fetch the most recent match
        if last_match_doc:
            rounds_array = last_match_doc.get("rounds", [])
            print(f"  [DEBUG DB] The last match in 'matches' had {len(rounds_array)} rounds (via last_match_doc['rounds']).")
        else:
            print("  [DEBUG DB] No matches found in the 'matches' collection.")

    @commands.command()
    async def signup(self, ctx):
        if self.bot.signup_active:
            await ctx.send("A signup is already in progress.")
            return

        if self.bot.match_not_reported:
            await ctx.send("Report the last match before starting another one.")
            return

        self.bot.load_mmr_data()
        print("[DEBUG] Reloaded MMR data at start of signup")

        # Clear any existing signup view and state
        if self.bot.signup_view is not None:
            self.bot.signup_view.cancel_signup_refresh()
            self.bot.signup_view = None

        # Reset all match-related state
        self.bot.signup_active = True
        self.bot.queue = []
        self.bot.captain1 = None
        self.bot.captain2 = None
        self.bot.team1 = []
        self.bot.team2 = []
        self.bot.chosen_mode = None
        self.bot.selected_map = None

        self.bot.match_name = f"match-{random.randrange(1, 10**4):04}"

        try:
            self.bot.match_role = await ctx.guild.create_role(name=self.bot.match_name, hoist=True)
            await ctx.guild.edit_role_positions(positions={self.bot.match_role: 5})

            match_channel_permissions = {
                ctx.guild.default_role: discord.PermissionOverwrite(send_messages=False),
                self.bot.match_role: discord.PermissionOverwrite(send_messages=True),
            }

            self.bot.match_channel = await ctx.guild.create_text_channel(
                name=self.bot.match_name,
                category=ctx.channel.category,
                position=0,
                overwrites=match_channel_permissions,
            )

            # Create new signup view
            from views.signup_view import SignupView
            self.bot.signup_view = SignupView(ctx, self.bot)

            self.bot.current_signup_message = await self.bot.match_channel.send(
                "Click a button to manage your queue status!", view=self.bot.signup_view
            )

            await ctx.send(f"Queue started! Signup: <#{self.bot.match_channel.id}>")
        except Exception as e:
            # Cleanup if anything fails
            self.bot.signup_active = False
            if hasattr(self.bot, 'match_role') and self.bot.match_role:
                try:
                    await self.bot.match_role.delete()
                except:
                    pass
            if hasattr(self.bot, 'match_channel') and self.bot.match_channel:
                try:
                    await self.bot.match_channel.delete()
                except:
                    pass
            await ctx.send(f"Error setting up queue: {str(e)}")

    async def cleanup_match_resources(self):
        try:
            if hasattr(self.bot, 'match_channel') and self.bot.match_channel:
                try:
                    await self.bot.match_channel.delete()
                except discord.NotFound:
                    print("[DEBUG] Match channel already deleted")
                except discord.Forbidden:
                    print("[DEBUG] Missing permissions to delete match channel")
                finally:
                    self.bot.match_channel = None

            if hasattr(self.bot, 'match_role') and self.bot.match_role:
                # Remove role from all members first
                try:
                    for member in self.bot.match_role.members:
                        await member.remove_roles(self.bot.match_role)
                except discord.HTTPException:
                    print("[DEBUG] Error removing roles from members")

                # Then delete the role
                try:
                    await self.bot.match_role.delete()
                except discord.NotFound:
                    print("[DEBUG] Match role already deleted")
                except discord.Forbidden:
                    print("[DEBUG] Missing permissions to delete match role")
                finally:
                    self.bot.match_role = None

            # Clear other match-related state
            self.bot.match_not_reported = False
            self.bot.match_ongoing = False
            self.bot.queue.clear()
            
            if self.bot.current_signup_message:
                try:
                    await self.bot.current_signup_message.delete()
                except discord.NotFound:
                    pass
                finally:
                    self.bot.current_signup_message = None

        except Exception as e:
            print(f"[DEBUG] Error during cleanup: {str(e)}")
    
    # Report the match
    @commands.command()
    async def report(self, ctx):

        current_user = users.find_one({"discord_id": str(ctx.author.id)})
        if not current_user:
            await ctx.send(
                "You need to link your Riot account first using `!linkriot Name#Tag`"
            )
            return
        
        print(f"[DEBUG] Current User: {current_user}")

        name = current_user.get("name", "").lower()
        tag = current_user.get("tag", "").lower()
        region = "na"
        platform = "pc"

        url = f"https://api.henrikdev.xyz/valorant/v4/matches/{region}/{platform}/{name}/{tag}"
        response = requests.get(url, headers=headers, timeout=30)
        match_data = response.json()

        match = match_data["data"][0]
        metadata = match.get("metadata", {})
        map_name = metadata.get("map", {}).get("name", "").lower()
        print(f"[DEBUG] Map from API: {map_name}, Selected map: {self.bot.selected_map}")

        testing_mode = False  # TRUE WHILE TESTING

        if testing_mode:
            match = mock_match_data
            self.bot.match_ongoing = True

            # Reconstruct queue, team1, and team2 from mock_match_data
            queue = []
            team1 = []
            team2 = []
            self.bot.team1 = team1
            self.bot.team2 = team2

            for player_data in match["players"]:
                player_name = player_data["name"].lower()
                player_tag = player_data["tag"].lower()

                user = users.find_one({"name": player_name, "tag": player_tag})
                if user:
                    discord_id = user["discord_id"]
                    player = {"id": discord_id, "name": player_name}

                    queue.append(player)

                    if player_data["team_id"] == "red":
                        team1.append(player)
                    else:
                        team2.append(player)

                    if discord_id not in self.bot.player_mmr:
                        self.bot.player_mmr[discord_id] = {
                            "mmr": 1000,
                            "wins": 0,
                            "losses": 0,
                        }
                    self.bot.player_names[discord_id] = player_name
                else:
                    await ctx.send(
                        f"Player {player_name}#{player_tag} is not linked to any Discord account."
                    )
                    return

            # For mocking match data, set to amount of rounds played
            total_rounds = 24
        else:
            if not self.bot.match_ongoing:
                await ctx.send(
                    "No match is currently active, use `!signup` to start one"
                )
                return

            if not self.bot.selected_map:
                await ctx.send("No map was selected for this match.")
                return

            # FOR TESTING PURPOSES
            #self.bot.selected_map = map_name

            if self.bot.selected_map.lower() != map_name:
                await ctx.send(
                    "Map doesn't match your most recent match. Unable to report it."
                )
                return

            if "data" not in match_data or not match_data["data"]:
                await ctx.send("Could not retrieve match data.")
                return

            match = match_data["data"][0]

            # Get total rounds played from the match data
            teams = match.get("teams", [])
            if teams:
                total_rounds = metadata.get("total_rounds")
                if not total_rounds:
                    # fallback to length of the "rounds" array
                    rounds_data = match.get("rounds", [])
                    total_rounds = len(rounds_data)
                    print(f"[DEBUG] total_rounds fallback to match['rounds'] length = {total_rounds}")
                else:
                    print(f"[DEBUG] total_rounds from metadata = {total_rounds}")
            else:
                await ctx.send("No team data found in match data.")
                return

        match_players = match.get("players", [])
        if not match_players:
            await ctx.send("No players found in match data.")
            return

        queue_riot_ids = set()
        for player in self.bot.queue:
            user_data = users.find_one({"discord_id": str(player["id"])})
            if user_data:
                player_name = user_data.get("name").lower()
                player_tag = user_data.get("tag").lower()
                queue_riot_ids.add((player_name, player_tag))
        
        print(f"[DEBUG] Queued players RIOT ID's: {queue_riot_ids}")

        # get the list of players in the match
        match_player_names = set()
        for player in match_players:
            player_name = player.get("name", "").lower()
            player_tag = player.get("tag", "").lower()
            match_player_names.add((player_name, player_tag))

        print(f"[DEBUG] match_player_names from API: {match_player_names}")

        if not queue_riot_ids.issubset(match_player_names):
            # Find which players don't match
            missing_players = queue_riot_ids - match_player_names
            mismatch_message = "The most recent match does not match the 10-man's match.\n\n"
            mismatch_message += "The following players' Riot IDs don't match the game data:\n"
            
            for name, tag in missing_players:
                mismatch_message += f"• {name}#{tag}\n"
            
            mismatch_message += "\nPossible reasons:\n"
            mismatch_message += "1. Did you or someone make a change to their Riot name/tag?\n"
            mismatch_message += "2. Are you trying to report the correct match?\n\n"
            mismatch_message += "If you changed your Riot ID, please use `!linkriot NewName#NewTag` to update it."
            
            await ctx.send(mismatch_message)
            return

        # Determine which team won
        teams = match.get("teams", [])
        if not teams:
            await ctx.send("No team data found in match data.")
            return

        winning_team_id = None
        for team in teams:
            if team.get("won"):
                winning_team_id = team.get("team_id", "").lower()
                break
        
        print(f"[DEBUG]: Winning team: {winning_team_id}")
        if not winning_team_id:
            await ctx.send("Could not determine the winning team.")
            return

        match_team_players = {"red": set(), "blue": set()}
        for player_info in match_players:
            raw_team_id = player_info.get("team_id", "").lower()  # "red" or "blue"
            p_name = player_info.get("name", "").lower()
            p_tag = player_info.get("tag", "").lower()
            if raw_team_id in match_team_players:
                match_team_players[raw_team_id].add((p_name, p_tag))

        team1_riot_ids = set()
        for player in self.bot.team1:
            user_data = users.find_one({"discord_id": str(player["id"])})
            if user_data:
                player_name = user_data.get("name", "").lower()
                player_tag = user_data.get("tag").lower()
                team1_riot_ids.add((player_name, player_tag))

        team2_riot_ids = set()
        for player in self.bot.team2:
            user_data = users.find_one({"discord_id": str(player["id"])})
            if user_data:
                player_name = user_data.get("name", "").lower()
                player_tag = user_data.get("tag").lower()
                team2_riot_ids.add((player_name, player_tag))

        print(f"[DEBUG] team1_riot_ids: {team1_riot_ids}")
        print(f"[DEBUG] team2_riot_ids: {team2_riot_ids}")

        winning_match_team_players = match_team_players.get(winning_team_id, set())
        print(f"[DEBUG] Winning team Riot ID's: {winning_match_team_players}")

        if winning_match_team_players == team1_riot_ids:
            winning_team = self.bot.team1
            losing_team = self.bot.team2
        elif winning_match_team_players == team2_riot_ids:
            winning_team = self.bot.team2
            losing_team = self.bot.team1
        else:
            await ctx.send("Could not match the winning team to our teams.")
            return

        for player in winning_team + losing_team:
            player_id = str(player["id"])
            self.bot.ensure_player_mmr(player_id, self.bot.player_names)

        # Get top players
        pre_update_mmr = copy.deepcopy(self.bot.player_mmr)
        
        # Filter out entries without MMR and ensure proper data structure
        valid_mmr_entries = [
            (pid, stats) for pid, stats in pre_update_mmr.items() 
            if isinstance(stats, dict) and "mmr" in stats
        ]
        
        if valid_mmr_entries:
            sorted_mmr_before = sorted(valid_mmr_entries, key=lambda x: x[1]["mmr"], reverse=True)
            top_mmr_before = sorted_mmr_before[0][1]["mmr"]
            top_players_before = [str(pid) for pid, stats in sorted_mmr_before if stats["mmr"] == top_mmr_before]
        else:
            # Handle case where no valid MMR entries exist
            top_mmr_before = 1000  # Default MMR
            top_players_before = []

        sorted_mmr_before = sorted(pre_update_mmr.items(), key=lambda x: x[1]["mmr"], reverse=True)
        top_mmr_before = sorted_mmr_before[0][1]["mmr"]
        top_players_before = [str(pid) for pid, stats in sorted_mmr_before if stats["mmr"] == top_mmr_before]

        # Update stats for each player
        for player_stats in match_players:
            update_stats(player_stats, total_rounds, self.bot.player_mmr, self.bot.player_names)
        print("[DEBUG] Basic stats updated")

        # Adjust MMR once
        self.bot.adjust_mmr(winning_team, losing_team)
        print("[DEBUG] MMR adjusted")
        await ctx.send("Match stats and MMR updated!")

        self.bot.save_mmr_data()
        print("[DEBUG] MMR data saved")

        self.bot.load_mmr_data()  # Reload the MMR data
        print("[DEBUG] Reloaded MMR data after save")

        # Now save all updates to the database
        print("Before player stats updated")
        

        for discord_id, stats in self.bot.player_mmr.items():
            # Get the Riot name for the player
            user_data = users.find_one({"discord_id": str(discord_id)})
            if user_data:
                riot_name = f"{user_data.get('name', 'Unknown')}#{user_data.get('tag', 'Unknown')}"
            else:
                riot_name = "Unknown"

            # Create complete stats document with all fields
            complete_stats = {
                "mmr": stats.get("mmr", 1000),
                "wins": stats.get("wins", 0),
                "losses": stats.get("losses", 0),
                "name": riot_name,
                "total_combat_score": stats.get("total_combat_score", 0),
                "total_kills": stats.get("total_kills", 0),
                "total_deaths": stats.get("total_deaths", 0),
                "matches_played": stats.get("matches_played", 0),
                "total_rounds_played": stats.get("total_rounds_played", 0),
                "average_combat_score": stats.get("average_combat_score", 0),
                "kill_death_ratio": stats.get("kill_death_ratio", 0)
            }

            # Update database with all fields
            mmr_collection.update_one(
                {"player_id": discord_id},
                {"$set": complete_stats},
                upsert=True
            )

        print("[DEBUG] All stats saved to database")

        sorted_mmr_after = sorted(self.bot.player_mmr.items(), key=lambda x: x[1]["mmr"], reverse=True)
        top_mmr_after = sorted_mmr_after[0][1]["mmr"]
        top_players_after = [pid for pid, stats in sorted_mmr_after if stats["mmr"] == top_mmr_after]

        new_top_players = set(top_players_after) - set(top_players_before)
        if new_top_players:
            for new_top_player_id in new_top_players:
                user_data = users.find_one({"discord_id": str(new_top_player_id)})
                if user_data:
                    riot_name = user_data.get("name", "Unknown")
                    riot_tag = user_data.get("tag", "Unknown")
                    await ctx.send(f"{riot_name}#{riot_tag} is now supersonic radiant!")

        # Record every match played in a new collection
        all_matches.insert_one(match)

        await asyncio.sleep(5)
        self.bot.match_not_reported = False
        self.bot.match_ongoing = False
        await self.cleanup_match_resources()

    # Allow players to check their MMR and stats
    @commands.command()
    async def stats(self, ctx, *, riot_input=None):
        # Allows players to lookup the stats of other players
        if riot_input is not None:
            try:
                riot_name, riot_tag = riot_input.rsplit("#", 1)
            except ValueError:
                await ctx.send("Please provide your Riot ID in the format: `Name#Tag`")
                return
            player_data = users.find_one({"name": str(riot_name).lower(), "tag": str(riot_tag).lower()})
            if player_data:
                player_id = str(player_data.get("discord_id"))
            else:
                await ctx.send(
                    "Could not find this player. Please check the name and tag and ensure they have played at least one match."
                )
                return
        else:
            player_id = str(ctx.author.id)

        if player_id in self.bot.player_mmr:
            stats_data = self.bot.player_mmr[player_id]
            # Get stats with safe defaults
            mmr_value = stats_data.get("mmr", 1000)
            wins = stats_data.get("wins", 0)
            losses = stats_data.get("losses", 0)
            matches_played = stats_data.get("matches_played", wins + losses)
            total_rounds_played = stats_data.get("total_rounds_played", 0)
            avg_cs = stats_data.get("average_combat_score", 0)
            kd_ratio = stats_data.get("kill_death_ratio", 0)
            win_percent = (wins / matches_played) * 100 if matches_played > 0 else 0

            # Get Riot name and tag
            user_data = users.find_one({"discord_id": str(player_id)})
            if user_data:
                riot_name = user_data.get("name", "Unknown")
                riot_tag = user_data.get("tag", "Unknown")
                player_name = f"{riot_name}#{riot_tag}"
            else:
                player_name = ctx.author.name

            # Find leaderboard position with safe dictionary access
            total_players = len(self.bot.player_mmr)
            sorted_mmr = sorted(
                [(pid, stats) for pid, stats in self.bot.player_mmr.items() if "mmr" in stats],
                key=lambda x: x[1]["mmr"],
                reverse=True
            )
            position = None
            slash = "/"
            for idx, (pid, _) in enumerate(sorted_mmr, start=1):
                if pid == player_id:
                    position = idx
                    break

            # Rank 1 tag
            if position == 1:
                position = "*Supersonic Radiant!* (Rank 1)"
                total_players = ""
                slash = ""

            await ctx.send(
                f"**{player_name}'s Stats:**\n"
                f"MMR: {mmr_value}\n"
                f"Rank: {position}{slash}{total_players}\n"
                f"Wins: {wins}\n"
                f"Losses: {losses}\n"
                f"Win%: {win_percent:.2f}%\n"
                f"Matches Played: {matches_played}\n"
                f"Total Rounds Played: {total_rounds_played}\n"
                f"Average Combat Score: {avg_cs:.2f}\n"
                f"Kill/Death Ratio: {kd_ratio:.2f}"
            )
        else:
            await ctx.send(
                "You do not have an MMR yet. Participate in matches to earn one!"
            )

    # Display leaderboard
    @commands.command()
    async def leaderboard(self, ctx):
        cursor = mmr_collection.find()
        sorted_data = list(cursor)
        sorted_data.sort(key=lambda x: x.get("mmr", 0), reverse=True)

        self.leaderboard_view = LeaderboardView(
            ctx, 
            self.bot, 
            sorted_data, 
            players_per_page=10, 
            timeout=None, 
            mode="normal"
        )

        # Calculate initial page data
        start_index = 0
        end_index = min(10, len(sorted_data))
        page_data = sorted_data[start_index:end_index]

        # Create initial leaderboard table
        leaderboard_data = []
        for idx, stats in enumerate(page_data, start=1):
            user_data = users.find_one({"discord_id": str(stats["player_id"])})
            if user_data:
                full_name = f"{user_data.get('name', 'Unknown')}#{user_data.get('tag', 'Unknown')}"
                if wcwidth.wcswidth(full_name) > 20:
                    name = full_name[:17] + "..."
                else:
                    name = full_name.ljust(20)
            else:
                name = "Unknown"

            leaderboard_data.append([
                idx,
                name,
                stats.get("mmr", 1000),
                stats.get("wins", 0),
                stats.get("losses", 0),
                f"{stats.get('average_combat_score', 0):.2f}",
                f"{stats.get('kill_death_ratio', 0):.2f}"
            ])

        table_output = t2a(
            header=["Rank", "User", "MMR", "Wins", "Losses", "Avg ACS", "K/D"],
            body=leaderboard_data,
            first_col_heading=True,
            style=PresetStyle.thick_compact
        )

        content = f"## MMR Leaderboard (Page 1/{self.leaderboard_view.total_pages}) ##\n```\n{table_output}\n```"
        
        self.leaderboard_message = await ctx.send(content=content, view=self.leaderboard_view)

        if self.refresh_task is not None:
            self.refresh_task.cancel()
        self.refresh_task = asyncio.create_task(self.periodic_refresh())

    async def periodic_refresh(self):
        await self.bot.wait_until_ready()
        try:
            while True:
                await asyncio.sleep(30)
                if self.leaderboard_message and self.leaderboard_view:
                    # Just edit with the same content and view
                    await self.leaderboard_message.edit(
                        content=self.leaderboard_message.content,
                        view=self.leaderboard_view,
                    )
                else:
                    break
        except asyncio.CancelledError:
            pass

    async def periodic_refresh_kd(self):
        await self.bot.wait_until_ready()
        try:
            while True:
                await asyncio.sleep(30)
                if self.leaderboard_message_kd and self.leaderboard_view_kd:
                    # Just edit with the same content and view
                    await self.leaderboard_message_kd.edit(
                        content=self.leaderboard_message_kd.content,
                        view=self.leaderboard_view_kd,
                    )
                else:
                    break
        except asyncio.CancelledError:
            pass

    async def periodic_refresh_wins(self):
        await self.bot.wait_until_ready()
        try:
            while True:
                await asyncio.sleep(30)
                if self.leaderboard_message_wins and self.leaderboard_view_wins:
                    # Just edit with the same content and view
                    await self.leaderboard_message_wins.edit(
                        content=self.leaderboard_message_wins.content,
                        view=self.leaderboard_view_wins,
                    )
                else:
                    break
        except asyncio.CancelledError:
            pass

    async def periodic_refresh_acs(self):
        await self.bot.wait_until_ready()
        try:
            while True:
                await asyncio.sleep(30)
                if self.leaderboard_message_acs and self.leaderboard_view_acs:
                    # Just edit with the same content and view
                    await self.leaderboard_message_acs.edit(
                        content=self.leaderboard_message_acs.content,
                        view=self.leaderboard_view_acs,
                    )
                else:
                    break
        except asyncio.CancelledError:
            pass

    @commands.command()
    @commands.has_role("Owner")
    async def stop_leaderboard(self, ctx):
        # Stop the refresh
        if self.refresh_task:
            self.refresh_task.cancel()
            self.refresh_task = None
        if self.leaderboard_message:
            await self.leaderboard_message.edit(
                content="Leaderboard closed.", view=None
            )
            self.leaderboard_message = None
            self.leaderboard_view = None
        await ctx.send("Leaderboard closed and refresh stopped.")

    # leaderboard sorted by K/D
    @commands.command()
    async def leaderboard_KD(self, ctx):
        if not self.bot.player_mmr:
            await ctx.send("No MMR data available yet.")
            return

        # Sort all players by MMR
        sorted_kd = sorted(
            self.bot.player_mmr.items(),
            key=lambda x: x[1].get(
                "kill_death_ratio", 0.0
            ),  # Default to 0.0 if key is missing
            reverse=True,
        )

        # Create the view for pages
        view = LeaderboardView(ctx, self.bot, sorted_kd, players_per_page=10)

        # Calculate the page indexes
        start_index = view.current_page * view.players_per_page
        end_index = start_index + view.players_per_page
        page_data = sorted_kd[start_index:end_index]

        names = []
        leaderboard_data = []
        for player_id, stats in page_data:
            user_data = users.find_one({"discord_id": str(player_id)})
            if user_data:
                riot_name = user_data.get("name", "Unknown")
                riot_tag = user_data.get("tag", "Unknown")
                names.append(f"{riot_name}#{riot_tag}")
            else:
                names.append("Unknown")

        # Stats for leaderboard
        for idx, ((player_id, stats), name) in enumerate(
            zip(page_data, names), start=start_index + 1
        ):
            mmr_value = stats["mmr"]
            wins = stats["wins"]
            losses = stats["losses"]
            matches_played = stats.get("matches_played", wins + losses)
            avg_cs = stats.get("average_combat_score", 0)
            kd_ratio = stats.get("kill_death_ratio", 0)
            win_percent = (wins / matches_played * 100) if matches_played > 0 else 0

            leaderboard_data.append(
                [
                    idx,
                    name,
                    f"{kd_ratio:.2f}",
                    mmr_value,
                    wins,
                    losses,
                    f"{win_percent:.2f}",
                    f"{avg_cs:.2f}",
                ]
            )

        table_output = t2a(
            header=["Rank", "User", "K/D", "MMR", "Wins", "Losses", "Win%", "Avg ACS"],
            body=leaderboard_data,
            first_col_heading=True,
            style=PresetStyle.thick_compact,
        )

        self.leaderboard_view_kd = LeaderboardViewKD(
            ctx, self.bot, sorted_kd, players_per_page=10, timeout=None
        )

        content = f"## K/D Leaderboard (Page {self.leaderboard_view_kd.current_page+1}/{self.leaderboard_view_kd.total_pages}) ##\n```\n{table_output}\n```"
        self.leaderboard_message_kd = await ctx.send(
            content=content, view=self.leaderboard_view_kd
        )  #########

        # Start the refresh
        if self.refresh_task_kd is not None:
            self.refresh_task_kd.cancel()
        self.refresh_task_kd = asyncio.create_task(self.periodic_refresh_kd())

    # Gives a leaderboard sorted by wins
    @commands.command()
    async def leaderboard_wins(self, ctx):
        if not self.bot.player_mmr:
            await ctx.send("No MMR data available yet.")
            return

        # Sort all players by wins
        sorted_wins = sorted(
            self.bot.player_mmr.items(),
            key=lambda x: x[1].get("wins", 0.0),  # Default to 0.0 if key is missing
            reverse=True,
        )

        # Create the view for pages
        view = LeaderboardView(ctx, self.bot, sorted_wins, players_per_page=10)

        # Calculate the page indexes
        start_index = view.current_page * view.players_per_page
        end_index = start_index + view.players_per_page
        page_data = sorted_wins[start_index:end_index]

        names = []
        leaderboard_data = []
        for player_id, stats in page_data:
            user_data = users.find_one({"discord_id": str(player_id)})
            if user_data:
                riot_name = user_data.get("name", "Unknown")
                riot_tag = user_data.get("tag", "Unknown")
                names.append(f"{riot_name}#{riot_tag}")
            else:
                names.append("Unknown")

        # Stats for leaderboard
        for idx, ((player_id, stats), name) in enumerate(
            zip(page_data, names), start=start_index + 1
        ):
            mmr_value = stats["mmr"]
            wins = stats["wins"]
            losses = stats["losses"]
            matches_played = stats.get("matches_played", wins + losses)
            avg_cs = stats.get("average_combat_score", 0)
            kd_ratio = stats.get("kill_death_ratio", 0)
            win_percent = (wins / matches_played * 100) if matches_played > 0 else 0

            leaderboard_data.append(
                [
                    idx,
                    name,
                    wins,
                    mmr_value,
                    losses,
                    f"{win_percent:.2f}",
                    f"{avg_cs:.2f}",
                    f"{kd_ratio:.2f}",
                ]
            )

        table_output = t2a(
            header=["Rank", "User", "Wins", "MMR", "Losses", "Win%", "Avg ACS", "K/D"],
            body=leaderboard_data,
            first_col_heading=True,
            style=PresetStyle.thick_compact,
        )

        self.leaderboard_view_wins = LeaderboardViewWins(
            ctx, self.bot, sorted_wins, players_per_page=10, timeout=None
        )

        content = f"## Wins Leaderboard (Page {self.leaderboard_view_wins.current_page+1}/{self.leaderboard_view_wins.total_pages}) ##\n```\n{table_output}\n```"
        self.leaderboard_message_wins = await ctx.send(
            content=content, view=self.leaderboard_view_wins
        )  #########

        # Start the refresh
        if self.refresh_task_wins is not None:
            self.refresh_task_wins.cancel()
        self.refresh_task_wins = asyncio.create_task(self.periodic_refresh_wins())

    # Gives a leaderboard sorted by ACS
    @commands.command()
    async def leaderboard_ACS(self, ctx):
        if not self.bot.player_mmr:
            await ctx.send("No MMR data available yet.")
            return

        # Sort all players by ACS
        sorted_acs = sorted(
            self.bot.player_mmr.items(),
            key=lambda x: x[1].get(
                "average_combat_score", 0.0
            ),  # Default to 0.0 if key is missing
            reverse=True,
        )

        # Create the view for pages
        view = LeaderboardView(ctx, self.bot, sorted_acs, players_per_page=10)

        # Calculate the page indexes
        start_index = view.current_page * view.players_per_page
        end_index = start_index + view.players_per_page
        page_data = sorted_acs[start_index:end_index]

        names = []
        leaderboard_data = []
        for player_id, stats in page_data:
            user_data = users.find_one({"discord_id": str(player_id)})
            if user_data:
                riot_name = user_data.get("name", "Unknown")
                riot_tag = user_data.get("tag", "Unknown")
                names.append(f"{riot_name}#{riot_tag}")
            else:
                names.append("Unknown")

        # Stats for leaderboard
        for idx, ((player_id, stats), name) in enumerate(
            zip(page_data, names), start=start_index + 1
        ):
            mmr_value = stats["mmr"]
            wins = stats["wins"]
            losses = stats["losses"]
            matches_played = stats.get("matches_played", wins + losses)
            avg_cs = stats.get("average_combat_score", 0)
            kd_ratio = stats.get("kill_death_ratio", 0)
            win_percent = (wins / matches_played * 100) if matches_played > 0 else 0

            leaderboard_data.append(
                [
                    idx,
                    name,
                    f"{avg_cs:.2f}",
                    mmr_value,
                    wins,
                    losses,
                    f"{win_percent:.2f}",
                    f"{kd_ratio:.2f}",
                ]
            )

        table_output = t2a(
            header=["Rank", "User", "Avg ACS", "MMR", "Wins", "Losses", "Win%", "K/D"],
            body=leaderboard_data,
            first_col_heading=True,
            style=PresetStyle.thick_compact,
        )

        self.leaderboard_view_acs = LeaderboardViewACS(
            ctx, self.bot, sorted_acs, players_per_page=10, timeout=None
        )

        content = f"## ACS Leaderboard (Page {self.leaderboard_view_acs.current_page+1}/{self.leaderboard_view_acs.total_pages}) ##\n```\n{table_output}\n```"
        self.leaderboard_message_acs = await ctx.send(
            content=content, view=self.leaderboard_view_acs
        )  #########

        # Start the refresh
        if self.refresh_task_acs is not None:
            self.refresh_task_acs.cancel()
        self.refresh_task_acs = asyncio.create_task(self.periodic_refresh_acs())

    @commands.command()
    @commands.has_role("Owner")  # Restrict this command to admins
    async def initialize_rounds(self, ctx):
        result = mmr_collection.update_many(
            {}, {"$set": {"total_rounds_played": 0}}  # Update all documents
        )
        await ctx.send(
            f"Initialized total_rounds_played for {result.modified_count} players."
        )

    # To recalculate average combat score after bug
    @commands.command()
    @commands.has_role("Owner")
    async def recalculate(self, ctx):
        players = mmr_collection.find()
        updated_count = 0
        for player in players:
            player_id = player.get("player_id")
            total_combat_score = player.get("total_combat_score", 0)
            total_rounds_played = player.get("total_rounds_played", 0)

            if total_rounds_played > 0:
                average_combat_score = total_combat_score / total_rounds_played
            else:
                average_combat_score = 0

            # Update the database
            mmr_collection.update_one(
                {"player_id": player_id},
                {"$set": {"average_combat_score": average_combat_score}},
            )

            # Update the in-memory player_mmr dictionary
            if player_id in self.bot.player_mmr:
                self.bot.player_mmr[player_id][
                    "average_combat_score"
                ] = average_combat_score
            else:
                # In case the player is not in player_mmr (should not happen)
                self.bot.player_mmr[player_id] = {
                    "average_combat_score": average_combat_score
                }

            updated_count += 1

        self.bot.load_mmr_data()

        await ctx.send(
            f"Recalculated average combat score for {updated_count} players."
        )

    # Simulate a queue
    @commands.command()
    async def simulate_queue(self, ctx):
        if self.bot.signup_view is None:
            self.bot.signup_view = SignupView(ctx, self.bot)
        if self.bot.signup_active:
            await ctx.send(
                "A signup is already in progress. Resetting queue for simulation."
            )
            self.bot.queue.clear()

        # Add 10 dummy players to the queue
        queue = [{"id": i, "name": f"Player{i}"} for i in range(1, 11)]

        # Assign default MMR to the dummy players and map IDs to names
        for player in queue:
            if player["id"] not in self.bot.player_mmr:
                self.bot.player_mmr[player["id"]] = {
                    "mmr": 1000,
                    "wins": 0,
                    "losses": 0,
                }
            self.bot.player_names[player["id"]] = player["name"]

        self.bot.save_mmr_data()

        self.bot.signup_active = True
        await ctx.send(
            f"Simulated full queue: {', '.join([player['name'] for player in queue])}"
        )

        # Proceed to the voting stage
        await ctx.send("The queue is now full, proceeding to the voting stage.")

        mode_vote = ModeVoteView(ctx, self.bot)
        await mode_vote.send_view()

    @commands.command()
    @commands.has_role("Owner")
    async def test(self, ctx):
        self.bot.signup_active = True
        self.bot.queue = []
        self.bot.captain1 = None
        self.bot.captain2 = None
        self.bot.team1 = []
        self.bot.team2 = []
        self.bot.chosen_mode = None
        self.bot.selected_map = None
        self.bot.match_not_reported = False
        self.bot.match_ongoing = False

        # Add 10 dummy players to the queue
        queue = [{"id": i, "name": f"TestPlayer{i}"} for i in range(1, 11)]
        for player in queue:
            self.bot.queue.append(player)
            if player["id"] not in self.bot.player_mmr:
                self.bot.player_mmr[player["id"]] = {
                    "mmr": random.randint(900,1100),  # Assign random MMR for testing
                    "wins": 0,
                    "losses": 0
                }
            self.bot.player_names[player["id"]] = player["name"]

        self.bot.save_mmr_data()
        await ctx.send("Simulated a full queue of 10 test players.")

        self.bot.chosen_mode = "Captains"
        await ctx.send("Forced chosen mode: Captains")

        # If captains chosen and not set, pick top 2 MMR as captains
        if self.bot.chosen_mode == "Captains":
            sorted_players = sorted(self.bot.queue, key=lambda p: self.bot.player_mmr[p["id"]]["mmr"], reverse=True)
            self.bot.captain1 = sorted_players[0]
            self.bot.captain2 = sorted_players[1]
            await ctx.send(f"Captains chosen automatically: Captain1={self.bot.captain1['name']}, Captain2={self.bot.captain2['name']}")

        # Force map pool
        from globals import official_maps
        chosen_maps = official_maps
        await ctx.send("Map pool chosen: Competitive")

        # Choose a random map from chosen_maps
        self.bot.selected_map = random.choice(chosen_maps)
        await ctx.send(f"Selected Map: {self.bot.selected_map}")

        if self.bot.chosen_mode == "Captains":
            remaining_players = [p for p in self.bot.queue if p not in [self.bot.captain1, self.bot.captain2]]
            remaining_players.sort(key=lambda p: self.bot.player_mmr[p["id"]]["mmr"], reverse=True)

            self.bot.team1 = [self.bot.captain1]
            self.bot.team2 = [self.bot.captain2]

            turn = 0
            for player in remaining_players:
                if turn % 2 == 0:
                    self.bot.team1.append(player)
                else:
                    self.bot.team2.append(player)
                turn += 1

            await ctx.send("Automatically assigned teams for captains mode.")

        # Mark the match as ongoing so we can report later if needed
        self.bot.match_ongoing = True

        # Finalize
        attackers = []
        from database import users
        for p in self.bot.team1:
            ud = users.find_one({"discord_id": str(p["id"])})
            mmr = self.bot.player_mmr[p["id"]]["mmr"]
            if ud:
                rn = ud.get("name", "Unknown")
                rt = ud.get("tag", "Unknown")
                attackers.append(f"{rn}#{rt} (MMR:{mmr})")
            else:
                attackers.append(f"{p['name']} (MMR:{mmr})")

        defenders = []
        for p in self.bot.team2:
            ud = users.find_one({"discord_id": str(p["id"])})
            mmr = self.bot.player_mmr[p["id"]]["mmr"]
            if ud:
                rn = ud.get("name", "Unknown")
                rt = ud.get("tag", "Unknown")
                defenders.append(f"{rn}#{rt} (MMR:{mmr})")
            else:
                defenders.append(f"{p['name']} (MMR:{mmr})")

        teams_embed = discord.Embed(
            title=f"Teams for the match on {self.bot.selected_map}",
            description="Good luck to both teams!",
            color=discord.Color.blue(),
        )
        teams_embed.add_field(
            name="**Attackers:**", value="\n".join(attackers), inline=False
        )
        teams_embed.add_field(
            name="**Defenders:**", value="\n".join(defenders), inline=False
        )
        await ctx.send(embed=teams_embed)

        await ctx.send("Setup complete! You can now `!report` after a match is done.")

    # Link Riot Account
    @commands.command()
    async def linkriot(self, ctx, *, riot_input):
        try:
            riot_name, riot_tag = riot_input.rsplit("#", 1)
        except ValueError:
            await ctx.send("Please provide your Riot ID in the format: `Name#Tag`")
            return

        data = requests.get(
            f"https://api.henrikdev.xyz/valorant/v1/account/{riot_name}/{riot_tag}",
            headers=headers,
            timeout=30,
        )
        user = data.json()

        if "data" not in user:
            await ctx.send(
                "Could not find your Riot account. Please check the name and tag."
            )
        else:
            # Update users collection
            discord_id = str(ctx.author.id)
            user_data = {
                "discord_id": discord_id,
                "name": riot_name.lower(),
                "tag": riot_tag.lower(),
            }
            users.update_one(
                {"discord_id": discord_id}, 
                {"$set": user_data}, 
                upsert=True
            )

            # Update name in mmr collections
            full_name = f"{riot_name}#{riot_tag}"
            mmr_collection.update_one(
                {"player_id": str(ctx.author.id)},
                {"$set": {"name": full_name}},
                upsert=False
            )

            tdm_mmr_collection.update_one(
                {"player_id": str(ctx.author.id)},
                {"$set": {"name": full_name}},
                upsert=False
            )

            # Check if user is in an active queue
            if self.bot.signup_active and any(p["id"] == discord_id for p in self.bot.queue):
                # Update the signup message if it exists
                if self.bot.current_signup_message:
                    riot_names = []
                    for player in self.bot.queue:
                        player_data = users.find_one({"discord_id": player["id"]})
                        if player_data:
                            player_riot_name = f"{player_data.get('name')}#{player_data.get('tag')}"
                            riot_names.append(player_riot_name)
                        else:
                            riot_names.append("Unknown")
                    
                    try:
                        await self.bot.current_signup_message.edit(
                            content="Click a button to manage your queue status!" + "\n" +
                            f"Current queue ({len(self.bot.queue)}/10): {', '.join(riot_names)}"
                        )
                    except discord.NotFound:
                        pass  # Message might have been deleted

                await ctx.send(
                    f"Successfully linked {riot_name}#{riot_tag} to your Discord account and updated your active queue entry."
                )
            else:
                await ctx.send(
                    f"Successfully linked {riot_name}#{riot_tag} to your Discord account."
                )

    # Set captain1
    @commands.command()
    @commands.has_role("blood")
    async def setcaptain1(self, ctx, *, riot_name_tag):
        try:
            riot_name, riot_tag = riot_name_tag.rsplit("#", 1)
        except ValueError:
            await ctx.send("Please provide the Riot ID in the format: `Name#Tag`")
            return

        # Find the player in the queue with matching Riot name and tag
        player_in_queue = None
        for player in self.bot.queue:
            user_data = users.find_one({"discord_id": str(player["id"])})
            if user_data:
                user_riot_name = user_data.get("name", "").lower()
                user_riot_tag = user_data.get("tag", "").lower()
                if (
                    user_riot_name == riot_name.lower()
                    and user_riot_tag == riot_tag.lower()
                ):
                    player_in_queue = player
                    break
        if not player_in_queue:
            await ctx.send(f"{riot_name}#{riot_tag} is not in the queue.")
            return

        if self.bot.captain2 and player_in_queue["id"] == self.bot.captain2["id"]:
            await ctx.send(f"{riot_name}#{riot_tag} is already selected as Captain 2.")
            return

        self.bot.captain1 = player_in_queue
        await ctx.send(f"Captain 1 set to {riot_name}#{riot_tag}")

    # Set captain2
    @commands.command()
    @commands.has_role("blood")
    async def setcaptain2(self, ctx, *, riot_name_tag):
        try:
            riot_name, riot_tag = riot_name_tag.rsplit("#", 1)
        except ValueError:
            await ctx.send("Please provide the Riot ID in the format: `Name#Tag`")
            return

        # Find the player in the queue with matching Riot name and tag
        player_in_queue = None
        for player in self.bot.queue:
            user_data = users.find_one({"discord_id": str(player["id"])})
            if user_data:
                user_riot_name = user_data.get("name", "").lower()
                user_riot_tag = user_data.get("tag", "").lower()
                if (
                    user_riot_name == riot_name.lower()
                    and user_riot_tag == riot_tag.lower()
                ):
                    player_in_queue = player
                    break
        if not player_in_queue:
            await ctx.send(f"{riot_name}#{riot_tag} is not in the queue.")
            return

        if self.bot.captain1 and player_in_queue["id"] == self.bot.captain1["id"]:
            await ctx.send(f"{riot_name}#{riot_tag} is already selected as Captain 1.")
            return

        self.bot.captain2 = player_in_queue
        await ctx.send(f"Captain 2 set to {riot_name}#{riot_tag}")

    # Set the bot to development mode
    @commands.command()
    @commands.has_role("blood")
    async def toggledev(self, ctx):
        if not self.dev_mode:
            self.dev_mode = True
            await ctx.send("Developer Mode Enabled")
            self.bot.command_prefix = "^"
            try:
                await self.bot.change_presence(
                    status=discord.Status.do_not_disturb,
                    activity=discord.Game(name="Bot Maintenance"),
                )
            except discord.HTTPException:
                pass
        else:
            self.dev_mode = False
            await ctx.send("Developer Mode Disabled")
            self.bot.command_prefix = "!"
            try:
                await self.bot.change_presence(
                    status=discord.Status.online, activity=discord.Game(name="10 Mans!")
                )
            except discord.HTTPException:
                pass

    # Stop the signup process, only owner can do this
    @commands.command()
    @commands.has_role("Owner")
    async def cancel(self, ctx):
        if not self.bot.signup_active:
            await ctx.send("No signup is active to cancel")
            return
            
        if self.bot.signup_view:
            self.bot.signup_view.cleanup()
            self.bot.signup_view = None
            
        self.bot.queue = []
        self.bot.current_signup_message = None
        self.bot.signup_active = False
        
        await ctx.send("Canceled Signup")
        
        try:
            await self.bot.match_channel.delete()
            await self.bot.match_role.delete()
        except discord.NotFound:
            pass

    @commands.command()
    async def force_draft(self, ctx):
        bot_queue = [
            {"name": "Player3", "id": 1},
            {"name": "Player4", "id": 2},
            {"name": "Player5", "id": 3},
            {"name": "Player6", "id": 4},
            {"name": "Player7", "id": 5},
            {"name": "Player8", "id": 6},
            {"name": "Player9", "id": 7},
            {"name": "Player10", "id": 8},
        ]
        for bot in bot_queue:
            self.bot.queue.append(bot)
        draft = CaptainsDraftingView(ctx, self.bot)
        await draft.send_current_draft_view()

    # Recalculate every stat from matches database
    @commands.command()
    @commands.has_role("Owner")
    async def reaggregate_matches(self, ctx):
        """
        Recalculate *all* players' stats AND MMR based on the entire history 
        of matches stored in the all_matches collection.
        """

        # 1) Clear or reset in-memory dictionaries for fresh aggregation
        #    This ensures everyone is starting from base MMR and 0 stats.
        self.bot.player_mmr.clear()
        self.bot.player_names.clear()

        # 2) Optionally, fetch all user docs from the DB to set base MMR = 1000
        #    Or you can just do it on the fly when we first see a user.
        all_users_cursor = users.find()
        for udoc in all_users_cursor:
            d_id = int(udoc["discord_id"])
            self.bot.player_mmr[d_id] = {
                "mmr": 1000,
                "wins": 0,
                "losses": 0,
                "total_combat_score": 0,
                "total_kills": 0,
                "total_deaths": 0,
                "matches_played": 0,
                "total_rounds_played": 0,
                "average_combat_score": 0,
                "kill_death_ratio": 0,
            }
            self.bot.player_names[d_id] = udoc["name"].lower()

        # 3) Pull out all the stored matches from the database
        #    IMPORTANT: Sort them in chronological order so MMR is updated match by match
        #    (Change "created_at" or "started_at" to match your actual field.)
        all_docs = all_matches.find().sort("started_at", 1)
        total_matches_processed = 0

        for match_doc in all_docs:
            total_matches_processed += 1

            # 3a) Identify total rounds from match['rounds']
            rounds_data = match_doc.get("rounds", [])
            total_rounds = len(rounds_data)

            # 3b) Identify the winning_team_id
            teams = match_doc.get("teams", [])
            winning_team_id = None
            for t in teams:
                if t.get("won"):
                    winning_team_id = t.get("team_id", "").lower()
                    break

            # 3c) Build sets (or lists) of players for each side
            match_players = match_doc.get("players", [])
            match_team_players = {"red": [], "blue": []}

            # We'll store them as a *list of dicts* so they mimic your usual "team" structure
            for pinfo in match_players:
                raw_team_id = pinfo.get("team_id", "").lower()
                name = pinfo.get("name", "").lower()
                tag = pinfo.get("tag", "").lower()

                # Look up the user to get the discord_id
                user_entry = users.find_one({"name": name, "tag": tag})
                if not user_entry:
                    # If user isn't found or not linked, skip or handle appropriately
                    continue

                d_id = int(user_entry["discord_id"])

                # We can build a "player dict" as your code normally does
                player_obj = {"id": d_id, "name": name}

                if raw_team_id in match_team_players:
                    match_team_players[raw_team_id].append(player_obj)

                # Also do the stats update here:
                # because this is effectively your "report" process
                update_stats(
                    pinfo, 
                    total_rounds,
                    self.bot.player_mmr,
                    self.bot.player_names
                )

            # 3d) Determine "winning_team" vs "losing_team" as *lists of dicts*
            winning_team = []
            losing_team = []

            # If the winning_team_id is "red", then winning_team = match_team_players["red"], etc.
            if winning_team_id == "red":
                winning_team = match_team_players["red"]
                losing_team = match_team_players["blue"]
            elif winning_team_id == "blue":
                winning_team = match_team_players["blue"]
                losing_team = match_team_players["red"]
            else:
                # If we can't determine a winning team, skip or handle error
                continue

            # 3e) Increment wins/losses for each player in memory
            for wplayer in winning_team:
                d_id = wplayer["id"]
                if d_id in self.bot.player_mmr:
                    self.bot.player_mmr[d_id]["wins"] = self.bot.player_mmr[d_id].get("wins", 0) + 1

            for lplayer in losing_team:
                d_id = lplayer["id"]
                if d_id in self.bot.player_mmr:
                    self.bot.player_mmr[d_id]["losses"] = self.bot.player_mmr[d_id].get("losses", 0) + 1


        for d_id, stats in self.bot.player_mmr.items():
            mmr_collection.update_one(
                {"player_id": d_id},
                {
                    "$set": {
                        "mmr": stats.get("mmr", 1000),
                        "wins": stats.get("wins", 0),
                        "losses": stats.get("losses", 0),
                        "total_combat_score": stats.get("total_combat_score", 0),
                        "total_kills": stats.get("total_kills", 0),
                        "total_deaths": stats.get("total_deaths", 0),
                        "matches_played": stats.get("matches_played", 0),
                        "total_rounds_played": stats.get("total_rounds_played", 0),
                        "average_combat_score": stats.get("average_combat_score", 0),
                        "kill_death_ratio": stats.get("kill_death_ratio", 0),
                        # store "name" if you want or any other fields
                    }
                },
                upsert=True
            )

        await ctx.send(f"Re-aggregated stats + MMR for all players from {total_matches_processed} stored matches!")

    # Custom Help Command
    @commands.command()
    async def help(self, ctx):
        help_embed = discord.Embed(
            title="Help Menu", 
            description="Duck's 10 Mans & TDM Commands:",
            color=discord.Color.green()
        )

        # General Commands
        help_embed.add_field(
            name="10 Mans Commands",
            value=(
                "**!signup** - Start a 10 mans signup session\n"
                "**!status** - View current queue status\n"
                "**!report** - Report match results and update MMR\n"
                "**!stats** - Check your MMR and match stats\n"
                "**!linkriot** - Link Riot account using `Name#Tag`\n"
            ),
            inline=False
        )

        # TDM Commands
        help_embed.add_field(
            name="TDM Commands",
            value=(
                "**!tdm** - Start a 3v3 TDM signup session\n"
                "**!tdmreport** - Report TDM match results\n"
                "**!tdmstats** - View TDM-specific stats\n"
            ),
            inline=False
        )

        # Leaderboard Commands  
        help_embed.add_field(
            name="Leaderboard Commands",
            value=(
                "**!leaderboard** - View MMR leaderboard\n"
                "**!leaderboard_KD** - View K/D leaderboard\n"
                "**!leaderboard_wins** - View wins leaderboard\n"
                "**!leaderboard_ACS** - View ACS leaderboard\n"
            ),
            inline=False
        )

        # Admin Commands
        help_embed.add_field(
            name="Admin Commands",
            value=(
                "**!setcaptain1** - Set Captain 1 using `Name#Tag`\n"
                "**!setcaptain2** - Set Captain 2 using `Name#Tag`\n"
                "**!cancel** - Cancel current 10 mans signup\n"
                "**!canceltdm** - Cancel current TDM signup\n"
                "**!toggledev** - Toggle Developer Mode\n"
            ),
            inline=False
        )

        # Footer
        help_embed.set_footer(text="Use commands with the ! prefix")

        await ctx.send(embed=help_embed)
