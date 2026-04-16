import discord
from discord.ext import commands
import json
import os
import asyncio
from datetime import datetime
from aiohttp import web

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TOKEN = os.environ["DISCORD_TOKEN"]
PORT  = int(os.environ.get("PORT", 8080))
ORDERS_FILE = "orders.json"

PRODUCTS = {
    "amoniac":    {"label": "Amoniac",    "price": 4500, "emoji": "🧪"},
    "bicarbonat": {"label": "Bicarbonat", "price": 4500, "emoji": "🧂"},
    "plicuri":    {"label": "Plicuri",    "price": 150,  "emoji": "✉️"},
    "brichete":   {"label": "Brichete",   "price": 150,  "emoji": "🔥"},
    "detergent":  {"label": "Detergent",  "price": 350,  "emoji": "🫧"},
    "seringa":    {"label": "Seringa",    "price": 200,  "emoji": "💉"},
}

def load_orders() -> dict:
    if os.path.exists(ORDERS_FILE):
        with open(ORDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_orders(data: dict):
    with open(ORDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

orders: dict = load_orders()

def get_user_order(user_id: str) -> dict:
    return orders.get(user_id, {}).get("items", {})

def order_total(items: dict) -> int:
    return sum(PRODUCTS[k]["price"] * qty for k, qty in items.items() if k in PRODUCTS)

def fmt_money(amount: int) -> str:
    return f"${amount:,}"

def build_order_embed(user, items: dict) -> discord.Embed:
    embed = discord.Embed(
        title=f"🛒  Comanda lui {user.display_name}",
        color=0xF5A623,
        timestamp=datetime.utcnow(),
    )
    if not items:
        embed.description = "*Coșul tău este gol.*"
        embed.color = 0x888888
    else:
        lines = [f"{PRODUCTS[k]['emoji']} **{PRODUCTS[k]['label']}** × {qty}  →  {fmt_money(PRODUCTS[k]['price']*qty)}"
                 for k, qty in items.items()]
        embed.description = "\n".join(lines)
        embed.add_field(name="💰 Total", value=f"**{fmt_money(order_total(items))}**", inline=False)
    embed.set_footer(text="GTA V Shop Bot")
    return embed

def build_all_orders_embed() -> discord.Embed:
    embed = discord.Embed(title="📋  Toate Comenzile", color=0x2ECC71, timestamp=datetime.utcnow())
    if not orders:
        embed.description = "*Nu există comenzi încă.*"
        return embed
    grand = 0
    for uid, data in orders.items():
        items = data.get("items", {})
        if not items:
            continue
        uname = data.get("username", f"User {uid}")
        total = order_total(items)
        grand += total
        lines = [f"{PRODUCTS[k]['emoji']} {PRODUCTS[k]['label']} ×{qty}  ({fmt_money(PRODUCTS[k]['price']*qty)})"
                 for k, qty in items.items()]
        embed.add_field(name=f"👤 {uname}  —  {fmt_money(total)}", value="\n".join(lines), inline=False)
    embed.add_field(name="━━━━━━━━━━━━━━━━━━", value=f"🏦 **TOTAL GENERAL: {fmt_money(grand)}**", inline=False)
    embed.set_footer(text="GTA V Shop Bot")
    return embed

class ShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for key, info in PRODUCTS.items():
            self.add_item(ProductButton(key, info))
        self.add_item(ViewOrderButton())
        self.add_item(ClearOrderButton())

class ProductButton(discord.ui.Button):
    def __init__(self, key: str, info: dict):
        super().__init__(
            label=f"{info['emoji']} {info['label']}  ({fmt_money(info['price'])})",
            custom_id=f"add_{key}",
            style=discord.ButtonStyle.primary,
            row=list(PRODUCTS.keys()).index(key) // 3,
        )
        self.key = key

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(QuantityModal(self.key))

class ViewOrderButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="📦 Vezi comanda", custom_id="view_order",
                         style=discord.ButtonStyle.secondary, row=2)

    async def callback(self, interaction: discord.Interaction):
        embed = build_order_embed(interaction.user, get_user_order(str(interaction.user.id)))
        await interaction.response.send_message(embed=embed, ephemeral=True)

class ClearOrderButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🗑️ Șterge comanda", custom_id="clear_order",
                         style=discord.ButtonStyle.danger, row=2)

    async def callback(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        if uid in orders:
            orders[uid]["items"] = {}
            save_orders(orders)
        await interaction.response.send_message("✅ Comanda ta a fost ștearsă.", ephemeral=True)

class QuantityModal(discord.ui.Modal, title="Adaugă la comandă"):
    quantity = discord.ui.TextInput(label="Cantitate", placeholder="ex: 2", min_length=1, max_length=4)

    def __init__(self, key: str):
        super().__init__()
        self.key = key
        self.title = f"Adaugă {PRODUCTS[key]['emoji']} {PRODUCTS[key]['label']}"

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qty = int(self.quantity.value)
            if qty <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ Te rog introdu un număr valid (> 0).", ephemeral=True)
            return
        uid = str(interaction.user.id)
        if uid not in orders:
            orders[uid] = {"username": interaction.user.display_name, "items": {}}
        orders[uid]["username"] = interaction.user.display_name
        orders[uid]["items"][self.key] = orders[uid]["items"].get(self.key, 0) + qty
        save_orders(orders)
        p = PRODUCTS[self.key]
        embed = discord.Embed(
            title="✅ Adăugat la comandă!",
            description=(f"{p['emoji']} **{p['label']}** × {qty}  →  {fmt_money(p['price']*qty)}\n\n"
                         f"💰 Total comandă: **{fmt_money(order_total(orders[uid]['items']))}**"),
            color=0x2ECC71,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class AdminView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📋 Vezi toate comenzile", custom_id="admin_all",
                       style=discord.ButtonStyle.success)
    async def all_orders(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=build_all_orders_embed(), ephemeral=True)

    @discord.ui.button(label="🗑️ Șterge TOATE comenzile", custom_id="admin_clear_all",
                       style=discord.ButtonStyle.danger)
    async def clear_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ConfirmClearModal())

class ConfirmClearModal(discord.ui.Modal, title="Confirmare ștergere"):
    confirm = discord.ui.TextInput(label='Scrie "CONFIRM" pentru a șterge',
                                   placeholder="CONFIRM", min_length=7, max_length=7)

    async def on_submit(self, interaction: discord.Interaction):
        if self.confirm.value.strip().upper() == "CONFIRM":
            orders.clear()
            save_orders(orders)
            await interaction.response.send_message("✅ Toate comenzile au fost șterse.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Anulat. Scrie exact CONFIRM.", ephemeral=True)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    bot.add_view(ShopView())
    bot.add_view(AdminView())
    print(f"✅ Bot pornit ca {bot.user}  (ID: {bot.user.id})")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

@bot.command(name="shop")
@commands.has_permissions(administrator=True)
async def post_shop(ctx):
    embed = discord.Embed(
        title="🏪  GTA V Shop",
        description=("Bun venit la magazin! Apasă un buton pentru a adăuga produse la comanda ta.\n\n"
                     + "\n".join(f"{v['emoji']} **{v['label']}** — {fmt_money(v['price'])}"
                                 for v in PRODUCTS.values())),
        color=0xF5A623,
    )
    embed.set_footer(text="Folosește butoanele de mai jos pentru a gestiona comanda ta.")
    await ctx.send(embed=embed, view=ShopView())
    await ctx.message.delete()

@bot.command(name="adminpanel")
@commands.has_permissions(administrator=True)
async def post_admin(ctx):
    embed = discord.Embed(title="⚙️  Panou Admin",
                          description="Gestionează toate comenzile de pe server.", color=0xE74C3C)
    await ctx.send(embed=embed, view=AdminView())
    await ctx.message.delete()

@bot.command(name="orders")
@commands.has_permissions(administrator=True)
async def show_orders(ctx):
    await ctx.send(embed=build_all_orders_embed())

async def handle_health(_request):
    return web.Response(text="OK")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_health)
    app.router.add_get("/health", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    print(f"🌐 Health server running on port {PORT}")

async def main():
    async with bot:
        await start_web_server()
        await bot.start(TOKEN)

asyncio.run(main())
