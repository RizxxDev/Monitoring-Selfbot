import re
from collections import deque


class Screen:
    def __init__(self, screen_id, match, buttons, patterns=None):
        self.id = screen_id
        self.match = [re.compile(p, re.IGNORECASE) for p in match]
        self.buttons = {key: label for key, label in buttons.items()}
        self._patterns = {key: re.compile(p, re.IGNORECASE) for key, p in (patterns or {}).items()}

    def matches(self, text):
        return any(rx.search(text) for rx in self.match)

    def pattern(self, logical):
        pat = self._patterns.get(logical)
        if pat:
            return pat
        return re.compile(re.escape(self.buttons[logical]), re.IGNORECASE)


SCREENS = [
    Screen(
        "home",
        [r"\bGrowcord[^\S\r\n]+Farm\b"],
        {
            "farm": "Farm",
            "ganti": "Ganti",
            "event": "Event",
            "toko": "Toko",
            "item": "Item",
            "profil": "Profil",
            "market": "Market",
            "guild": "Guild",
            "worlds": "Worlds",
        },
        {"farm": r"\bFarm\b", "toko": r"\bToko\b|\bShop\b", "item": r"\bItems?\b",
         "ganti": r"\bGanti\b|\bChange\b", "event": r"\bEvent\b", "profil": r"\bProfil\b|\bProfile\b",
         "market": r"\bMarket\b", "guild": r"\bGuild\b", "worlds": r"\bWorlds\b"},
    ),
    Screen(
        "fish",
        [r"Fishing\s*Rod", r"Fish\s*inventory"],
        {
            "back": "Back",
            "fish_start": "Fish (1 cast)",
            "bait": "Change Bait",
            "sell": "Sell Fish",
            "shop": "Shop",
            "inventory": "Inventory",
            "codex": "Fish Codex",
            "kembali": "Back",
        },
        {"back": r"\bBack\b", "kembali": r"\bBack\b", "fish_start": r"Fish\s*\(\s*1"},
    ),
    Screen(
        "toko",
        [r"Pilih\s*kategori\s*shop"],
        {
            "locks": "Lock",
            "farmable": "Farmable",
            "gacha": "Gacha",
            "alat": "Alat",
            "consumable": "Consumable",
            "item": "Item",
            "role": "Role",
            "aset": "Aset",
            "convert": "Convert",
            "traits": "Traits",
            "mutations": "Mutations",
            "kembali": "Kembali",
        },
        {"locks": r"\bLocks?\b", "item": r"\bItems?\b", "farmable": r"\bFarmables?\b", "consumable": r"\bConsumables?\b"},
    ),
    Screen(
        "consumables",
        [r"Item\s*•\s*(?:Consumables?|Habis\s*Pakai|Siap\s*Pakai)"],
        {
            "select_item": "Select Item",
            "use": "Use",
            "trade": "Trade",
            "back_item": "← Item",
            "back": "← Item",
            "tools": "Tools",
            "codex": "Item Codex",
        },
        {
            "use": r"\b(?:Use|Gunakan)\b",
            "select_item": r"Select\s*Item|Pilih\s*Item",
            "back_item": r"←\s*(?:Items?|Kembali|Back)\b|^\s*(?:Items?|Kembali|Back)\s*$",
            "back": r"←\s*(?:Items?|Kembali|Back)\b|^\s*(?:Items?|Kembali|Back)\s*$",
        },
    ),
    Screen(
        "items",
        [
            r"##\s*..\s*Item\s*•",
            r"##\s*🎒\s*Item\s*•",
            r"Item\s*•\s*(?:Terbatas|Custom|Unique|Normal)\s*Item",
            r"Item\s*•\s*(?:Terbatas|Custom|Unique|Normal)",
        ],
        {
            "consumable": "Habis Pakai",
            "back": "Kembali",
            "tools": "Tools",
            "ssu": "SSUs",
            "codex": "Item Codex",
        },
        {
            "consumable": r"\b(?:Consumables?|Habis\s*Pakai|Siap\s*Pakai)\b",
            "back": r"←?\s*(?:Kembali|Back)",
        },
    ),
    Screen(
        "shop_consumable",
        [r"Consumables\s*Toko"],
        {
            "beli_arroz": "Beli Arroz",
            "beli_benedict": "Beli Benedict",
            "kembali": "Kembali",
        },
    ),
    Screen(
        "shop_farmable",
        [r"Farmables?\s*(?:Toko|Shop)", r"Toko\s*Farmables?", r"Item\s*•\s*Farmables?", r"Pilih\s*farmable", r"Farmables?\s*Toko"],
        {
            "select_item": "Select Item",
            "buy_max": "Buy Max",
            "kembali": "Kembali",
        },
        {
            "select_item": r"Select\s*(?:Item|Farmable)",
            "buy_max": r"\b(?:Buy|Beli)\s*Max\b|\bMax\b",
            "kembali": r"\bKembali\b|\bBack\b",
        },
    ),
    Screen(
        "locks",
        [
            r"Locks?\s*(?:Toko|Shop)",
            r"Toko\s*Locks?",
            r"Beli\s*WL",
            r"Pembelian\s*WL\s*bebas\s*pajak",
        ],
        {
            "beli_wl": "Beli WL",
            "beli_dl": "Beli DL",
            "beli_bgl": "Beli BGL",
            "beli_all": "Beli All",
            "kembali": "Kembali",
        },
        {
            "beli_wl": r"\b(?:Beli|Buy)\s*WL\b",
            "beli_dl": r"\b(?:Beli|Buy)\s*DL\b",
            "beli_bgl": r"\b(?:Beli|Buy)\s*BGL\b",
            "beli_all": r"\b(?:Beli|Buy)\s*(?:All|Semua|Max)\b",
            "kembali": r"←?\s*(?:Kembali|Back|Toko|Shop)\b",
        },
    ),
]

SOURCES = {s.id: s for s in SCREENS}

# rute: (screen asal, tombol logis, screen tujuan)
EDGES = [
    ("home", "toko", "toko"),
    ("toko", "locks", "locks"),
    ("locks", "kembali", "toko"),
    ("fish", "back", "home"),
    ("toko", "consumable", "shop_consumable"),
    ("shop_consumable", "kembali", "toko"),
    ("toko", "farmable", "shop_farmable"),
    ("shop_farmable", "kembali", "toko"),
    ("toko", "kembali", "home"),
    ("home", "item", "items"),
    ("items", "consumable", "consumables"),
    ("consumables", "back", "items"),
    ("consumables", "back_item", "items"),
    ("items", "back", "home"),
]


def route_steps(current_id, target_id):
    if current_id == target_id:
        return []
    parents = {}
    queue_ = deque([current_id])
    visited = {current_id}
    while queue_:
        node = queue_.popleft()
        for source, btn, nxt in EDGES:
            if source != node or nxt in visited:
                continue
            visited.add(nxt)
            parents[nxt] = (node, btn)
            if nxt == target_id:
                steps = []
                cursor = nxt
                while cursor != current_id:
                    cursor, back_btn = parents[cursor]
                    steps.append(back_btn)
                steps.reverse()
                return steps
            queue_.append(nxt)
    return None


def parse_screen(msg_text):
    for screen in SCREENS:
        if screen.matches(msg_text):
            return screen
    return None
