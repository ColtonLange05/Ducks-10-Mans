"""This view creates and maintains a signup interaction, contained within its own channel."""

import asyncio

import discord
from discord.ui import Button

from database import users
from views.mode_vote_view import ModeVoteView


class SignupView(discord.ui.View):
    def __init__(self, ctx, bot):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.bot = bot
        self.bot.origin_ctx = ctx
        # Start refresh tasks ONLY if needed
        self.signup_refresh_task = asyncio.create_task(self.refresh_signup_message())
        self.channel_name_refresh_task = asyncio.create_task(self.refresh_channel_name())

        self.sign_up_button = Button(
            label="Sign Up (0/10)", style=discord.ButtonStyle.green
        )
        self.leave_queue_button = Button(
            label="Leave Queue", style=discord.ButtonStyle.red
        )
        self.add_item(self.sign_up_button)
        self.add_item(self.leave_queue_button)

        self.setup_callbacks()

    async def sign_up_callback(self, interaction: discord.Interaction):
        existing_user = users.find_one({"discord_id": str(interaction.user.id)})
        if existing_user:
            if interaction.user.id not in [p["id"] for p in self.bot.queue]:
                self.bot.queue.append({"id": interaction.user.id, "name": interaction.user.name})
                if interaction.user.id not in self.bot.player_mmr:
                    self.bot.player_mmr[interaction.user.id] = {"mmr": 1000, "wins": 0, "losses": 0}
                self.bot.player_names[interaction.user.id] = interaction.user.name

                self.sign_up_button.label = f"Sign Up ({len(self.bot.queue)}/10)"
                await interaction.response.edit_message(
                    content="Click a button to manage your queue status!", view=self
                )
                await interaction.followup.send(
                    f"{interaction.user.name} added to the queue! ({len(self.bot.queue)}/10)",
                    ephemeral=True
                )

                # Add role
                member = interaction.guild.get_member(interaction.user.id) or await interaction.guild.fetch_member(interaction.user.id)
                if member:
                    try:
                        await member.add_roles(self.bot.match_role)
                    except discord.Forbidden:
                        await interaction.followup.send("Could not assign the role due to permissions.", ephemeral=True)
                else:
                    await interaction.followup.send("Could not assign the role. Member not found in guild.", ephemeral=True)

                if len(self.bot.queue) == 10:
                    await interaction.channel.send("The queue is now full, proceeding to the voting stage.")
                    self.cancel_signup_refresh()

                    # Ping all players
                    await interaction.channel.send("__Players:__ " + " ".join([f"<@{p['id']}>" for p in self.bot.queue]))

                    self.bot.signup_active = False
                    self.ctx.channel = self.bot.match_channel

                    from views.mode_vote_view import ModeVoteView
                    mode_vote = ModeVoteView(self.ctx, self.bot)
                    await mode_vote.send_view()
            else:
                await interaction.response.send_message("You're already in the queue!", ephemeral=True)
        else:
            await interaction.response.send_message(
                "You must link your Riot account first. Use `!linkriot Name#Tag`",
                ephemeral=True
            )

    async def leave_queue_callback(self, interaction: discord.Interaction):
        self.bot.queue = [p for p in self.bot.queue if p["id"] != interaction.user.id]
        self.sign_up_button.label = f"Sign Up ({len(self.bot.queue)}/10)"
        await interaction.response.edit_message(
            content="Click a button to manage your queue status!", view=self
        )

        await interaction.followup.send(f"{interaction.user.name} left the queue. ({len(self.bot.queue)}/10)", ephemeral=True)
        member = interaction.guild.get_member(interaction.user.id) or await interaction.guild.fetch_member(interaction.user.id)
        if member:
            try:
                await member.remove_roles(self.bot.match_role)
            except discord.Forbidden:
                await interaction.followup.send("Could not remove role due to permissions.", ephemeral=True)

    def setup_callbacks(self):
        self.sign_up_button.callback = self.sign_up_callback
        self.leave_queue_button.callback = self.leave_queue_callback

    async def refresh_signup_message(self):
        try:
            # Wait before first refresh to avoid immediate duplicate message
            await asyncio.sleep(60)
            while self.bot.signup_active:
                if self.bot.current_signup_message:
                    try:
                        await self.bot.current_signup_message.delete()
                    except discord.NotFound:
                        pass
                # Re-send the signup message after 60 seconds
                self.bot.current_signup_message = await self.bot.match_channel.send(
                    "Click a button to manage your queue status!",
                    view=self,
                    silent=True,
                )
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            pass

    def cancel_signup_refresh(self):
        if self.signup_refresh_task:
            self.signup_refresh_task.cancel()
            self.signup_refresh_task = None

    async def refresh_channel_name(self):
        try:
            while self.bot.signup_active:
                try:
                    await self.bot.match_channel.edit(name=f"{self.bot.match_name}《{len(self.bot.queue)}∕10》")
                except discord.HTTPException:
                    pass
                await asyncio.sleep(720)
        except asyncio.CancelledError:
            pass

    def cancel_channel_name_refresh(self):
        if self.channel_name_refresh_task:
            self.channel_name_refresh_task.cancel()
            self.channel_name_refresh_task = None

    async def send_signup(self):
        return await self.ctx.send(
            content="Click a button to manage your queue status!", view=self
        )

    async def update_signup(self):
        if self.bot.current_signup_message:
            self.sign_up_button.label = f"Sign Up ({len(self.bot.queue)}/10)"
            await self.bot.current_signup_message.edit(
                content="Click a button to manage your queue status!", view=self
            )

    def add_player_to_queue(self, player):
        self.bot.queue.append(player)
