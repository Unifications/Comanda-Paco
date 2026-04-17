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

TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN sau TOKEN nu este setat.")

PORT = int(os.environ.get("PORT", 8080))

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
FISIER_COMENZI = os.path.join(DATA_DIR, "orders.json")

PRODUSE = {
    "amoniac": {"label": "Amoniac", "price": 4500, "emoji": "🧪"},
    "bicarbonat": {"label": "Bicarbonat", "price": 4500, "emoji": "🧂"},
    "plicuri": {"label": "Plicuri", "price": 150, "emoji": "✉️"},
    "brichete": {"label": "Brichete", "price": 150, "emoji": "🔥"},
    "detergent": {"label": "Detergent", "price": 350, "emoji": "🫧"},
    "seringa": {"label": "Seringă", "price": 200, "emoji": "💉"},
}


def incarca_comenzi() -> dict:
    if os.path.exists(FISIER_COMENZI):
        try:
            with open(FISIER_COMENZI, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def salveaza_comenzi(data: dict):
    with open(FISIER_COMENZI, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


comenzi: dict = incarca_comenzi()


def ia_comanda_utilizator(user_id: str) -> dict:
    return comenzi.get(user_id, {}).get("items", {})


def calculeaza_total(items: dict) -> int:
    return sum(PRODUSE[k]["price"] * qty for k, qty in items.items() if k in PRODUSE)


def format_bani(suma: int) -> str:
    return f"${suma:,}"


def calculeaza_totaluri_materiale() -> dict:
    totaluri = {cheie: 0 for cheie in PRODUSE.keys()}

    for _, data in comenzi.items():
        items = data.get("items", {})
        for cheie, cantitate in items.items():
            if cheie in totaluri:
                totaluri[cheie] += cantitate

    return totaluri


def construieste_embed_comanda(user, items: dict) -> discord.Embed:
    embed = discord.Embed(
        title=f"🛒 Comanda lui {user.display_name}",
        color=0xF5A623,
        timestamp=datetime.utcnow(),
    )

    if not items:
        embed.description = "*Coșul este gol.*"
        embed.color = 0x888888
    else:
        linii = [
            f"{PRODUSE[k]['emoji']} **{PRODUSE[k]['label']}** × {qty} → {format_bani(PRODUSE[k]['price'] * qty)}"
            for k, qty in items.items()
        ]
        embed.description = "\n".join(linii)
        embed.add_field(
            name="💰 Total",
            value=f"**{format_bani(calculeaza_total(items))}**",
            inline=False
        )

    embed.set_footer(text="Bot Magazin GTA V")
    return embed


def construieste_embed_toate_comenzile() -> discord.Embed:
    embed = discord.Embed(
        title="📋 Toate comenzile",
        color=0x2ECC71,
        timestamp=datetime.utcnow()
    )

    if not comenzi:
        embed.description = "*Nu există comenzi încă.*"
        return embed

    total_general = 0
    exista_comenzi = False

    for uid, data in comenzi.items():
        items = data.get("items", {})
        if not items:
            continue

        exista_comenzi = True
        nume = data.get("username", f"Utilizator {uid}")
        total = calculeaza_total(items)
        total_general += total

        linii = [
            f"{PRODUSE[k]['emoji']} {PRODUSE[k]['label']} × {qty} ({format_bani(PRODUSE[k]['price'] * qty)})"
            for k, qty in items.items()
        ]

        embed.add_field(
            name=f"👤 {nume} — {format_bani(total)}",
            value="\n".join(linii),
            inline=False
        )

    if not exista_comenzi:
        embed.description = "*Nu există comenzi încă.*"
        return embed

    totaluri_materiale = calculeaza_totaluri_materiale()
    linii_materiale = []

    for cheie, cantitate in totaluri_materiale.items():
        if cantitate > 0:
            produs = PRODUSE[cheie]
            pret_total_material = produs["price"] * cantitate
            linii_materiale.append(
                f"{produs['emoji']} **{produs['label']}** — Cantitate totală: **{cantitate}** | Valoare totală: **{format_bani(pret_total_material)}**"
            )

    if linii_materiale:
        embed.add_field(
            name="🧾 Total pe fiecare material",
            value="\n".join(linii_materiale),
            inline=False
        )

    embed.add_field(
        name="━━━━━━━━━━━━━━━━━━",
        value=f"🏦 **TOTAL GENERAL: {format_bani(total_general)}**",
        inline=False
    )
    embed.set_footer(text="Bot Magazin GTA V")
    return embed


class VizualizareMagazin(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        for key, info in PRODUSE.items():
            self.add_item(ButonProdus(key, info))

        self.add_item(ButonVeziComanda())
        self.add_item(ButonStergeComanda())


class ButonProdus(discord.ui.Button):
    def __init__(self, key: str, info: dict):
        super().__init__(
            label=f"{info['emoji']} {info['label']} ({format_bani(info['price'])})",
            custom_id=f"adauga_{key}",
            style=discord.ButtonStyle.primary,
            row=list(PRODUSE.keys()).index(key) // 3,
        )
        self.key = key

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ModalCantitate(self.key))


class ButonVeziComanda(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="📦 Vezi comanda",
            custom_id="vezi_comanda",
            style=discord.ButtonStyle.secondary,
            row=2
        )

    async def callback(self, interaction: discord.Interaction):
        embed = construieste_embed_comanda(
            interaction.user,
            ia_comanda_utilizator(str(interaction.user.id))
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ButonStergeComanda(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="🗑️ Șterge comanda",
            custom_id="sterge_comanda",
            style=discord.ButtonStyle.danger,
            row=2
        )

    async def callback(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)

        if uid in comenzi:
            comenzi[uid]["items"] = {}
            salveaza_comenzi(comenzi)

        await interaction.response.send_message(
            "✅ Comanda ta a fost ștearsă.",
            ephemeral=True
        )


class ModalCantitate(discord.ui.Modal, title="Adaugă produs"):
    cantitate = discord.ui.TextInput(
        label="Cantitate",
        placeholder="Exemplu: 2",
        min_length=1,
        max_length=4
    )

    def __init__(self, key: str):
        super().__init__()
        self.key = key
        self.title = f"Adaugă {PRODUSE[key]['emoji']} {PRODUSE[key]['label']}"

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qty = int(self.cantitate.value)
            if qty <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "❌ Te rog să introduci un număr valid mai mare decât 0.",
                ephemeral=True
            )
            return

        uid = str(interaction.user.id)

        if uid not in comenzi:
            comenzi[uid] = {
                "username": interaction.user.display_name,
                "items": {}
            }

        comenzi[uid]["username"] = interaction.user.display_name
        comenzi[uid]["items"][self.key] = comenzi[uid]["items"].get(self.key, 0) + qty
        salveaza_comenzi(comenzi)

        produs = PRODUSE[self.key]
        embed = discord.Embed(
            title="✅ Produs adăugat",
            description=(
                f"{produs['emoji']} **{produs['label']}** × {qty} → {format_bani(produs['price'] * qty)}\n\n"
                f"💰 Total comandă: **{format_bani(calculeaza_total(comenzi[uid]['items']))}**"
            ),
            color=0x2ECC71,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


class VizualizareAdmin(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="📋 Vezi toate comenzile",
        custom_id="admin_toate_comenzile",
        style=discord.ButtonStyle.success
    )
    async def toate_comenzile(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=construieste_embed_toate_comenzile(),
            ephemeral=True
        )

    @discord.ui.button(
        label="🗑️ Șterge toate comenzile",
        custom_id="admin_sterge_toate",
        style=discord.ButtonStyle.danger
    )
    async def sterge_toate(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ModalConfirmareStergere())


class ModalConfirmareStergere(discord.ui.Modal, title="Confirmare ștergere totală"):
    confirmare = discord.ui.TextInput(
        label='Scrie "CONFIRM" pentru a șterge tot',
        placeholder="CONFIRM",
        min_length=7,
        max_length=7
    )

    async def on_submit(self, interaction: discord.Interaction):
        if self.confirmare.value.strip().upper() == "CONFIRM":
            comenzi.clear()
            salveaza_comenzi(comenzi)
            await interaction.response.send_message(
                "✅ Toate comenzile au fost șterse.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Acțiune anulată. Trebuie să scrii exact CONFIRM.",
                ephemeral=True
            )


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    bot.add_view(VizualizareMagazin())
    bot.add_view(VizualizareAdmin())
    print(f"✅ Bot pornit ca {bot.user} (ID: {bot.user.id})")
    print(f"📁 Fișier comenzi: {FISIER_COMENZI}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


@bot.command(name="magazin")
@commands.has_permissions(administrator=True)
async def comanda_magazin(ctx):
    embed = discord.Embed(
        title="🏪 Magazin GTA V",
        description=(
            "Bun venit la magazin. Apasă un buton pentru a adăuga produse în comanda ta.\n\n"
            + "\n".join(
                f"{v['emoji']} **{v['label']}** — {format_bani(v['price'])}"
                for v in PRODUSE.values()
            )
        ),
        color=0xF5A623,
    )
    embed.set_footer(text="Folosește butoanele de mai jos pentru a-ți gestiona comanda.")
    await ctx.send(embed=embed, view=VizualizareMagazin())
    await ctx.message.delete()


@bot.command(name="panouadmin")
@commands.has_permissions(administrator=True)
async def comanda_panou_admin(ctx):
    embed = discord.Embed(
        title="⚙️ Panou administrator",
        description="De aici poți gestiona toate comenzile de pe server.",
        color=0xE74C3C
    )
    await ctx.send(embed=embed, view=VizualizareAdmin())
    await ctx.message.delete()


@bot.command(name="toatecomenzile")
@commands.has_permissions(administrator=True)
async def comanda_toate_comenzile(ctx):
    await ctx.send(embed=construieste_embed_toate_comenzile())


@bot.command(name="comandamea")
async def comanda_mea(ctx):
    embed = construieste_embed_comanda(
        ctx.author,
        ia_comanda_utilizator(str(ctx.author.id))
    )
    await ctx.send(embed=embed)


@bot.command(name="comanda")
@commands.has_permissions(administrator=True)
async def comanda_membru(ctx, membru: discord.Member):
    embed = construieste_embed_comanda(
        membru,
        ia_comanda_utilizator(str(membru.id))
    )
    await ctx.send(embed=embed)


async def healthcheck(_request):
    return web.Response(text="OK")


async def porneste_server_web():
    app = web.Application()
    app.router.add_get("/", healthcheck)
    app.router.add_get("/health", healthcheck)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    print(f"🌐 Server healthcheck pornit pe portul {PORT}")


async def main():
    async with bot:
        await porneste_server_web()
        await bot.start(TOKEN)


asyncio.run(main())
