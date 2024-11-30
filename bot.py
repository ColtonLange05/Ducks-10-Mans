import discord
from discord.ext import commands
from discord.ui import Button, View, Select
import random
import asyncio
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import requests
import os

# FOR TESTING ONLY
mock_match_data = {
    "players": [
        {
            "name": "TestPlayer1",
            "tag": "1234",
            "team_id": "Red",
            "stats": {
                "score": 250,
                "kills": 15,
                "deaths": 10,
                "assists": 5
            }
        },
        {
            "name": "TestPlayer2",
            "tag": "1234",
            "team_id": "Red",
            "stats": {
                "score": 250,
                "kills": 15,
                "deaths": 10,
                "assists": 5
            }
        },
        {
            "name": "TestPlayer3",
            "tag": "1234",
            "team_id": "Red",
            "stats": {
                "score": 250,
                "kills": 15,
                "deaths": 10,
                "assists": 5
            }
        },
        {
            "name": "TestPlayer4",
            "tag": "1234",
            "team_id": "Red",
            "stats": {
                "score": 250,
                "kills": 15,
                "deaths": 10,
                "assists": 5
            }
        },
        {
            "name": "TestPlayer5",
            "tag": "1234",
            "team_id": "Red",
            "stats": {
                "score": 250,
                "kills": 15,
                "deaths": 10,
                "assists": 5
            }
        },
        {
            "name": "TestPlayer6",
            "tag": "1234",
            "team_id": "Blue",
            "stats": {
                "score": 250,
                "kills": 15,
                "deaths": 10,
                "assists": 5
            }
        },
        {
            "name": "TestPlayer7",
            "tag": "1234",
            "team_id": "Blue",
            "stats": {
                "score": 250,
                "kills": 15,
                "deaths": 10,
                "assists": 5
            }
        },
        {
            "name": "TestPlayer8",
            "tag": "1234",
            "team_id": "Blue",
            "stats": {
                "score": 250,
                "kills": 15,
                "deaths": 10,
                "assists": 5
            }
        },
        {
            "name": "TestPlayer9",
            "tag": "1234",
            "team_id": "Blue",
            "stats": {
                "score": 250,
                "kills": 15,
                "deaths": 10,
                "assists": 5
            }
        },
        {
            "name": "TestPlayer10",
            "tag": "1234",
            "team_id": "Blue",
            "stats": {
                "score": 250,
                "kills": 15,
                "deaths": 10,
                "assists": 5
            }
        },
    ],
    "teams": [
        {
            "team_id": "Red",
            "won": True
        },
        {
            "team_id": "Blue",
            "won": False
        }
    ]
}

class SignupView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.sign_up_button = Button(label=f"Sign Up ({len(queue)}/10)", style=discord.ButtonStyle.green)
        self.leave_queue_button = Button(label="Leave Queue", style=discord.ButtonStyle.red)
        self.add_item(self.sign_up_button)
        self.add_item(self.leave_queue_button)
        self.sign_up_button.callback = self.sign_up_callback
        self.leave_queue_button.callback = self.leave_queue_callback

    async def sign_up_callback(self, interaction: discord.Interaction):
        global signup_active
        existing_user = users.find_one({"discord_id": str(interaction.user.id)})
        if existing_user:
            if interaction.user.id not in [player["id"] for player in queue]:
                queue.append({"id": interaction.user.id, "name": interaction.user.name})
                if interaction.user.id not in player_mmr:
                    player_mmr[interaction.user.id] = {"mmr": 1000, "wins": 0, "losses": 0}
                player_names[interaction.user.id] = interaction.user.name

                self.sign_up_button.label = f"Sign Up ({len(queue)}/10)"
                await interaction.response.edit_message(content="Click a button to manage your queue status!", view=self)

                await interaction.followup.send(
                    f"{interaction.user.name} added to the queue! Current queue count: {len(queue)}",
                    ephemeral=True,
                )

                if len(queue) == 10:
                    await interaction.channel.send("The queue is now full, proceeding to the voting stage.")
                    cancel_signup_task()
                    await start_voting(interaction.channel)
            else:
                await interaction.response.send_message("You're already in the queue!", ephemeral=True)
        else:
            await interaction.response.send_message(
                "You must link your Riot account to queue. Use `!linkriot Name#Tag` to link your account",
                ephemeral=True
            )

    async def leave_queue_callback(self, interaction: discord.Interaction):
        queue[:] = [player for player in queue if player["id"] != interaction.user.id]
        self.sign_up_button.label = f"Sign Up ({len(queue)}/10)"
        await interaction.response.edit_message(content="Click a button to manage your queue status!", view=self)

        await interaction.followup.send(
            f"{interaction.user.name} removed from the queue! Current queue count: {len(queue)}",
            ephemeral=True,
        )

# MongoDB Connection
uri = "mongodb+srv://x4skinniestduck:8QZOdjPrrgJkRGPX@rapid.12llf.mongodb.net/?retryWrites=true&w=majority&appName=Rapid"
client = MongoClient(uri, server_api=ServerApi('1'))

# Set up bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Global variables to track signups and MMR
queue = []
team1 = []  
team2 = []  
signup_active = False  
player_mmr = {}  
player_names = {}  
votes = {"Balanced Teams": 0, "Captains": 0}
match_ongoing = False
dummy = False
signup_message = None
sign_up_button = None
leave_queue_button = None
view = None
selected_map_name = None
selected_captain1 = None
selected_captain2 = None
signup_refresh_task = None

# Initialize MongoDB Collections
db = client["valorant"]  
users = db["users"]       
mmr_collection = db["mmr_data"]  

# Initialize API
api_key = os.getenv("api_key")
headers = {
    "Authorization": api_key,
}
bot_token = os.getenv("bot_token")

official_maps = ["Haven", "Sunset", "Ascent", "Abyss", "Pearl", "Bind", "Split"]
all_maps = ["Bind", "Haven", "Split", "Ascent", "Icebox", "Breeze", "Fracture", "Pearl", "Lotus", "Sunset", "Abyss"]

def create_signup_view():
    sign_up_button = Button(label=f"Sign Up ({len(queue)}/10)", style=discord.ButtonStyle.green)
    leave_queue_button = Button(label="Leave Queue", style=discord.ButtonStyle.red)

    async def sign_up_callback(interaction: discord.Interaction):
        existing_user = users.find_one({"discord_id": str(interaction.user.id)})
        if existing_user:
            if interaction.user.id not in [player["id"] for player in queue]:
                queue.append({"id": interaction.user.id, "name": interaction.user.name})
                if interaction.user.id not in player_mmr:
                    player_mmr[interaction.user.id] = {"mmr": 1000, "wins": 0, "losses": 0}
                player_names[interaction.user.id] = interaction.user.name

                sign_up_button.label = f"Sign Up ({len(queue)}/10)"
                await interaction.response.edit_message(content="Click a button to manage your queue status!", view=view)

                await interaction.followup.send(
                    f"{interaction.user.name} added to the queue! Current queue count: {len(queue)}",
                    ephemeral=True,
                )

                if len(queue) == 10:
                    await interaction.channel.send("The queue is now full, proceeding to the voting stage.")
                    cancel_signup_task()
                    await start_voting(interaction.channel)
            else:
                await interaction.response.send_message("You're already in the queue!", ephemeral=True)
        else:
            await interaction.response.send_message("You must link your Riot account to queue. Use `!linkriot Name#Tag` to link your account", ephemeral=True)

    async def leave_queue_callback(interaction: discord.Interaction):
        # Remove the user from the queue
        queue[:] = [player for player in queue if player["id"] != interaction.user.id]
        sign_up_button.label = f"Sign Up ({len(queue)}/10)"
        await interaction.response.edit_message(content="Click a button to manage your queue status!", view=view)

        await interaction.followup.send(
            f"{interaction.user.name} removed from the queue! Current queue count: {len(queue)}",
            ephemeral=True,
        )

    sign_up_button.callback = sign_up_callback
    leave_queue_button.callback = leave_queue_callback

    view = View()
    view.add_item(sign_up_button)
    view.add_item(leave_queue_button)

    return view

# Function to refresh the signup message every minute
async def refresh_signup_message(ctx):
    global signup_message, signup_active, signup_view

    try:
        while signup_active:
            await asyncio.sleep(60)

            # Delete the old message
            try:
                await signup_message.delete()
            except discord.NotFound:
                pass

            # Send new signup message
            signup_message = await ctx.send("Click a button to manage your queue status!", view=signup_view)
    except asyncio.CancelledError:
        # Task was cancelled
        pass

# Function to cancel the signup refresh task
def cancel_signup_task():
    global signup_refresh_task
    if signup_refresh_task:
        signup_refresh_task.cancel()
        signup_refresh_task = None

async def vote_map(ctx):
    global queue, selected_map_name, team1, team2

    # vote between competitive maps or all maps
    map_pool_votes = {"Competitive Maps": 0, "All Maps": 0}
    voters = set()

    competitive_button = Button(label="Competitive Maps (0)", style=discord.ButtonStyle.green)
    all_maps_button = Button(label="All Maps (0)", style=discord.ButtonStyle.blurple)

    async def competitive_callback(interaction: discord.Interaction):
        # make user is in the queue and hasn't voted yet
        if interaction.user.id not in [player["id"] for player in queue]:
            await interaction.response.send_message("You must be in the queue to vote!", ephemeral=True)
            return
        if interaction.user.id in voters:
            await interaction.response.send_message("You have already voted!", ephemeral=True)
            return
        map_pool_votes["Competitive Maps"] += 1
        voters.add(interaction.user.id)
        competitive_button.label = f"Competitive Maps ({map_pool_votes['Competitive Maps']})"
        await interaction.message.edit(view=map_pool_view)
        await interaction.response.send_message("You voted for Competitive Maps.", ephemeral=True)

    async def all_maps_callback(interaction: discord.Interaction):
        # make sure the user is in the queue and hasn't voted yet
        if interaction.user.id not in [player["id"] for player in queue]:
            await interaction.response.send_message("You must be in the queue to vote!", ephemeral=True)
            return
        if interaction.user.id in voters:
            await interaction.response.send_message("You have already voted!", ephemeral=True)
            return
        map_pool_votes["All Maps"] += 1
        voters.add(interaction.user.id)
        all_maps_button.label = f"All Maps ({map_pool_votes['All Maps']})"
        await interaction.message.edit(view=map_pool_view)
        await interaction.response.send_message("You voted for All Maps.", ephemeral=True)

    competitive_button.callback = competitive_callback
    all_maps_button.callback = all_maps_callback

    map_pool_view = View()
    map_pool_view.add_item(competitive_button)
    map_pool_view.add_item(all_maps_button)

    await ctx.send("Vote for the map pool:", view=map_pool_view)
    await asyncio.sleep(10)

    if map_pool_votes["Competitive Maps"] >= map_pool_votes["All Maps"]:
        selected_map_pool = official_maps
        await ctx.send("Competitive Maps selected!")
    else:
        selected_map_pool = all_maps
        await ctx.send("All Maps selected!")

    map_choices = random.sample(selected_map_pool, 3)
    map_votes = {map_name: 0 for map_name in map_choices}
    voters = set()

    map_buttons = []
    for map_name in map_choices:
        button = Button(label=f"{map_name} (0)", style=discord.ButtonStyle.secondary)

        async def map_callback(interaction: discord.Interaction, map_name=map_name):
            if interaction.user.id not in [player["id"] for player in queue]:
                await interaction.response.send_message("You must be in the queue to vote!", ephemeral=True)
                return
            if interaction.user.id in voters:
                await interaction.response.send_message("You have already voted!", ephemeral=True)
                return
            map_votes[map_name] += 1
            voters.add(interaction.user.id)
            # Update the button label
            for btn in map_buttons:
                if btn.label.startswith(map_name):
                    btn.label = f"{map_name} ({map_votes[map_name]})"
            await interaction.message.edit(view=map_view)
            await interaction.response.send_message(f"You voted for {map_name}.", ephemeral=True)

        button.callback = map_callback
        map_buttons.append(button)

    map_view = View()
    for button in map_buttons:
        map_view.add_item(button)

    await ctx.send("Vote for the map to play:", view=map_view)
    await asyncio.sleep(10)

    winning_map = max(map_votes, key=map_votes.get)
    selected_map_name = winning_map
    await ctx.send(f"The selected map is **{winning_map}**!")

    teams_embed = discord.Embed(
        title=f"Teams for the match on {winning_map}",
        description="Good luck to both teams!",
        color=discord.Color.blue()
    )

    attackers = []
    for player in team1:
        user_data = users.find_one({"discord_id": str(player["id"])})
        mmr = player_mmr.get(player["id"], {}).get("mmr", 1000)
        if user_data:
            riot_name = user_data.get("name", "Unknown")
            riot_tag = user_data.get("tag", "Unknown")
            attackers.append(f"{riot_name}#{riot_tag} (MMR: {mmr})")
        else:
            attackers.append(f"{player['name']} (MMR: {mmr})")

    defenders = []
    for player in team2:
        user_data = users.find_one({"discord_id": str(player["id"])})
        mmr = player_mmr.get(player["id"], {}).get("mmr", 1000)
        if user_data:
            riot_name = user_data.get("name", "Unknown")
            riot_tag = user_data.get("tag", "Unknown")
            defenders.append(f"{riot_name}#{riot_tag} (MMR: {mmr})")
        else:
            defenders.append(f"{player['name']} (MMR: {mmr})")

    teams_embed.add_field(
        name="**Attackers:**",
        value='\n'.join(attackers),
        inline=False
    )
    teams_embed.add_field(
        name="**Defenders:**",
        value='\n'.join(defenders),
        inline=False
    )

    # Send the finalized teams again, this time in a readable message
    await ctx.send(embed=teams_embed)

    await ctx.send("Start the match, then use !report to finalize results")

# Load data from mongodb
def load_mmr_data():
    global player_mmr, player_names
    player_mmr = {}
    player_names = {}

    for doc in mmr_collection.find():
        player_id = int(doc['player_id'])
        player_mmr[player_id] = {
            'mmr': doc.get('mmr', 1000),
            'wins': doc.get('wins', 0),
            'losses': doc.get('losses', 0),
            'total_combat_score': doc.get('total_combat_score', 0),
            'total_kills': doc.get('total_kills', 0),
            'total_deaths': doc.get('total_deaths', 0),
            'matches_played': doc.get('matches_played', 0),
            'average_combat_score': doc.get('average_combat_score', 0),
            'kill_death_ratio': doc.get('kill_death_ratio', 0)
        }
        player_names[player_id] = doc.get('name', '')

# Save mmr
def save_mmr_data():
    for player_id, stats in player_mmr.items():
        mmr_collection.update_one(
            {'player_id': player_id},
            {'$set': {
                'mmr': stats['mmr'],
                'wins': stats['wins'],
                'losses': stats['losses'],
                'name': player_names.get(player_id, ''),
                'total_combat_score': stats.get('total_combat_score', 0),
                'total_kills': stats.get('total_kills', 0),
                'total_deaths': stats.get('total_deaths', 0),
                'matches_played': stats.get('matches_played', 0),
                'average_combat_score': stats.get('average_combat_score', 0),
                'kill_death_ratio': stats.get('kill_death_ratio', 0)
            }},
            upsert=True
        )

load_mmr_data()

# adjust MMR and track wins/losses
def adjust_mmr(winning_team, losing_team):
    MMR_GAIN = 25
    MMR_LOSS = 25

    for player in winning_team:
        player_id = player["id"]
        if player_id in player_mmr:
            player_mmr[player_id]["mmr"] += MMR_GAIN
            player_mmr[player_id]["wins"] += 1 

    for player in losing_team:
        player_id = player["id"]
        if player_id in player_mmr:
            player_mmr[player_id]["mmr"] -= MMR_LOSS
            if player_mmr[player_id]["mmr"] < 0:
                player_mmr[player_id]["mmr"] = 0
            player_mmr[player_id]["losses"] += 1 

    save_mmr_data()

def balanced_teams(players):
    global match_ongoing
    players.sort(key=lambda p: player_mmr[p["id"]]["mmr"], reverse=True)
    match_ongoing = True
    team1, team2 = [], []
    team1_mmr, team2_mmr = 0, 0

    for player in players:
        if team1_mmr <= team2_mmr:
            team1.append(player)
            team1_mmr += player_mmr[player["id"]]["mmr"]
        else:
            team2.append(player)
            team2_mmr += player_mmr[player["id"]]["mmr"]

    return team1, team2

async def captains_mode(ctx):
    global team1, team2, match_ongoing, selected_captain1, selected_captain2, signup_active

    captains = []
    if selected_captain1:
        captains.append(selected_captain1)
    if selected_captain2:
        captains.append(selected_captain2)

    # Fill captains with highest MMR if not set
    if len(captains) < 2:
        sorted_players = sorted(queue, key=lambda p: player_mmr[p["id"]]["mmr"], reverse=True)
        for player in sorted_players:
            if player not in captains:
                captains.append(player)
                if len(captains) == 2:
                    break

    captain1, captain2 = captains[:2]

    await ctx.send(
        f"**Captains Mode Selected:**\n"
        f"Captain 1: {captain1['name']} (MMR: {player_mmr[captain1['id']]['mmr']})\n"
        f"Captain 2: {captain2['name']} (MMR: {player_mmr[captain2['id']]['mmr']})"
    )

    # Initialize teams with captains
    team1, team2 = [captain1], [captain2]

    remaining_players = [p for p in queue if p not in [captain1, captain2]]

    # The correct pick order
    pick_order = [
        captain1["id"],  # Use IDs for accurate comparison
        captain2["id"],
        captain2["id"],
        captain1["id"],
        captain1["id"],
        captain2["id"],
        captain2["id"],
        captain1["id"],
    ]

    pick_count = 0

    await captains_pick_next(ctx, remaining_players, captains, pick_order, pick_count, team1, team2)

async def captains_pick_next(ctx, remaining_players, captains, pick_order, pick_count):
    global team1, team2, signup_active, match_ongoing, selected_captain1, selected_captain2, queue, votes, selected_map_name

    if not remaining_players:
        # Finalize teams
        captain1 = captains[0]
        captain2 = captains[1]
        await ctx.send(
            f"**Final Teams:**\n"
            f"Attackers (Captain: {captain1['name']}): {', '.join([p['name'] for p in team1])}\n"
            f"Defenders (Captain: {captain2['name']}): {', '.join([p['name'] for p in team2])}"
        )
        signup_active = False
        match_ongoing = True

        # Reset the selected captains
        selected_captain1 = None
        selected_captain2 = None

        await vote_map(ctx)
        return

    current_captain_id = pick_order[pick_count]
    current_captain = next((c for c in captains if c["id"] == current_captain_id), None)
    await ctx.send(f"Remaining players: {', '.join([p['name'] for p in remaining_players])}")
    await ctx.send(f"{current_captain['name']}, it's your turn to pick!")

    # Create the dropdown menu
    options = [
        discord.SelectOption(label=p['name'], value=str(p['id']))
        for p in remaining_players
    ]

    select = Select(
        placeholder="Select a player to pick",
        options=options,
    )

    async def select_callback(interaction: discord.Interaction):
        if interaction.user.id != current_captain_id:
            await interaction.response.send_message("It's not your turn to pick.", ephemeral=True)
            return

        selected_player_id = int(select.values[0])
        player_dict = next((p for p in remaining_players if p["id"] == selected_player_id), None)
        if not player_dict:
            await interaction.response.send_message("Player not available. Please select a valid player.", ephemeral=True)
            return

        # Add the player to the appropriate team
        if current_captain_id == captains[0]["id"]:
            team1.append(player_dict)
        else:
            team2.append(player_dict)

        remaining_players.remove(player_dict)
        select.disabled = True
        await interaction.response.edit_message(content=f"{current_captain['name']} picked {player_dict['name']}.", view=None)
        await interaction.followup.send(f"You picked {player_dict['name']}.", ephemeral=True)

        # Proceed to the next pick
        await captains_pick_next(ctx, remaining_players, captains, pick_order, pick_count + 1)

    select.callback = select_callback

    view = View()
    view.add_item(select)

    message = await ctx.send(f"{current_captain['name']}, please pick a player:", view=view)

    # Wait for the captain to make a selection or timeout
    try:
        await bot.wait_for(
            "interaction",
            check=lambda i: i.data.get('component_type') == 3 and i.user.id == current_captain_id,
            timeout=60,
        )
    except asyncio.TimeoutError:
        await ctx.send(f"{current_captain['name']} took too long to pick. Drafting canceled.")

        # Reset variables
        signup_active = False
        match_ongoing = False
        selected_captain1 = None
        selected_captain2 = None
        selected_map_name = None
        votes = {"Balanced Teams": 0, "Captains": 0}

        # Clear teams and queue
        team1.clear()
        team2.clear()
        queue.clear()

        # Cancel any ongoing tasks
        cancel_signup_task()

        # Reopen signup
        await signup(ctx)
        return

async def start_voting(channel):
    global votes, dummy, match_ongoing
    votes = {"Balanced Teams": 0, "Captains": 0} 
    voters = set() 

    # Create voting buttons with labels
    balanced_button = Button(label="Balanced Teams (0)", style=discord.ButtonStyle.green)
    captains_button = Button(label="Captains (0)", style=discord.ButtonStyle.blurple)

    async def balanced_callback(interaction: discord.Interaction):
        # make sure the user is in the queue
        if interaction.user.id not in [player["id"] for player in queue]:
            await interaction.response.send_message("You must be in the queue to vote!", ephemeral=True)
            return
        # make sure the user has not already voted
        if interaction.user.id in voters:
            await interaction.response.send_message("You have already voted!", ephemeral=True)
            return

        votes["Balanced Teams"] += 1
        voters.add(interaction.user.id)
        balanced_button.label = f"Balanced Teams ({votes['Balanced Teams']})" 
        await interaction.message.edit(view=voting_view) 
        await interaction.response.send_message(
            f"Voted for Balanced Teams! Current votes: {votes['Balanced Teams']}",
            ephemeral=True,
        )

    async def captains_callback(interaction: discord.Interaction):
        if interaction.user.id not in [player["id"] for player in queue]:
            await interaction.response.send_message("You must be in the queue to vote!", ephemeral=True)
            return
        if interaction.user.id in voters:
            await interaction.response.send_message("You have already voted!", ephemeral=True)
            return

        votes["Captains"] += 1
        voters.add(interaction.user.id)  
        captains_button.label = f"Captains ({votes['Captains']})"  
        await interaction.message.edit(view=voting_view) 
        await interaction.response.send_message(
            f"Voted for Captains! Current votes: {votes['Captains']}",
            ephemeral=True,
        )

    balanced_button.callback = balanced_callback
    captains_button.callback = captains_callback

    voting_view = View()
    voting_view.add_item(balanced_button)
    voting_view.add_item(captains_button)

    await channel.send("Vote for how teams will be decided:", view=voting_view)

    await asyncio.sleep(15)

    # Determine voting results
    if dummy == True:
        await channel.send("Balanced Teams wins the vote!")
        await balanced_teams_logic(channel)
    else:
        if votes["Balanced Teams"] > votes["Captains"]:
            await channel.send("Balanced Teams wins the vote!")
            await balanced_teams_logic(channel)
        elif votes["Captains"] > votes["Balanced Teams"]:
            await channel.send("Captains wins the vote!")
            await captains_mode(channel)
        else:
            decision = "Balanced Teams" if random.choice([True, False]) else "Captains"
            await channel.send(f"It's a tie! Flipping a coin... {decision} wins!")
            if decision == "Balanced Teams":
                await balanced_teams_logic(channel) 
            else:
                await captains_mode(channel) 
    match_ongoing = True
    dummy = False

async def balanced_teams_logic(ctx):
    global team1, team2, match_ongoing
    team1, team2 = balanced_teams(queue)
    await ctx.send(f"**Balanced Teams:**\nAttackers: {', '.join([p['name'] for p in team1])}\nDefenders: {', '.join([p['name'] for p in team2])}")
    signup_active = False  
    match_ongoing = True

    # vote for maps next
    await vote_map(ctx)

# Signup Command
@bot.command()
async def signup(ctx):
    global signup_active, team1, team2, signup_message, signup_refresh_task, signup_view

    if signup_active:
        await ctx.send("A signup is already in progress. Please wait for it to complete.")
        return

    signup_active = True
    queue.clear()
    team1.clear()
    team2.clear()

    signup_view = SignupView()
    signup_message = await ctx.send("Click a button to manage your queue status!", view=signup_view)

    # Start the background task to refresh the signup message
    signup_refresh_task = asyncio.create_task(refresh_signup_message(ctx))

# Command to join queue without pressing the button
@bot.command()
async def join(ctx):
    global queue, signup_message, signup_active, signup_view

    if not signup_active:
        await ctx.send("No signup is currently active.")
        return

    existing_user = users.find_one({"discord_id": str(ctx.author.id)})
    if existing_user:
        if ctx.author.id not in [player["id"] for player in queue]:
            queue.append({"id": ctx.author.id, "name": ctx.author.name})
            if ctx.author.id not in player_mmr:
                player_mmr[ctx.author.id] = {"mmr": 1000, "wins": 0, "losses": 0}
            player_names[ctx.author.id] = ctx.author.name

            # Update the button label
            signup_view.sign_up_button.label = f"Sign Up ({len(queue)}/10)"
            await signup_message.edit(content="Click a button to manage your queue status!", view=signup_view)

            await ctx.send(f"{ctx.author.name} added to the queue! Current queue count: {len(queue)}")

            if len(queue) == 10:
                await ctx.send("The queue is now full, proceeding to the voting stage.")
                cancel_signup_task()
                await start_voting(ctx.channel)
                signup_active = False
        else:
            await ctx.send("You're already in the queue!")
    else:
        await ctx.send("You must link your Riot account to join the queue. Use `!linkriot Name#Tag` to link your account.")

# Leave queue command without pressing button
@bot.command()
async def leave(ctx):
    global queue, signup_message, signup_active, signup_view

    if not signup_active:
        await ctx.send("No signup is currently active.")
        return

    if ctx.author.id in [player["id"] for player in queue]:
        queue[:] = [player for player in queue if player["id"] != ctx.author.id]
        signup_view.sign_up_button.label = f"Sign Up ({len(queue)}/10)"
        await signup_message.edit(content="Click a button to manage your queue status!", view=signup_view)
        await ctx.send(f"{ctx.author.name} removed from the queue! Current queue count: {len(queue)}")
    else:
        await ctx.send("You're not in the queue.")

@bot.command()
async def status(ctx):
    global signup_active, queue

    if not signup_active:
        await ctx.send("No signup is currently active.")
        return

    if not queue:
        await ctx.send("The queue is currently empty.")
        return

    riot_names = []
    for player in queue:
        discord_id = player['id']
        user_data = users.find_one({"discord_id": str(discord_id)})
        if user_data:
            riot_name = user_data.get("name", "Unknown")
            riot_names.append(riot_name)
        else:
            # INCASE SOMEONE HASN'T LINKED ACCOUNT
            riot_names.append("Unknown")

    queue_status = ", ".join(riot_names)
    await ctx.send(f"Current queue ({len(queue)}/10): {queue_status}")

# Report the match
@bot.command()
async def report(ctx):
    global match_ongoing, queue, team1, team2, selected_map_name

    # Retrieve current_user at the beginning
    current_user = users.find_one({"discord_id": str(ctx.author.id)})
    if not current_user:
        await ctx.send("You need to link your Riot account first using `!linkriot Name#Tag`")
        return

    name = current_user.get("name")
    tag = current_user.get("tag")
    region = "na"
    platform = "pc"

    url = f"https://api.henrikdev.xyz/valorant/v4/matches/{region}/{platform}/{name}/{tag}"
    response = requests.get(url, headers=headers)
    match_data = response.json()

    # Ensure match_data contains 'data' and it's not empty
    if "data" not in match_data or not match_data["data"]:
        await ctx.send("Could not retrieve match data.")
        return

    match = match_data["data"][0]
    metadata = match.get("metadata", {})
    map_name = metadata.get("map", {}).get("name", "").lower()

    testing_mode = False  # Set to True while testing

    if testing_mode:
        match = mock_match_data
        match_ongoing = True

        queue = []
        team1 = []
        team2 = []
        for i in range(1, 11):
            player_id = i  
            player_name = f"TestPlayer{i}"

            users.update_one(
                {"discord_id": str(player_id)},
                {"$set": {"name": player_name, "tag": "1234"}},
                upsert=True
            )

            player = {"id": player_id, "name": player_name}
            queue.append(player)
            if i <= 5:
                team1.append(player)
            else:
                team2.append(player)

            if player_id not in player_mmr:
                player_mmr[player_id] = {"mmr": 1000, "wins": 0, "losses": 0}
            player_names[player_id] = player_name
    else:
        if not match_ongoing:
            await ctx.send("No match is currently active, use `!signup` to start one")
            return

        if not selected_map_name:
            await ctx.send("No map was selected for this match.")
            return

        if selected_map_name.lower() != map_name:
            await ctx.send("Map doesn't match your most recent match. Unable to report it.")
            return

        current_user = users.find_one({"discord_id": str(ctx.author.id)})
        if not current_user:
            await ctx.send("You need to link your Riot account first using `!linkriot Name#Tag`")
            return

        if "data" not in match_data or not match_data["data"]:
            await ctx.send("Could not retrieve match data.")
            return

        match = match_data["data"][0] 

    match_players = match.get("players", [])
    if not match_players:
        await ctx.send("No players found in match data.")
        return

    queue_riot_ids = set()
    for player in queue:
        user_data = users.find_one({"discord_id": str(player["id"])})
        if user_data:
            player_name = user_data.get("name").lower()
            player_tag = user_data.get("tag").lower()
            queue_riot_ids.add((player_name, player_tag))

    # get the list of players in the match
    match_player_names = set()
    for player in match_players:
        player_name = player.get("name", "").lower()
        player_tag = player.get("tag", "").lower()
        match_player_names.add((player_name, player_tag))

    if not queue_riot_ids.issubset(match_player_names):
        await ctx.send("The most recent match does not match the 10-man's match.")
        return

    # Determine which team won
    teams = match.get("teams", [])
    if not teams:
        await ctx.send("No team data found in match data.")
        return

    winning_team_id = None
    for team in teams:
        if team.get("won"):
            winning_team_id = team.get("team_id")
            break

    if not winning_team_id:
        await ctx.send("Could not determine the winning team.")
        return

    match_team_players = {
        'Red': set(),
        'Blue': set()
    }

    for player in match_players:
        team_id = player.get("team_id")
        player_name = player.get("name", "").lower()
        player_tag = player.get("tag", "").lower()
        if team_id in match_team_players:
            match_team_players[team_id].add((player_name, player_tag))

    team1_riot_ids = set()
    for player in team1:
        user_data = users.find_one({"discord_id": str(player["id"])})
        if user_data:
            player_name = user_data.get("name", "").lower()
            player_tag = user_data.get("tag").lower()
            team1_riot_ids.add((player_name, player_tag))

    team2_riot_ids = set()
    for player in team2:
        user_data = users.find_one({"discord_id": str(player["id"])})
        if user_data:
            player_name = user_data.get("name", "").lower()
            player_tag = user_data.get("tag").lower()
            team2_riot_ids.add((player_name, player_tag))

    winning_match_team_players = match_team_players.get(winning_team_id, set())

    if winning_match_team_players == team1_riot_ids:
        winning_team = team1
        losing_team = team2
    elif winning_match_team_players == team2_riot_ids:
        winning_team = team2
        losing_team = team1
    else:
        await ctx.send("Could not match the winning team to our teams.")
        return

    # Adjust MMR
    adjust_mmr(winning_team, losing_team)
    await ctx.send("MMR Updated!")

    # Update stats
    for player_stats in match_players:
        update_stats(player_stats)

    await ctx.send("Player stats updated!")
    match_ongoing = False 

# Update stats
def update_stats(player_stats):
    name = player_stats.get("name")
    tag = player_stats.get("tag")

    user_entry = users.find_one({"name": name, "tag": tag})
    if not user_entry:
        print(f"Player {name}#{tag} not linked to any Discord account.")
        return

    discord_id = int(user_entry.get("discord_id"))

    # Get the stats
    stats = player_stats.get("stats", {})
    score = stats.get("score", 0)
    kills = stats.get("kills", 0)
    deaths = stats.get("deaths", 0)
    assists = stats.get("assists", 0)

    # Update stats
    if discord_id in player_mmr:
        player_data = player_mmr[discord_id]
        total_matches = player_data.get("matches_played", 0) + 1
        total_combat_score = player_data.get("total_combat_score", 0) + score
        total_kills = player_data.get("total_kills", 0) + kills
        total_deaths = player_data.get("total_deaths", 0) + deaths

        average_combat_score = total_combat_score / total_matches
        kill_death_ratio = total_kills / total_deaths if total_deaths > 0 else total_kills

        player_mmr[discord_id].update({
            "total_combat_score": total_combat_score,
            "total_kills": total_kills,
            "total_deaths": total_deaths,
            "matches_played": total_matches,
            "average_combat_score": average_combat_score,
            "kill_death_ratio": kill_death_ratio
        })

        mmr_collection.update_one(
            {'player_id': discord_id},
            {'$set': {
                'total_combat_score': total_combat_score,
                'total_kills': total_kills,
                'total_deaths': total_deaths,
                'matches_played': total_matches,
                'average_combat_score': average_combat_score,
                'kill_death_ratio': kill_death_ratio
            }},
            upsert=True
        )
    else:
        total_matches = 1
        total_combat_score = score
        total_kills = kills
        total_deaths = deaths
        average_combat_score = score
        kill_death_ratio = kills / deaths if deaths > 0 else kills

        player_mmr[discord_id] = {
            'mmr': 1000,  
            'wins': 0,
            'losses': 0,
            'total_combat_score': total_combat_score,
            'total_kills': total_kills,
            'total_deaths': total_deaths,
            'matches_played': total_matches,
            'average_combat_score': average_combat_score,
            'kill_death_ratio': kill_death_ratio
        }
        player_names[discord_id] = name

        mmr_collection.update_one(
            {'player_id': discord_id},
            {'$set': {
                'mmr': 1000,
                'wins': 0,
                'losses': 0,
                'name': name,
                'total_combat_score': total_combat_score,
                'total_kills': total_kills,
                'total_deaths': total_deaths,
                'matches_played': total_matches,
                'average_combat_score': average_combat_score,
                'kill_death_ratio': kill_death_ratio
            }},
            upsert=True
        )


# Allow players to check their MMR and stats
@bot.command()
async def stats(ctx):
    player_id = ctx.author.id  
    if player_id in player_mmr:
        stats = player_mmr[player_id]
        mmr_value = stats["mmr"]
        wins = stats["wins"]
        losses = stats["losses"]
        matches_played = stats.get('matches_played', wins + losses)
        avg_cs = stats.get('average_combat_score', 0)
        kd_ratio = stats.get('kill_death_ratio', 0)
        win_percent = (wins / matches_played) * 100 if matches_played > 0 else 0

        await ctx.send(
            f"**{ctx.author.name}'s Stats:**\n"
            f"MMR: {mmr_value}\n"
            f"Wins: {wins}\n"
            f"Losses: {losses}\n"
            f"Win%: {win_percent:.2f}%\n"
            f"Matches Played: {matches_played}\n"
            f"Average Combat Score: {avg_cs:.2f}\n"
            f"Kill/Death Ratio: {kd_ratio:.2f}"
        )
    else:
        await ctx.send("You do not have an MMR yet. Participate in matches to earn one!")

# Display leaderboard
@bot.command()
async def leaderboard(ctx):
    if not player_mmr: 
        await ctx.send("No MMR data available yet.")
        return

    # Sort players by MMR and take the top 10
    sorted_mmr = sorted(player_mmr.items(), key=lambda x: x[1]["mmr"], reverse=True)[:10]

    leaderboard_entries = []
    for idx, (player_id, stats) in enumerate(sorted_mmr, start=1):
        name = player_names.get(player_id, "Unknown")
        mmr_value = stats["mmr"]
        wins = stats["wins"]
        losses = stats["losses"]
        matches_played = stats.get('matches_played', wins + losses)
        avg_cs = stats.get('average_combat_score', 0)
        kd_ratio = stats.get('kill_death_ratio', 0)
        win_percent = (wins / matches_played) * 100 if matches_played > 0 else 0

        leaderboard_entries.append(
            f"{idx}. {name} - MMR: {mmr_value}, Wins: {wins}, Losses: {losses}, "
            f"Win%: {win_percent:.1f}%, Avg CS: {avg_cs:.2f}, K/D: {kd_ratio:.2f}"
        )

    leaderboard_text = "\n".join(leaderboard_entries)
    await ctx.send(f"**MMR Leaderboard (Top 10 Players):**\n{leaderboard_text}")

# Simulate a queue
@bot.command()
async def simulate_queue(ctx):
    global queue, signup_active, team1, team2, dummy
    dummy = True

    if signup_active:
        await ctx.send("A signup is already in progress. Resetting queue for simulation.")
        queue.clear()  

    # Clear teams
    team1.clear()
    team2.clear()

    # Add 10 dummy players to the queue
    queue = [{"id": i, "name": f"Player{i}"} for i in range(1, 11)]  # Use dummy IDs

    # Assign default MMR to the dummy players and map IDs to names
    for player in queue:
        if player["id"] not in player_mmr:
            player_mmr[player["id"]] = {"mmr": 1000, "wins": 0, "losses": 0}  
        player_names[player["id"]] = player["name"]  

    save_mmr_data()  

    signup_active = True  
    await ctx.send(f"Simulated full queue: {', '.join([player['name'] for player in queue])}")

    # Proceed to the voting stage
    await ctx.send("The queue is now full, proceeding to the voting stage.")
    await start_voting(ctx.channel)

# Link Riot Account
@bot.command()
async def linkriot(ctx, *, riot_input):
    try:
        riot_name, riot_tag = riot_input.rsplit("#", 1) 
    except ValueError:
        await ctx.send("Please provide your Riot ID in the format: `Name#Tag`")
        return

    existing_user = users.find_one({"discord_id": str(ctx.author.id)})
    if not existing_user:
        data = requests.get(f"https://api.henrikdev.xyz/valorant/v1/account/{riot_name}/{riot_tag}", headers=headers)
        user = data.json()
        
        if "data" not in user:
            await ctx.send("Could not find your Riot account. Please check the name and tag.")
        else:
            user_data = {
                "discord_id": str(ctx.author.id),
                "name": riot_name,
                "tag": riot_tag,
            }
            users.update_one(
                {"discord_id": str(ctx.author.id)},
                {"$set": user_data},
                upsert=True
            )
            await ctx.send(f"Successfully linked {riot_name}#{riot_tag}")
    else:
        await ctx.send("Your account is already linked. Use `!unlink` to unlink your account.")

# Unlink Account
@bot.command()
async def unlink(ctx):
    result = users.delete_one({"discord_id": str(ctx.author.id)})
    if result.deleted_count > 0:
        await ctx.send("Successfully unlinked your account")
    else:
        await ctx.send("Could not find an account linked to you")


# Set captain1
@bot.command()
@commands.has_role("blood")
async def setcaptain1(ctx, *, riot_name_tag):
    global selected_captain1, selected_captain2, queue
    try:
        riot_name, riot_tag = riot_name_tag.rsplit("#", 1)
    except ValueError:
        await ctx.send("Please provide the Riot ID in the format: `Name#Tag`")
        return

    # Find the player in the queue with matching Riot name and tag
    player_in_queue = None
    for player in queue:
        user_data = users.find_one({"discord_id": str(player["id"])})
        if user_data:
            user_riot_name = user_data.get("name", "").lower()
            user_riot_tag = user_data.get("tag", "").lower()
            if user_riot_name == riot_name.lower() and user_riot_tag == riot_tag.lower():
                player_in_queue = player
                break
    if not player_in_queue:
        await ctx.send(f"{riot_name}#{riot_tag} is not in the queue.")
        return

    if selected_captain2 and player_in_queue == selected_captain2:
        await ctx.send(f"{riot_name}#{riot_tag} is already selected as Captain 2.")
        return

    selected_captain1 = player_in_queue
    await ctx.send(f"Captain 1 set to {riot_name}#{riot_tag}")
    
# Set captain2
@bot.command()
@commands.has_role("blood")
async def setcaptain2(ctx, *, riot_name_tag):
    global selected_captain1, selected_captain2, queue
    try:
        riot_name, riot_tag = riot_name_tag.rsplit("#", 1)
    except ValueError:
        await ctx.send("Please provide the Riot ID in the format: `Name#Tag`")
        return

    # Find the player in the queue with matching Riot name and tag
    player_in_queue = None
    for player in queue:
        user_data = users.find_one({"discord_id": str(player["id"])})
        if user_data:
            user_riot_name = user_data.get("name", "").lower()
            user_riot_tag = user_data.get("tag", "").lower()
            if user_riot_name == riot_name.lower() and user_riot_tag == riot_tag.lower():
                player_in_queue = player
                break
    if not player_in_queue:
        await ctx.send(f"{riot_name}#{riot_tag} is not in the queue.")
        return

    if selected_captain1 and player_in_queue == selected_captain1:
        await ctx.send(f"{riot_name}#{riot_tag} is already selected as Captain 1.")
        return

    selected_captain2 = player_in_queue
    await ctx.send(f"Captain 2 set to {riot_name}#{riot_tag}")

# Custom Help Command
@bot.command()
async def help(ctx):
    help_embed = discord.Embed(
        title="Help Menu",
        description="Duck's 10 Mans Commands:",
        color=discord.Color.blue()
    )
    
    help_embed.add_field(name="!signup", value="Start a signup session for matches.", inline=False)
    help_embed.add_field(name="!report", value="Report the most recent match and update MMR.", inline=False)
    help_embed.add_field(name="!stats", value="Check your MMR and match stats.", inline=False)
    help_embed.add_field(name="!leaderboard", value="View the MMR leaderboard.", inline=False)
    help_embed.add_field(name="!linkriot", value="Link your Riot account using `Name#Tag`.", inline=False)
    help_embed.add_field(name="!unlink", value="Unlink your Riot account.", inline=False)
    help_embed.add_field(name="!join", value="Joins the queue.", inline=False)
    help_embed.add_field(name="!setcaptain1", value="Set Captain 1 using `Name#Tag` (only accessible by admins)", inline=False)
    help_embed.add_field(name="!setcaptain2", value="Set Captain 2 using `Name#Tag` (only accessible by admins)", inline=False)
    help_embed.add_field(name="!leave", value="Leaves the queue", inline=False)
    help_embed.add_field(name="!help", value="Display this help menu.", inline=False)
    
    # Send the embedded message
    await ctx.send(embed=help_embed)


# Run the bot
bot.run(bot_token)