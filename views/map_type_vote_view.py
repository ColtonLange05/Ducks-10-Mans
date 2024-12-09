"""This view allows players to interactively vote for map type."""

import asyncio
import discord
from discord.ui import Button
import random

from globals import official_maps, all_maps
from views.map_vote_view import MapVoteView


class MapTypeVoteView(discord.ui.View):
    def __init__(self, ctx, bot):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.bot = bot
        self.competitive_button = Button(
            label="Competitive Maps (0)", style=discord.ButtonStyle.green
        )
        self.all_maps_button = Button(
            label="All Maps (0)", style=discord.ButtonStyle.blurple
        )

        self.add_item(self.competitive_button)
        self.add_item(self.all_maps_button)

        # Initialize votes for map pool
        self.map_pool_votes = {"Competitive Maps": 0, "All Maps": 0}
        self.voters = set()

        self.setup_callbacks()

    async def competitive_callback(self, interaction: discord.Interaction):
        # make user is in the queue and hasn't voted yet
        if interaction.user.id not in [player["id"] for player in self.bot.queue]:
            await interaction.response.send_message(
                "You must be in the queue to vote!", ephemeral=True
            )
            return
        if interaction.user.id in self.voters:
            await interaction.response.send_message(
                "You have already voted!", ephemeral=True
            )
            return
        self.map_pool_votes["Competitive Maps"] += 1
        self.voters.add(interaction.user.id)
        self.competitive_button.label = (
            f"Competitive Maps ({self.map_pool_votes['Competitive Maps']})"
        )
        await interaction.message.edit(view=self)
        await interaction.response.send_message(
            "You voted for Competitive Maps.", ephemeral=True
        )

    async def all_maps_callback(self, interaction: discord.Interaction):
        # make sure the user is in the queue and hasn't voted yet
        if interaction.user.id not in [player["id"] for player in self.bot.queue]:
            await interaction.response.send_message(
                "You must be in the queue to vote!", ephemeral=True
            )
            return
        if interaction.user.id in self.voters:
            await interaction.response.send_message(
                "You have already voted!", ephemeral=True
            )
            return
        self.map_pool_votes["All Maps"] += 1
        self.voters.add(interaction.user.id)
        self.all_maps_button.label = f"All Maps ({self.map_pool_votes['All Maps']})"
        await interaction.message.edit(view=self)
        await interaction.response.send_message(
            "You voted for All Maps.", ephemeral=True
        )

    async def send_view(self):
        await self.ctx.send("Vote for the map pool:", view=self)

        count = 0
        # We loop and wait for votes, or break early if a clear winner emerges
        while count < 50:
            # If one category exceeds 4 votes, they automatically win (assuming a 10-player match)
            if self.map_pool_votes["All Maps"] > 4:
                await self.ctx.send("All Maps selected!")
                chosen_maps = all_maps
                break
            elif self.map_pool_votes["Competitive Maps"] > 4:
                await self.ctx.send("Competitive Maps selected!")
                chosen_maps = official_maps
                break

            await asyncio.sleep(0.5)
            count += 1
        else:
            # Timeout reached, decide by who has more votes
            if self.map_pool_votes["Competitive Maps"] > self.map_pool_votes["All Maps"]:
                await self.ctx.send("Competitive Maps selected! - Voting Phase Timeout")
                chosen_maps = official_maps
            elif self.map_pool_votes["All Maps"] > self.map_pool_votes["Competitive Maps"]:
                await self.ctx.send("All Maps selected! - Voting Phase Timeout")
                chosen_maps = all_maps
            else:
                # Tie breaker
                decision = "All Maps" if random.choice([True, False]) else "Competitive Maps"
                await self.ctx.send(f"It's a tie! The RNG gods say {decision} wins!")
                chosen_maps = all_maps if decision == "All Maps" else official_maps

        # Now that chosen_maps is decided, call MapVoteView to pick the final map.
        map_vote = MapVoteView(self.ctx, self.bot, chosen_maps)
        await map_vote.setup()
        await map_vote.send_view()  # MapVoteView handles the final map selection

    def setup_callbacks(self):
        self.competitive_button.callback = self.competitive_callback
        self.all_maps_button.callback = self.all_maps_callback