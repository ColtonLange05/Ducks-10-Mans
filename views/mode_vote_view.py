import asyncio
import random
import discord
from discord.ui import Button, View
import time

class ModeVoteView(discord.ui.View):
    def __init__(self, ctx, bot):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.bot = bot
        self.balanced_button = Button(label="Balanced Teams (0)", style=discord.ButtonStyle.green)
        self.captains_button = Button(label="Captains (0)", style=discord.ButtonStyle.blurple)
        self.add_item(self.balanced_button)
        self.add_item(self.captains_button)

        self.votes = {"Balanced":0, "Captains":0}
        self.voters = set()

        self.balanced_button.callback = self.balanced_callback
        self.captains_button.callback = self.captains_callback

        self.voting_phase_ended = False
        self.timeout = False

    async def balanced_callback(self, interaction: discord.Interaction):
        if self.voting_phase_ended: #doesn't allow for votes if phase has already ended
            await interaction.response.send_message("Thias voting phase has already ended", ephemeral=True)

        if str(interaction.user.id) not in [p["id"] for p in self.bot.queue]:
            await interaction.response.send_message("Must be in queue!", ephemeral=True)
            return
        
        if str(interaction.user.id) in self.voters:
            await interaction.response.send_message("Already voted!", ephemeral=True)
            return

        self.votes["Balanced"]+=1
        self.voters.add(str(interaction.user.id))
        print(f"[DEBUG] Updated vote count: {self.votes}")
        self.balanced_button.label = f"Balanced Teams ({self.votes['Balanced']})"
        await self.check_vote() #check if an option has won
        await interaction.message.edit(view=self)
        await interaction.response.send_message("Voted Balanced!", ephemeral=True)

    async def captains_callback(self, interaction: discord.Interaction):
        if self.voting_phase_ended:
            await interaction.response.send_message("This voting phase has already ended", ephemeral=True)

        if str(interaction.user.id) not in [p["id"] for p in self.bot.queue]:
            await interaction.response.send_message("Must be in queue!", ephemeral=True)
            return
  
        if str(interaction.user.id) in self.voters:
            await interaction.response.send_message("Already voted!", ephemeral=True)
            return
        
        self.votes["Captains"]+=1
        self.voters.add(str(interaction.user.id))
        print(f"[DEBUG] Updated vote count: {self.votes}")
        self.captains_button.label = f"Captains ({self.votes['Captains']})"
        await self.check_vote() #check if an option has won
        await interaction.message.edit(view=self)
        await interaction.response.send_message("Voted Captains!", ephemeral=True)

    async def send_view(self):
        await self.ctx.send("Vote for mode (Balanced/Captains):", view=self)
        asyncio.create_task(self.start_timer())

    async def check_vote(self):
        print(f"[DEBUG] Checking votes. Current state: {self.votes}")
        print(f"[DEBUG] Voting phase ended: {self.voting_phase_ended}")
        print(f"[DEBUG] Timeout status: {self.timeout}")
        
        #if self.voting_phase_ended:
            #return
            
        # Handle timeout case
        if self.timeout:
            if self.votes["Balanced"] > self.votes["Captains"]:
                print("[DEBUG] Balanced wins on timeout")
                self.bot.chosen_mode = "Balanced"
                await self.ctx.send("Balanced Teams chosen!")
                self.voting_phase_ended = True
                await self._setup_balanced_teams()
            elif self.votes["Captains"] > self.votes["Balanced"]:
                print("[DEBUG] Captains wins on timeout")
                self.bot.chosen_mode = "Captains"
                await self.ctx.send("Captains chosen! Captains will be set after map is chosen.")
                self.voting_phase_ended = True
            else:
                # Handle tie
                decision = "Balanced" if random.choice([True, False]) else "Captains"
                self.bot.chosen_mode = decision
                await self.ctx.send(f"Tie! {decision} wins by coin flip!")
                if decision == "Balanced":
                    await self._setup_balanced_teams()
            return

        # Handle majority vote case (5 votes) first
        if self.votes["Balanced"] > 4:
            print("[DEBUG] Setting mode to Balanced (majority)")
            self.bot.chosen_mode = "Balanced"
            self.voting_phase_ended = True
            await self.ctx.send("Balanced Teams chosen!")
            await self._setup_balanced_teams()
            print(f"[DEBUG] Mode after setting: {self.bot.chosen_mode}")
            return
        elif self.votes["Captains"] > 4:
            print("[DEBUG] Setting mode to Captains (majority)")
            self.bot.chosen_mode = "Captains"
            self.voting_phase_ended = True
            await self.ctx.send("Captains chosen! Captains will be set after map is chosen.")
            print(f"[DEBUG] Mode after setting: {self.bot.chosen_mode}")
            return
            
        # Handle timeout case - now properly finalizes even without majority
        if self.timeout and not self.voting_phase_ended:
            balanced_votes = self.votes["Balanced"]
            captains_votes = self.votes["Captains"]
            
            if balanced_votes > captains_votes:
                print("[DEBUG] Balanced wins on timeout")
                self.bot.chosen_mode = "Balanced"
                self.voting_phase_ended = True
                await self.ctx.send(f"Time's up! Balanced Teams wins with {balanced_votes} votes vs {captains_votes} votes!")
                await self._setup_balanced_teams()
            elif captains_votes > balanced_votes:
                print("[DEBUG] Captains wins on timeout")
                self.bot.chosen_mode = "Captains"
                self.voting_phase_ended = True
                await self.ctx.send(f"Time's up! Captains wins with {captains_votes} votes vs {balanced_votes} votes!")
            else:
                # Handle tie
                decision = "Balanced" if random.choice([True, False]) else "Captains"
                self.bot.chosen_mode = decision
                self.voting_phase_ended = True
                await self.ctx.send(f"Time's up! Votes tied {balanced_votes}-{balanced_votes}. {decision} wins by coin flip!")
                if decision == "Balanced":
                    await self._setup_balanced_teams()
            
            print(f"[DEBUG] Final mode selection: {self.bot.chosen_mode}")
            return
    
    async def _setup_balanced_teams(self):
        players = self.bot.queue[:]
        players.sort(key=lambda p: self.bot.player_mmr[p["id"]]["mmr"], reverse=True)
        team1, team2 = [], []
        t1_mmr = 0
        t2_mmr = 0
        for player in players:
            if t1_mmr <= t2_mmr:
                team1.append(player)
                t1_mmr += self.bot.player_mmr[player["id"]]["mmr"]
            else:
                team2.append(player)
                t2_mmr += self.bot.player_mmr[player["id"]]["mmr"]
        self.bot.team1 = team1
        self.bot.team2 = team2

    async def start_timer(self):
        await asyncio.sleep(25)  # Wait 25 seconds
        if not self.voting_phase_ended:  # Ensure we haven't already ended the voting phase
            self.timeout = True
            self.voting_phase_ended = True
            await self.check_vote()
            

        # After mode chosen, do map type vote
        from views.map_type_vote_view import MapTypeVoteView
        map_type_vote=MapTypeVoteView(self.ctx,self.bot)
        await map_type_vote.send_view()
