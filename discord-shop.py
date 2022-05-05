import discord
import mysql.connector
import time
import json
import requests
import validators
from numpy import base_repr
import os


with open("TestgithubCE\DiscordShopBot-main\DiscordShopBot-main\config.json") as f:
	config = json.load(f)
	config_mysql = config["mysql"]
	config_discord = config["discord"]

client = discord.Client()

cart_database = test_mysql = mysql.connector.connect(
    user=config_mysql["user"],
    password=config_mysql["password"],
    host=config_mysql["host"],
    port=config_mysql["port"],
    database=config_mysql["database"]
	)

print(f"MySQL: Logged in as {cart_database.user}")
cart_cursor = cart_database.cursor(buffered=True)
cart_cursor.execute(
    "CREATE TABLE IF NOT EXISTS `items` (`id` int NOT NULL AUTO_INCREMENT PRIMARY KEY, `name` varchar(256) DEFAULT NULL, `description` varchar(1024) DEFAULT NULL, `url` varchar(1024) DEFAULT NULL, `price` varchar(255) DEFAULT NULL, `quantity` varchar(255) DEFAULT NULL, `channel_id` varchar(255) DEFAULT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
)
cart_database.commit()


async def get_database_user(user, reaction) -> str:
	"""Returns the username of the discord user which corresponds to the database table.

	Args:
		user: the user on the server
		reaction: the reaction on the server

	Returns:
		str: username which corresponds to the database table
	"""
	try:
		guild_id = base_repr(reaction.message.guild.id, 36)
	except AttributeError:
		guild_id = reaction.message.embeds[0].fields[3].value.split(
		    "|")[2].replace(" ", "")
	database_user = f"{user.id}_{guild_id}"
	print(str(user) + ':' + database_user)
	return database_user


async def start_setup(message) -> None:
	"""Performs the automatic setup.

	Args:
		message: the message which ran the setup process
	"""
	for guild in client.guilds:
		roleExists = False
		categoryExists = False
		for role in guild.roles:
			if "Seller" in role.name:
				roleExists = True
		if roleExists is False:
			await guild.create_role(name="Seller",
			                        reason="จำเป็นสำหรับ DiscordShopBot")
		for category in guild.categories:
			if "orders" in category.name:
				categoryExists = True
		if categoryExists is False:
			await guild.create_category("orders")
	embed = discord.Embed(title="ดำเนินการสำเร็จแล้ว",
	                      description="",
	                      color=discord.Colour.from_rgb(255, 0, 0))
	embed.add_field(
	    name="Developer",
	    value=
	    "JAY | [Discord](https://discord.gg/mfUEw9d98y)",
	    inline=True)

	await message.channel.send(embed=embed)


@client.event
async def on_ready() -> None:
	"""Is ran when the bot is ready and sets changes the presence of the bot."""
	print("Discord: Logged in as {0.user}".format(client))
	await client.change_presence(activity=discord.Activity(
	    type=discord.ActivityType.watching, name=f"{len(client.guilds)} Server"))


@client.event
async def on_raw_reaction_add(raw_reaction) -> None:
	"""Is ran when a reaction is added to a message of the bot.

	Args:
		raw_reaction: the reaction which has been added to the message
	"""
	channel = await client.fetch_channel(raw_reaction.channel_id)
	message = await channel.fetch_message(raw_reaction.message_id)
	user = await client.fetch_user(raw_reaction.user_id)

	if user != client.user:
		cart_cursor.execute(
		    "SELECT EXISTS (SELECT * FROM items WHERE name = %s AND channel_id = %s)",
		    (message.embeds[0].title, message.channel.id))
		is_sell_message = cart_cursor.fetchall()
		if is_sell_message == [(1, )]:
			for reaction in message.reactions:
				await reaction.remove(user=user)
				if reaction.count >= 2:
					database_user = await get_database_user(user, reaction)
					if reaction.emoji == "🛒":
						print(f"{user}: 🛒 เพิ่มในรถเข็น")
						cart(database_user, 1, reaction)
						await cart_message(database_user, reaction, user)
					elif reaction.emoji == "❌":
						print(f"{user}: ❌ นำออกจากรถเข็น")
						cart(database_user, -1, reaction)
						await cart_message(database_user, reaction, user)
				elif reaction.emoji == "✏️":
					await edit_item(reaction, user)
				elif reaction.emoji == "🗑️":
					await delete_item(reaction, user)
		elif is_cart(message):
			for reaction in message.reactions:
				if reaction.count >= 2:
					database_user = await get_database_user(user, reaction)
					if reaction.emoji == "💰":
						print(f"{user}: 💰  ไปการชำระเงิน")
						await cart_ticket(database_user, reaction, user)
					elif reaction.emoji == "🗑️":
						print(f"{user}: 🗑️  รถเข็นเปล่า")
						await delete_cart(reaction, database_user)
		elif is_order(message):
			for reaction in message.reactions:
				if reaction.count >= 2 and reaction.emoji == "🗑️":
					print(f"{user}: 🗑️  ยกเลิกการชำระเงิน")
					await message.channel.delete()


async def delete_item(reaction, user) -> None:
	"""Deletes a item from the chat and database.

	Args:
		reaction: the reaction which was added to the item message
		user: the user who added the reaction
	"""
	guild = reaction.message.guild
	guild_member = await guild.fetch_member(user.id)

	role_names = [role.name for role in guild_member.roles]
	if "Seller" not in role_names:
		return

	item_name = reaction.message.embeds[0].title

	print(f"{user}: 🗑️  {item_name}")

	edit_item_channel = await guild.create_text_channel(f"delete-{item_name}")

	await edit_item_channel.set_permissions(guild.default_role,
	                                        read_messages=False,
	                                        send_messages=False)
	await edit_item_channel.set_permissions(user,
	                                        read_messages=True,
	                                        send_messages=True)
	await edit_item_channel.set_permissions(discord.utils.get(guild.roles,
	                                                          name="Seller"),
	                                        read_messages=True,
	                                        send_messages=True)

	def check(m) -> bool:
		return m.channel == edit_item_channel and m.author == guild_member

	cart_cursor.execute(
	    "SELECT * FROM items WHERE name = %s AND channel_id = %s",
	    (item_name, reaction.message.channel.id))
	productinfo = cart_cursor.fetchall()[0]
	item_id = productinfo[0]
	item_name = productinfo[1]
	item_description = productinfo[2]
	item_image = productinfo[3]
	item_price = productinfo[4]
	item_quantity_database = productinfo[5]
	if str(item_quantity_database) == "-1":
		item_quantity = "Unlimited"
	else:
		item_quantity = item_quantity_database

	while True:
		embed = discord.Embed(title=f"ตัวอย่างรายการ:\n\n{item_name}",
		                      description="",
		                      color=discord.Colour.from_rgb(255, 0, 0))
		embed.add_field(name=f"ราคา: {item_price}€",
		                value=item_description,
		                inline=True)
		embed.add_field(name=f"จำนวนสินค้า: {item_quantity}",
		                value=".",
		                inline=True)
		if str(item_image) != "." and "None":
			embed.set_image(url=item_image)
		await edit_item_channel.send(embed=embed, content="")

		embed = discord.Embed(title="คุณแน่ใจหรือว่าต้องการลบสินค้านี้",
		                      description="ตอบ yes หรือ no",
		                      color=discord.Colour.from_rgb(255, 0, 0))
		await edit_item_channel.send(embed=embed, content=f"<@{user.id}>")

		edit_item_menu_message = await client.wait_for('message', check=check)
		edit_item_menu = edit_item_menu_message.content

		if edit_item_menu == "yes":
			embed = discord.Embed(title="กำลังลบ ...",
			                      description="",
			                      color=discord.Colour.from_rgb(255, 0, 0))
			await edit_item_channel.send(embed=embed)
			time.sleep(2)

			cart_cursor.execute(f"DELETE FROM items WHERE id = {item_id}")
			cart_database.commit()

			await reaction.message.delete()
			await edit_item_channel.delete()
			break
		if edit_item_menu == "no":
			embed = discord.Embed(title="กำลังยกเลิก ...",
			                      description="",
			                      color=discord.Colour.from_rgb(255, 0, 0))
			await edit_item_channel.send(embed=embed)
			time.sleep(2)
			await edit_item_channel.delete()
			break


async def edit_item(reaction, user) -> None:
	"""Edits an item.

	Args:
		reaction: the reaction which was added to the item message
		user: the user who added the reaction
	"""
	guild = reaction.message.guild
	guild_member = await guild.fetch_member(user.id)

	role_names = [role.name for role in guild_member.roles]
	if "Seller" not in role_names:
		return

	item_name = reaction.message.embeds[0].title

	print(f"{user}: ✏️  {item_name}")

	edit_item_channel = await guild.create_text_channel(f"edit-{item_name}")

	await edit_item_channel.set_permissions(guild.default_role,
	                                        read_messages=False,
	                                        send_messages=False)
	await edit_item_channel.set_permissions(user,
	                                        read_messages=True,
	                                        send_messages=True)
	await edit_item_channel.set_permissions(discord.utils.get(guild.roles,
	                                                          name="Seller"),
	                                        read_messages=True,
	                                        send_messages=True)

	def check(m) -> bool:
		return m.channel == edit_item_channel and m.author == guild_member

	cart_cursor.execute(
	    "SELECT * FROM items WHERE name = %s AND channel_id = %s",
	    (item_name, reaction.message.channel.id))
	productinfo = cart_cursor.fetchall()[0]
	item_id = productinfo[0]
	item_name = productinfo[1]
	item_description = productinfo[2]
	item_image = productinfo[3]
	item_price = productinfo[4]
	item_quantity_database = productinfo[5]
	if str(item_quantity_database) == "-1":
		item_quantity = "Unlimited"
	else:
		item_quantity = item_quantity_database

	while True:
		embed = discord.Embed(title=f"ตัวอย่างสินค้า:\n\n{item_name}",
		                      description="",
		                      color=discord.Colour.from_rgb(255, 0, 0))
		embed.add_field(name=f"Price: {item_price}€",
		                value=item_description,
		                inline=True)
		embed.add_field(name=f"Quantity: {item_quantity}",
		                value=".",
		                inline=True)
		if str(item_image) != "." and "None":
			embed.set_image(url=item_image)
		await edit_item_channel.send(embed=embed, content="")

		embed = discord.Embed(title="วิธีแก้ไข:",
		                      description="",
		                      color=discord.Colour.from_rgb(255, 0, 0))
		embed.add_field(name="แก้ไขชื่อ", value="Usage: =name", inline=True)
		embed.add_field(name="แก้ไขคำอธิบาย",
		                value="Usage: =description",
		                inline=True)
		embed.add_field(name="แก้ไขภาพ", value="Usage: =image", inline=True)
		embed.add_field(name="แก้ไขราคา", value="Usage: =price", inline=True)
		embed.add_field(name="แก้ไขจำนวน",
		                value="Usage: =quantity",
		                inline=True)
		embed.add_field(name="ยกเลิกการแก้ไข",
		                value="Usage: =cancel",
		                inline=True)
		embed.add_field(name="บันทึกการเปลี่ยนแปลง", value="Usage: =save", inline=True)
		await edit_item_channel.send(embed=embed, content=f"<@{user.id}>")

		edit_item_menu_message = await client.wait_for('message', check=check)
		edit_item_menu = edit_item_menu_message.content

		if edit_item_menu == "=name":
			while True:
				embed = discord.Embed(title="ชื่อที่ต้องการแก้ไข",
				                      description="",
				                      color=discord.Colour.from_rgb(255, 0, 0))
				embed.add_field(name="ชื่อปัจจุบัน: ",
				                value=f"```{item_name}```",
				                inline=True)
				await edit_item_channel.send(embed=embed)
				item_name_message = await client.wait_for('message',
				                                          check=check)
				new_item_name = item_name_message.content
				if new_item_name != item_name:
					cart_cursor.execute(
					    "SELECT * FROM items WHERE name = %s AND channel_id = %s",
					    (new_item_name, reaction.message.channel.id))
					if cart_cursor.fetchall() != []:
						embed = discord.Embed(
						    title="คุณไม่สามารถมี 2 รายการที่มีชื่อเดียวกัน",
						    description=
						    "เพียงลบอันเก่าหรือเลือกชื่ออื่นเพื่อดำเนินการต่อ",
						    color=discord.Colour.from_rgb(255, 0, 0))
						await edit_item_channel.send(embed=embed)
					else:
						if len(new_item_name) > 256:
							embed = discord.Embed(
							    title="ความยาวสูงสุดคือ 256 อักขระ",
							    description="",
							    color=discord.Colour.from_rgb(255, 0, 0))
							await edit_item_channel.send(embed=embed)
						else:
							item_name = new_item_name
							break
				else:
					break
			embed = discord.Embed(title="ตั้งชื่อเป็น:",
			                      description=f"```{item_name}```",
			                      color=discord.Colour.from_rgb(255, 0, 0))
			await edit_item_channel.send(embed=embed)
		elif edit_item_menu == "=description":
			while True:
				embed = discord.Embed(
				    title="What should be the item description?",
				    description="Enter . for no description.",
				    color=discord.Colour.from_rgb(255, 0, 0))
				embed.add_field(name="Current description:",
				                value=f"```{item_description}```",
				                inline=True)
				await edit_item_channel.send(embed=embed)
				item_description_message = await client.wait_for('message',
				                                                 check=check)
				new_item_description = item_description_message.content
				if len(new_item_description) > 1024:
					embed = discord.Embed(
					    title="The maximum length is 1024 characters.",
					    description="",
					    color=discord.Colour.from_rgb(255, 0, 0))
					await edit_item_channel.send(embed=embed)
				else:
					item_description = new_item_description
					break
			embed = discord.Embed(title="Description set to:",
			                      description=f"```{item_description}```",
			                      color=discord.Colour.from_rgb(255, 0, 0))
			await edit_item_channel.send(embed=embed)
		elif edit_item_menu == "=image":
			while True:
				embed = discord.Embed(
				    title="ภาพที่ต้องการแก้ไข",
				    description=
				    "โปรดป้อน URL สาธารณะของรูปภาพหรืออัปโหลดรูปภาพผ่าน Discord\nไฟล์ที่ถูกต้องคือ png, jpg หรือ gif \n ป้อน . สำหรับไม่มีภาพ",
				    color=discord.Colour.from_rgb(255, 0, 0))
				embed.add_field(name="ภาพปัจจุบัน:",
				                value=f"```{item_image}```",
				                inline=True)
				if str(item_image) != "." and "None":
					embed.set_image(url=item_image)
				await edit_item_channel.send(embed=embed)
				item_image_message = await client.wait_for('message',
				                                           check=check)
				try:
					new_item_image = item_image_message.attachments[0].url
				except IndexError:
					new_item_image = item_image_message.content
				if str(new_item_image) == ".":
					item_image = new_item_image
					break
				if validators.url(new_item_image) is True:
					if len(new_item_image) > 1024:
						embed = discord.Embed(
						    title="ความยาวสูงสุดคือ 1024 อักขระ",
						    description="",
						    color=discord.Colour.from_rgb(255, 0, 0))
						await edit_item_channel.send(embed=embed)
					else:
						if is_url_image(new_item_image) is True:
							item_image = new_item_image
							break
						embed = discord.Embed(
						    title="URL รูปภาพไม่ใช่รูปแบบไฟล์ที่ถูกต้อง",
						    description="",
						    color=discord.Colour.from_rgb(255, 0, 0))
						await edit_item_channel.send(embed=embed)
				else:
					embed = discord.Embed(
					    title="URL รูปภาพไม่เป็นสาธารณะหรือไม่มีอยู่",
					    description="",
					    color=discord.Colour.from_rgb(255, 0, 0))
					await edit_item_channel.send(embed=embed)
			embed = discord.Embed(title="Image set to:",
			                      description=f"```{item_image}```",
			                      color=discord.Colour.from_rgb(255, 0, 0))
			await edit_item_channel.send(embed=embed)
		elif edit_item_menu == "=price":
			while True:
				embed = discord.Embed(
				    title="ราคาที่ต้องการแก้ไข",
				    description="กรุณาใส่ราคาเช่นนี้: 0.1, 0.5, 1, 5, 10, 50, 100, 500, 1000",
				    color=discord.Colour.from_rgb(255, 0, 0))
				embed.add_field(name="ราคาปัจจุบัน:",
				                value=f"```{item_price}```",
				                inline=True)
				await edit_item_channel.send(embed=embed)
				item_price_message = await client.wait_for('message',
				                                           check=check)
				new_item_price = item_price_message.content
				try:
					new_item_price = round(float(new_item_price), 2)
					if new_item_price > 0:
						item_price = new_item_price
						break
					if new_item_price == 0:
						embed = discord.Embed(
						    title="ราคาสินค้าเป็นศูนย์ไม่ได้",
						    description="",
						    color=discord.Colour.from_rgb(255, 0, 0))
						await edit_item_channel.send(embed=embed)
					else:
						embed = discord.Embed(
						    title="ราคาสินค้าต้องไม่ต่ำกว่าศูนย์",
						    description="",
						    color=discord.Colour.from_rgb(255, 0, 0))
						await edit_item_channel.send(embed=embed)
				except ValueError:
					embed = discord.Embed(title="ราคาสินค้าต้องไม่ศูนย์",
					                      description="",
					                      color=discord.Colour.from_rgb(
					                          255, 0, 0))
					await edit_item_channel.send(embed=embed)
			embed = discord.Embed(title="ราคาตั้งเป็น:",
			                      description=f"```{item_price}```",
			                      color=discord.Colour.from_rgb(255, 0, 0))
			await edit_item_channel.send(embed=embed)
		elif edit_item_menu == "=quantity":
			while True:
				embed = discord.Embed(
				    title="จำนวนสินค้าที่ต้องการแก้ไข",
				    description="0 หมายถึง สินค้าหมด \n-1 หมายถึง ไม่จำกัด",
				    color=discord.Colour.from_rgb(255, 0, 0))
				embed.add_field(name="Current quantity:",
				                value=f"```{item_quantity}```",
				                inline=True)
				await edit_item_channel.send(embed=embed)
				item_quantity_message = await client.wait_for('message',
				                                              check=check)
				new_item_quantity_database = item_quantity_message.content
				try:
					new_item_quantity_database = int(
					    new_item_quantity_database)
					if new_item_quantity_database > -1:
						item_quantity = new_item_quantity_database
						item_quantity_database = new_item_quantity_database
						break
					if new_item_quantity_database == -1:
						item_quantity = "Unlimited"
						item_quantity_database = new_item_quantity_database
						break
					embed = discord.Embed(
					    title="ปริมาณสินค้าต้องไม่ต่ำกว่า -1(ไม่จำกัด)",
					    description="",
					    color=discord.Colour.from_rgb(255, 0, 0))
					await edit_item_channel.send(embed=embed)
				except ValueError:
					embed = discord.Embed(
					    title="โปรดป้อนปริมาณที่ถูกต้อง",
					    description="",
					    color=discord.Colour.from_rgb(255, 0, 0))
					await edit_item_channel.send(embed=embed)
			embed = discord.Embed(title="จำนวนตั้งเป็น:",
			                      description=f"```{item_quantity}```",
			                      color=discord.Colour.from_rgb(255, 0, 0))
			await edit_item_channel.send(embed=embed)
		elif edit_item_menu == "=save":
			embed = discord.Embed(title="กำลังบันทึกข้อมูล",
			                      description="",
			                      color=discord.Colour.from_rgb(255, 0, 0))
			await edit_item_channel.send(embed=embed)
			time.sleep(2)
			await edit_item_channel.delete()

			embed = discord.Embed(title=item_name,
			                      description="",
			                      color=discord.Colour.from_rgb(255, 0, 0))
			embed.add_field(name=f"ราคา: {item_price}€",
			                value=item_description,
			                inline=True)
			embed.add_field(name=f"จำนวน: {item_quantity}",
			                value=".",
			                inline=True)
			if str(item_image) != "." and "None":
				embed.set_image(url=item_image)
			await reaction.message.edit(embed=embed)

			cart_cursor.execute(
			    "UPDATE items SET name = %s, description = %s, url = %s, price = %s, quantity = %s WHERE id = %s",
			    (item_name, item_description, item_image, item_price,
			     item_quantity_database, item_id))
			cart_database.commit()
			break
		elif edit_item_menu == "=cancel":
			embed = discord.Embed(title="กำลังยกเลิก ...",
			                      description="",
			                      color=discord.Colour.from_rgb(255, 0, 0))
			await edit_item_channel.send(embed=embed)
			await edit_item_channel.delete()
			break
		else:
			embed = discord.Embed(title="คำสั่งไม่ถูกต้อง",
			                      description="",
			                      color=discord.Colour.from_rgb(255, 0, 0))
			await edit_item_channel.send(embed=embed)


async def cart_ticket(database_user, reaction, user) -> None:
	"""Creates the cart ticket.

	Args:
		database_user: The database user
		reaction: the reaction which was added to the cart message
		user: the user who added the reaction
	"""
	print(f"{user}")
	cart_cursor.execute(f"SELECT EXISTS (SELECT * FROM {database_user})")
	cart_exists = cart_cursor.fetchall()
	if cart_exists == [(1, )]:
		cart_cursor.execute(f"SELECT * FROM {database_user}")
		products = cart_cursor.fetchall()

		guild_msg_id = int(database_user.split("_")[1], 36)
		guild_ids = []
		for guild in client.guilds:
			guild_ids.append(guild.id)
		temp_id = guild_ids.index(guild_msg_id)
		guild_msg = client.guilds[temp_id]

		embed = discord.Embed(title=f"สั่งซื้อได้ที่ {guild_msg}",
		                      description="",
		                      color=discord.Colour.from_rgb(255, 0, 0))
		productnames = ""
		productquantity = ""
		productprices = ""
		total = 0
		for product in products:
			cart_cursor.execute(f"SELECT * FROM items WHERE id = {product[0]}")
			productinfo = cart_cursor.fetchall()[0]
			productnames = productnames + productinfo[1] + "\n "
			productquantity = productquantity + product[1] + "\n "
			productprices = productprices + productinfo[4] + "$" + "\n "
			total = total + (int(product[1]) * float(productinfo[4]))
		paypaltotal = round(total, 2) + (0.0249 * total + 0.35)

		embed.add_field(name="ชื่อ", value=f"{productnames}", inline=True)
		embed.add_field(name="จำนวน", value=f"{productquantity}", inline=True)
		embed.add_field(name="ราคา", value=f"{productprices}", inline=True)
		embed.add_field(
		    name=
		    f"ทั้งหมด: {round(total, 2)}$ | With PayPal fees: {round(paypaltotal, 2)}$",
		    value="(บางทีข้อความนี้อาจแสดงผลได้ไม่ดีบนอุปกรณ์มือถือ)",
		    inline=True)

		await delete_cart(reaction, database_user)

		cart_cursor.execute(f"DROP TABLE IF EXISTS `{database_user}`")
		cart_database.commit()

		guild = await client.fetch_guild(int(database_user.split("_")[1], 36))

		ticketchannel = await guild.create_text_channel(f"order-{user}")

		await ticketchannel.set_permissions(guild.default_role,
		                                    read_messages=False,
		                                    send_messages=False)
		await ticketchannel.set_permissions(user,
		                                    read_messages=True,
		                                    send_messages=True)
		await ticketchannel.set_permissions(discord.utils.get(guild.roles,
		                                                      name="Seller"),
		                                    read_messages=True,
		                                    send_messages=True)

		sent_ticket_message = await ticketchannel.send(embed=embed,
		                                               content=f"<@{user.id}>")
		await sent_ticket_message.add_reaction('🗑️')


async def delete_cart(reaction, database_user) -> None:
	"""Deletes the cart from the chat between the user and the bot.

	Args:
		reaction: the reaction which was added to the cart message
		database_user: the database user which added the reaction
	"""
	cart_cursor.execute(f"DROP TABLE IF EXISTS `{database_user}`")
	cart_database.commit()
	await reaction.message.delete()


def cart(database_user, cart_add_count, reaction) -> None:
	"""Creates or updates the cart database for the database user

	Args:
		database_user: the database user which added the reaction
		cart_add_count int: positive or negative int of items to add or remove from the cart
		reaction: the reaction which was added to the item message
	"""
	cart_cursor.execute(
	    "SELECT `id`, `quantity` FROM items WHERE name = %s AND channel_id = %s",
	    (reaction.message.embeds[0].title, reaction.message.channel.id))
	productid = cart_cursor.fetchone()[0]

	cart_cursor.execute(
	    f"CREATE TABLE IF NOT EXISTS {database_user} (`id` varchar(255) DEFAULT NULL, `quantity` varchar(255) DEFAULT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
	)
	cart_database.commit()
	cart_cursor.execute(
	    f"SELECT * FROM {database_user} WHERE id = {productid}", )
	cart = cart_cursor.fetchall()
	if cart == []:
		cart_cursor.execute(
		    f"INSERT INTO {database_user} (`id`, `quantity`) VALUES ({productid}, {cart_add_count})"
		)
		cart_database.commit()
	else:
		product = cart[0]
		cart_product_count = int(product[1])
		new_cart_product_count = cart_product_count + cart_add_count
		if new_cart_product_count <= 0:
			cart_cursor.execute(
			    f"DELETE FROM {database_user} WHERE id = {productid}")
		else:
			cart_cursor.execute(
			    f"UPDATE {database_user} SET quantity = {new_cart_product_count} WHERE id = {productid}"
			)
		cart_database.commit()


async def cart_message(database_user, reaction, user) -> None:
	"""Sends or updates the cart message in the chat between the user and the bot

	Args:
		database_user str: the database user which added the reaction
		cart_add_count int: positive or negative int of items to add or remove from the cart
		reaction: the reaction which was added to the item message
	"""
	cart_cursor.execute(f"SELECT EXISTS (SELECT * FROM {database_user})")
	cart_exists = cart_cursor.fetchall()
	if cart_exists == [(1, )]:
		cart_cursor.execute(f"SELECT * FROM {database_user}")
		products = cart_cursor.fetchall()

		guild_msg_id = int(database_user.split("_")[1], 36)
		guild_ids = []
		for guild in client.guilds:
			guild_ids.append(guild.id)
		temp_id = guild_ids.index(guild_msg_id)
		guild_msg = client.guilds[temp_id]

		embed = discord.Embed(title=f"Your cart at {guild_msg}",
		                      description="",
		                      color=discord.Colour.from_rgb(255, 0, 0))
		productnames = ""
		productquantity = ""
		productprices = ""
		total = 0
		for product in products:
			try:
				cart_cursor.execute(
				    f"SELECT * FROM items WHERE id = {product[0]}")
				productinfo = cart_cursor.fetchall()[0]
				productnames = productnames + productinfo[1] + "\n "
				productquantity = productquantity + product[1] + "\n "
				productprices = productprices + productinfo[4] + "€" + "\n "
				total = total + (int(product[1]) * float(productinfo[4]))
			except IndexError:
				cart_cursor.execute("DELETE FROM %s WHERE id = %s",
				                    (database_user, product[0]))
				print(
				    f"{user}: ❌ ลบรายการที่ไม่มีอยู่ของรายการฐานข้อมูล"
				)

		embed.add_field(name="Name", value=f"{productnames}", inline=True)
		embed.add_field(name="Count", value=f"{productquantity}", inline=True)
		embed.add_field(name="Price", value=f"{productprices}", inline=True)
		embed.add_field(
		    name=f"Total: {round(total, 2)}€",
		    value=
		    f"กด 💰 เพิ่อไปชำระเงินได้เลย หรือ กด 🗑️ เพื่อลบสินค้านี้ออกจากรถเข็น\n(บางทีข้อความนี้อาจแสดงผลได้ไม่ดีบนอุปกรณ์มือถือ)\nDeveloper: JAY | [Discord](https://discord.gg/BdRwt47X) | {base_repr(reaction.message.guild.id, 36)}",
		    inline=True)

		DMChannel = await user.create_dm()
		cart_message = await DMChannel.history().find(
		    lambda m: database_user.split("_")[1] in m.embeds[0].fields[
		        3].value)
		if cart_message is None:
			sent_cart_message = await DMChannel.send(embed=embed)
			await sent_cart_message.add_reaction('💰')
			await sent_cart_message.add_reaction('🗑️')
		else:
			await cart_message.edit(embed=embed)


async def delete_dm(user) -> None:
	"""Deletes a direct message between the user and the bot

	Args:
		user: the user for which the dm should be deleted
	"""
	DMChannel = await user.create_dm()
	async for message in DMChannel.history(limit=1000):
		if message.author.id == client.user.id:
			await message.delete()


def is_cart(message) -> bool:
	"""Checks if the message is a cart message

	Args:
		message: the message to check

	Returns:
		bool: a boolean indicating if the message is a cart message
	"""
	return "Your cart at " in message.embeds[0].title


def is_order(message) -> bool:
	"""Checks if the message is a order message

	Args:
		message: the message to check

	Returns:
		bool: a boolean indicating if the message is a order message
	"""
	return "Your order at " in message.embeds[0].title


async def delete_messages(channel) -> None:
	deleted = await channel.purge(limit=10000, check=None)
	message_count = len(deleted)
	if message_count == 1:
		await channel.send(f'Deleted {message_count} message')
	else:
		await channel.send(f'Deleted {message_count} messages')


async def help_command(message) -> None:
	"""Generates the help message on the help command

	Args:
		message: the message which ran the help command
	"""
	embed = discord.Embed(title="Command Help",
	                      description="",
	                      color=discord.Colour.from_rgb(255, 0, 0))

	embed.add_field(name="Command Help", value="Usage: =help", inline=True)
	embed.add_field(name="ลบข้อความทั้งหมดในช่อง",
	                value="Usage: =clear",
	                inline=True)
	embed.add_field(name="สร้างหมวดหมู่ร้านค้า",
	                value="Usage: =addcategory",
	                inline=True)
	embed.add_field(name="สร้างช่องทางร้านค้า",
	                value="Usage: =addchannel",
	                inline=True)
	embed.add_field(name="เพิ่มสินค้า", value="Usage: =additem", inline=True)
	embed.add_field(name="✏️ เเก้ไขสินค้า",
	                value="Usage: Reaction ✏️",
	                inline=True)
	embed.add_field(
	    name="Developer",
	    value=
	    "JAY | [Discord](https://discord.gg/BdRwt47X)",
	    inline=True)

	await message.channel.send(embed=embed)


async def addcategory_command(message) -> None:
	"""Creates a category

	Args:
		message: the message which ran the command
	"""
	guild = message.guild
	channel = message.channel
	author = message.author

	embed = discord.Embed(title="ชื่อหมวดหมู่ของคุณ",
	                      description="",
	                      color=discord.Colour.from_rgb(255, 0, 0))
	await message.channel.send(embed=embed)

	def check(m) -> bool:
		return m.channel == channel and m.author == author

	category = await client.wait_for('message', check=check)
	category_name = category.content

	embed = discord.Embed(title=f"สร้างหมวดหมู่ {category_name} เเล้ว",
	                      description="",
	                      color=discord.Colour.from_rgb(255, 0, 0))
	await message.channel.send(embed=embed)
	created_category = await guild.create_category(category_name)

	await created_category.set_permissions(guild.default_role,
	                                       read_messages=True,
	                                       send_messages=False)
	await created_category.set_permissions(discord.utils.get(guild.roles,
	                                                         name="Seller"),
	                                       read_messages=True,
	                                       send_messages=True)


async def addchannel_command(message) -> None:
	"""Creates a channel

	Args:
		message: the message which ran the command
	"""
	guild = message.guild
	channel = message.channel
	author = message.author
	categories = message.guild.categories

	def check(m) -> bool:
		return m.channel == channel and m.author == author

	while True:
		embed = discord.Embed(
		    title="ช่องใหม่ควรอยู่ในหมวดไหน?",
		    description="",
		    color=discord.Colour.from_rgb(255, 0, 0))
		await message.channel.send(embed=embed)
		category_message = await client.wait_for('message', check=check)
		category_name = category_message.content
		for category in categories:
			if category.name == category_name:
				new_category = category
		if "new_category" in locals():
			break
		embed = discord.Embed(title="โปรดป้อนหมวดหมู่ที่ถูกต้อง",
		                      description="",
		                      color=discord.Colour.from_rgb(255, 0, 0))
		await message.channel.send(embed=embed)

	embed = discord.Embed(title="ชื่อช่องของคุณ",
	                      description="",
	                      color=discord.Colour.from_rgb(255, 0, 0))
	await message.channel.send(embed=embed)

	channel_name_message = await client.wait_for('message', check=check)
	channel_name = channel_name_message.content

	embed = discord.Embed(title=f"สร้างช่อง {channel_name}",
	                      description="",
	                      color=discord.Colour.from_rgb(255, 0, 0))
	await message.channel.send(embed=embed)
	await guild.create_text_channel(channel_name, category=new_category)


def is_url_image(image_url) -> bool:
	"""Checks if a url does contain an image.

	Args:
		image_url str: the url which should be checked

	Returns:
		bool: a boolean indicating if the url contains an image
	"""
	image_formats = ("image/jpg", "image/jpeg", "image/png", "image/gif")
	r = requests.head(image_url)
	if r.headers["content-type"] in image_formats:
		return True
	return False


async def additem_command(message) -> None:
	"""Adds an item to the guild.

	Args:
		message: the message which ran the command
	"""
	channel = message.channel
	author = message.author

	def check(m) -> bool:
		return m.channel == channel and m.author == author

	while True:
		embed = discord.Embed(
		    title="ช่องสำหรับรายการของคุณคืออะไร?",
		    description=
		    "โปรดระบุช่องด้วย # เท่านี้น",
		    color=discord.Colour.from_rgb(255, 0, 0))
		await message.channel.send(embed=embed)
		item_category_message = await client.wait_for('message', check=check)
		mentioned_item_category = item_category_message.raw_channel_mentions
		try:
			mentioned_item_category_id = mentioned_item_category[0]
			item_category_channel = await client.fetch_channel(
			    mentioned_item_category_id)
			break
		except IndexError:
			embed = discord.Embed(title="โปรดระบุหมวดหมู่ที่ถูกต้อง",
			                      description="",
			                      color=discord.Colour.from_rgb(255, 0, 0))
			await message.channel.send(embed=embed)

	while True:
		embed = discord.Embed(title="ชื่อรายการของคุณ",
		                      description="",
		                      color=discord.Colour.from_rgb(255, 0, 0))
		await message.channel.send(embed=embed)
		item_name_message = await client.wait_for('message', check=check)
		item_name = item_name_message.content

		cart_cursor.execute(
		    "SELECT * FROM items WHERE name = %s AND channel_id = %s",
		    (item_name, mentioned_item_category_id))
		if cart_cursor.fetchall() != []:
			embed = discord.Embed(
			    title="คุณไม่สามารถมี 2 รายการที่มีชื่อเดียวกัน",
			    description=
			    "เพียงลบอันเก่าหรือเลือกชื่ออื่นเพื่อดำเนินการต่อ",
			    color=discord.Colour.from_rgb(255, 0, 0))
			await message.channel.send(embed=embed)
		else:
			if len(item_name) > 256:
				embed = discord.Embed(
				    title="ชื่อสินค้าต้องไม่เกิน 256 ตัวอักษร",
				    description="ความยาวสูงสุดคือ 256 อักขระ",
				    color=discord.Colour.from_rgb(255, 0, 0))
				await message.channel.send(embed=embed)
			else:
				break

	while True:
		embed = discord.Embed(title="คำอธิบายรายการสินค้าของคุณ",
		                      description="พิม . ถ้าไม่มีคำอธิบาย",
		                      color=discord.Colour.from_rgb(255, 0, 0))
		await message.channel.send(embed=embed)
		item_description_message = await client.wait_for('message',
		                                                 check=check)
		item_description = item_description_message.content
		if len(item_description) > 1024:
			await message.channel.send(
			    title="คำอธิบายต้องไม่เกิน 1024 ตัวอักษร",
			    description="ความยาวสูงสุดของคำอธิบายคือ 1024 ตัวอักษร",
			    color=discord.Colour.from_rgb(255, 0, 0))
		else:
			break

	while True:
		embed = discord.Embed(
		    title="รูปภาพสินค้าของคุณ",
		    description=
		    "โปรดป้อน URL สาธารณะของรูปภาพหรืออัปโหลดภาพผ่าน Discord\nไฟล์ที่ถูกต้องคือ .png, .jpg, .jpeg หรือ .gif \n พิมห . ถ้าไม่มีรูปภาพ",
		    color=discord.Colour.from_rgb(255, 0, 0))
		await message.channel.send(embed=embed)
		item_image_message = await client.wait_for('message', check=check)
		try:
			item_image = item_image_message.attachments[0].url
		except IndexError:
			item_image = item_image_message.content
		if str(item_image) == ".":
			break
		if validators.url(item_image) is True:
			if len(item_image) > 2048:
				embed = discord.Embed(
				    title="URl ไม่สามารถเกิน 2048 ตัวอักษร",
				    description="",
				    color=discord.Colour.from_rgb(255, 0, 0))
				await message.channel.send(embed=embed)
			else:
				if is_url_image(item_image) is True:
					break
				embed = discord.Embed(
				    title="URL รูปภาพไม่ใช่รูปแบบไฟล์ที่ถูกต้อง",
				    description="",
				    color=discord.Colour.from_rgb(255, 0, 0))
				await message.channel.send(embed=embed)
		else:
			embed = discord.Embed(
			    title="URL รูปภาพไม่เป็นสาธารณะหรือไม่มีอยู่",
			    description="",
			    color=discord.Colour.from_rgb(255, 0, 0))
			await message.channel.send(embed=embed)

	while True:
		embed = discord.Embed(
		    title="ราคาของสินค้าของคุณ",
		    description="กรุณาใส่ราคาเช่นนี้: 0.1, 0.5, 1, 5, 10, 50, 100",
		    color=discord.Colour.from_rgb(255, 0, 0))
		await message.channel.send(embed=embed)
		item_price_message = await client.wait_for('message', check=check)
		item_price = item_price_message.content
		try:
			item_price = round(float(item_price), 2)
			if item_price > 0:
				break
			if item_price == 0:
				embed = discord.Embed(title="ราคาสินค้าเป็นศูนย์ไม่ได้",
				                      description="",
				                      color=discord.Colour.from_rgb(255, 0, 0))
				await message.channel.send(embed=embed)
			else:
				embed = discord.Embed(
				    title="ราคาสินค้าต้องไม่ต่ำกว่าศูนย์",
				    description="",
				    color=discord.Colour.from_rgb(255, 0, 0))
				await message.channel.send(embed=embed)
		except ValueError:
			embed = discord.Embed(title="โปรดป้อนราคาที่ ไม่เท่ากับ 0",
			                      description="",
			                      color=discord.Colour.from_rgb(255, 0, 0))
			await message.channel.send(embed=embed)

	while True:
		embed = discord.Embed(
		    title="มีสินค้าทังหมดมีชิ้น",
		    description="0 หมายถึง สินค้าหมด \n-1 หมายถึง ไม่จำกัด",
		    color=discord.Colour.from_rgb(255, 0, 0))
		await message.channel.send(embed=embed)
		item_quantity_message = await client.wait_for('message', check=check)
		item_quantity_database = item_quantity_message.content
		try:
			item_quantity_database = int(item_quantity_database)
			if item_quantity_database > -1:
				item_quantity = item_quantity_database
				break
			if item_quantity_database == -1:
				item_quantity = "Unlimited"
				break
			embed = discord.Embed(
			    title="ปริมาณสินค้าต้องไม่ต่ำกว่า -1(ไม่จำกัด)",
			    description="",
			    color=discord.Colour.from_rgb(255, 0, 0))
			await message.channel.send(embed=embed)
		except ValueError:
			embed = discord.Embed(title="โปรดป้อนปริมาณที่ถูกต้อง",
			                      description="",
			                      color=discord.Colour.from_rgb(255, 0, 0))
			await message.channel.send(embed=embed)

	embed = discord.Embed(title=item_name,
	                      description="",
	                      color=discord.Colour.from_rgb(255, 0, 0))

	embed.add_field(name=f"ราคา: {item_price}€",
	                value=item_description,
	                inline=True)
	embed.add_field(name=f"จำนวน : {item_quantity}", value=".", inline=True)
	if str(item_image) != ".":
		embed.set_image(url=item_image)

	sent_item_message = await item_category_channel.send(embed=embed)
	await sent_item_message.add_reaction('🛒')
	await sent_item_message.add_reaction('❌')

	cart_cursor.execute(
	    "INSERT INTO `items` (`name`, `description`, `url`, `price`, `quantity`, `channel_id`) VALUES (%s, %s, %s, %s, %s, %s)",
	    (item_name, item_description, item_image, item_price,
	     item_quantity_database, mentioned_item_category_id))
	cart_database.commit()


@client.event
async def on_message(message) -> None:
	"""Is ran when the bot receives a message

	Args:
		message: the message which got received
	"""
	if message.author != client.user and message.guild is not None:
		role_names = [role.name for role in message.author.roles]
		if message.content.startswith("=setup"):
			await start_setup(message)
		if "Seller" in role_names:
			if message.content.startswith("=help"):
				await help_command(message)
			elif message.content.startswith("=clear"):
				await delete_messages(message.channel)
			elif message.content.startswith("=addcategory"):
				await addcategory_command(message)
				await help_command(message)
			elif message.content.startswith("=addchannel"):
				await addchannel_command(message)
				await help_command(message)
			elif message.content.startswith("=additem"):
				await additem_command(message)
				await help_command(message)


client.run(config_discord["bot_token"])
