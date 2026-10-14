"""
The shopping list: kept on the Pi, shown on its own page in the den (/shopping), and
filled by voice through the Dot ("Add eggs to the shopping list").

Items are sorted into the sections of a typical supermarket. A built-in catalogue of
everyday groceries says which section each belongs in (and gives Harald the words to
listen for). Anything else goes under "Other"; move it in the den and he remembers where
it belongs from then on.
"""
import re
import time

SECTIONS = ["Produce", "Dairy & eggs", "Meat & fish", "Bakery", "Frozen", "Cupboard", "Drinks",
            "Household", "Toiletries", "Other"]

CATALOGUE = {
    "Produce": """cranberries pomegranate figs dates apricots nectarines grapefruit rhubarb satsumas clementines tangerines coconut papaya shallots fennel okra plantain berries chilli radish leek pears apple apples banana bananas orange oranges lemon lemons lime limes grapes pear pears
        peach peaches plum plums strawberries raspberries blueberries blackberries cherries melon
        watermelon pineapple mango kiwi avocado avocados tomato tomatoes potato potatoes
        sweet potatoes onion onions red onion spring onions garlic ginger carrot carrots broccoli
        cauliflower cabbage lettuce spinach kale rocket salad cucumber pepper peppers courgette
        courgettes aubergine mushrooms celery leeks peas green beans sweetcorn corn parsnips swede
        turnip beetroot radishes herbs parsley coriander basil mint chillies fruit veg vegetables
        pumpkin squash asparagus brussels sprouts""",
    "Dairy & eggs": """buttermilk ricotta brie stilton camembert quark kefir paneer creme fraiche milk eggs egg butter cheese cheddar mozzarella parmesan feta halloumi cream
        cheese cream double cream single cream sour cream yoghurt yogurt greek yoghurt custard
        margarine spread oat milk almond milk soya milk""",
    "Meat & fish": """duck venison meatballs burgers crab mussels scallops sardines anchovies trout sausage chicken chicken breasts chicken thighs beef mince steak pork pork chops lamb
        bacon sausages ham turkey gammon salami chorizo pepperoni fish salmon cod haddock tuna steaks
        prawns mackerel fish fingers meat""",
    "Bakery": """pastries doughnuts brioche sourdough pancakes waffles flatbreads bread loaf rolls bread rolls baguette wraps tortillas pitta naan crumpets muffins
        bagels croissants cake scones teacakes""",
    "Frozen": """sorbet ice cream frozen peas frozen chips chips pizza oven chips frozen veg ice ice cubes
        ice lollies""",
    "Cupboard": """couscous quinoa barley tahini hummus olives capers pickles chutney horseradish cinnamon paprika cumin nutmeg vanilla custard powder syrup treacle jelly pasta spaghetti rice noodles flour sugar salt black pepper oil olive oil vinegar
        cereal porridge oats muesli tinned tomatoes beans baked beans chickpeas lentils soup stock
        stock cubes gravy ketchup mayonnaise mustard brown sauce soy sauce pesto jam honey peanut
        butter marmalade chocolate spread biscuits crisps crackers chocolate sweets nuts raisins
        tea bags coffee hot chocolate tuna tinned tuna sweetcorn tin curry paste spices herbs
        baking powder yeast cocoa popcorn""",
    "Drinks": """smoothies milkshake water juice orange juice apple juice squash lemonade cola coke fizzy drinks beer
        wine cider sparkling water tonic""",
    "Household": """dishcloths gloves toilet roll toilet paper kitchen roll bin bags washing up liquid washing powder
        laundry detergent fabric conditioner dishwasher tablets bleach cleaner sponges cling film
        foil tin foil baking paper batteries light bulbs matches candles tissues""",
    "Toiletries": """shampoo conditioner soap shower gel toothpaste toothbrush deodorant razors
        shaving foam cotton wool cotton buds plasters paracetamol ibuprofen hand cream moisturiser
        sun cream tampons pads nappies wipes""",
}

# a few words that decide the section whatever else is in the name ("frozen pizza", "dog food")
KEYWORDS = [("frozen", "Frozen"), ("tinned", "Cupboard"), ("tin", "Cupboard"), ("juice", "Drinks"),
            ("cheese", "Dairy & eggs"), ("milk", "Dairy & eggs"), ("yoghurt", "Dairy & eggs"),
            ("bread", "Bakery"), ("sauce", "Cupboard"), ("crisps", "Cupboard"), ("chicken", "Meat & fish"),
            ("fish", "Meat & fish"), ("shampoo", "Toiletries"), ("cleaner", "Household")]


def _norm(name):
    name = re.sub(r"[^a-z0-9' &-]", " ", name.lower())
    return re.sub(r"\s+", " ", name).strip()


def _singular(word):
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("oes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def _key(name):
    """What makes two names the same item: 'Eggs' = 'egg', 'Tomatoes' = 'tomato'."""
    return " ".join(_singular(w) for w in _norm(name).split())


# multi-word items, written out so they're matched whole
PHRASE_ITEMS = {
    "Produce": ["cherry tomatoes", "new potatoes", "butternut squash", "red cabbage", "pak choi", "bean sprouts",
                "passion fruit", "red onion", "spring onions", "sweet potatoes", "green beans", "brussels sprouts"],
    "Dairy & eggs": ["goats cheese", "creme fraiche", "cream cheese", "double cream", "single cream", "sour cream", "greek yoghurt",
                     "oat milk", "almond milk", "soya milk"],
    "Meat & fish": ["chicken breasts", "chicken thighs", "pork chops", "tuna steaks", "fish fingers"],
    "Bakery": ["bread rolls"],
    "Frozen": ["fish and chips", "ice cream", "frozen peas", "oven chips", "frozen veg", "ice cubes", "ice lollies"],
    "Cupboard": ["cranberry sauce", "mint sauce", "maple syrup", "golden syrup", "gravy granules",
                 "salt and vinegar crisps", "cheese and onion crisps", "sweet and sour sauce",
                 "macaroni and cheese", "olive oil", "black pepper", "tinned tomatoes", "baked beans", "stock cubes", "brown sauce",
                 "soy sauce", "peanut butter", "chocolate spread", "tea bags", "hot chocolate",
                 "tinned tuna", "curry paste", "baking powder"],
    "Drinks": ["orange juice", "apple juice", "fizzy drinks", "sparkling water"],
    "Household": ["dog food", "cat food", "cat litter", "air freshener", "toilet roll", "toilet paper", "kitchen roll", "bin bags", "washing up liquid",
                  "washing powder", "laundry detergent", "fabric conditioner", "dishwasher tablets",
                  "cling film", "tin foil", "baking paper", "light bulbs"],
    "Toiletries": ["shower gel", "shaving foam", "cotton wool", "cotton buds", "hand cream", "sun cream"],
}

_INDEX = {}
for _section, _text in CATALOGUE.items():
    for _w in _text.split():
        _INDEX.setdefault(_key(_w), _section)
for _section, _items in PHRASE_ITEMS.items():
    for _p in _items:
        _INDEX[_key(_p)] = _section
# words that are in the catalogue under more than one section belong to the first listed,
# except these, which are better guesses on their own
_INDEX.update({_key("cream"): "Dairy & eggs", _key("chips"): "Frozen", _key("pepper"): "Produce",
               _key("ice"): "Frozen", _key("tin"): "Cupboard", _key("squash"): "Drinks",
               _key("herbs"): "Produce", _key("sweetcorn"): "Produce", _key("tuna"): "Meat & fish"})


def known_items():
    """Every item name the catalogue knows, as plain words (for the recognizer)."""
    names = set()
    for text in CATALOGUE.values():
        names.update(text.split())
    for items in PHRASE_ITEMS.values():
        names.update(items)
    return names


def is_known(name):
    """A whole item name the catalogue knows ('salt and vinegar crisps')."""
    return _key(tidy(name)) in _INDEX


def guess_section(name, learned=None):
    k = _key(name)
    if learned and k in learned:
        return learned[k]
    if k in _INDEX:
        return _INDEX[k]
    words = k.split()
    for word, section in KEYWORDS:              # "frozen pizza", "dog shampoo"
        if _singular(word) in words:
            return section
    for n in range(len(words) - 1, 0, -1):      # "cheddar cheese" -> "cheese", "free range eggs" -> "eggs"
        for i in range(len(words) - n + 1):
            part = " ".join(words[i:i + n])
            if part in _INDEX:
                return _INDEX[part]
    return "Other"


_LEADS = sorted(["some", "a", "an", "the", "more", "another", "a few", "a couple of", "a bottle of",
                 "a pack of", "a packet of", "a tin of", "a jar of", "a bag of", "a box of", "a loaf of",
                 "two", "three", "four", "some more"], key=len, reverse=True)


def tidy(name):
    """How an item is written on the list: 'some free range eggs' -> 'Free range eggs'."""
    name = re.sub(r"\bplease\b", " ", _norm(name)).strip()
    name = re.sub(r"\s+", " ", name)
    for lead in _LEADS:                      # longest first: "a tin of" before "a"
        if name.startswith(lead + " "):
            name = name[len(lead) + 1:]
            break
    return name[:1].upper() + name[1:60] if name else ""


def _with_qty(name, qty):
    """'eggs', '12' -> '12 eggs'; 'mince', '500 g' -> '500 g of mince'."""
    if not qty:
        return name
    return f"{qty} {name}" if re.fullmatch(r"\d+", qty) else f"{qty} of {name}"


class ShoppingList:
    def __init__(self, store):
        self.store = store
        self.items = store.get("shopping_list") or []
        self.learned = store.get("shopping_learned") or {}
        self.stores = store.get("shopping_stores") or {}     # item -> the shop you buy it at
        self._next = max([i["id"] for i in self.items] + [0]) + 1
        self.changed = time.time()

    def save(self):
        self.store.put("shopping_list", self.items)
        self.changed = time.time()

    def find(self, name):
        k = _key(tidy(name))
        return next((i for i in self.items if _key(i["name"]) == k), None)

    def get(self, item_id):
        return next((i for i in self.items if i["id"] == item_id), None)

    def add(self, name):
        """Returns ('added' | 'back' | 'already', item) or (None, None) for an empty name."""
        name = tidy(name)
        if not name:
            return None, None
        old = self.find(name)
        if old:
            if old["done"]:
                old["done"] = False
                self.save()
                return "back", old
            return "already", old
        item = {"id": self._next, "name": name, "section": guess_section(name, self.learned),
                "done": False, "added": int(time.time()), "qty": "",
                "store": self.stores.get(_key(name), "")}
        self._next += 1
        self.items.append(item)
        self.save()
        return "added", item

    def remove(self, name=None, item_id=None):
        item = self.get(item_id) if item_id is not None else self.find(name or "")
        if item:
            self.items.remove(item)
            self.save()
        return item

    def toggle(self, item_id):
        item = self.get(item_id)
        if item:
            item["done"] = not item["done"]
            self.save()
        return item

    def set_details(self, item_id, qty=None, store=None):
        """How many to buy, and the shop to buy it at. The shop is remembered for next time."""
        item = self.get(item_id)
        if not item:
            return None
        if qty is not None:
            item["qty"] = re.sub(r"\s+", " ", str(qty)).strip()[:20]
        if store is not None:
            store = re.sub(r"\s+", " ", str(store)).strip()[:24]
            item["store"] = store
            k = _key(item["name"])
            if store:
                self.stores[k] = store
            else:
                self.stores.pop(k, None)
            self.store.put("shopping_stores", self.stores)
        self.save()
        return item

    def known_stores(self):
        """Shops used before (for the den's suggestions), plus a few common ones."""
        used = sorted({s for s in self.stores.values() if s} | {i.get("store") for i in self.items if i.get("store")})
        return used + [s for s in ("Aldi", "Costco", "Kroger", "Lidl", "Target", "Tesco",
                                   "Trader Joe's", "Walmart") if s not in used]

    def move(self, item_id, section):
        """Put an item in another section, and remember that for next time."""
        item = self.get(item_id)
        if item and section in SECTIONS:
            item["section"] = section
            self.learned[_key(item["name"])] = section
            self.store.put("shopping_learned", self.learned)
            self.save()
        return item

    def clear_done(self):
        n = len(self.items)
        self.items = [i for i in self.items if not i["done"]]
        self.save()
        return n - len(self.items)

    def by_section(self, include_done=True):
        out = []
        for s in SECTIONS:
            items = [i for i in self.items if i["section"] == s and (include_done or not i["done"])]
            if items:
                out.append((s, sorted(items, key=lambda i: (i["done"], i["name"].lower()))))
        return out

    def words(self):
        """Words the recognizer should know: the catalogue, plus anything ever put on the list."""
        names = known_items() | {_norm(i["name"]) for i in self.items} | set(self.learned)
        return sorted({w for n in names for w in n.split() if w.isalpha() or "'" in w})

    def spoken(self):
        """The list read aloud, section by section (crossed-off items left out)."""
        groups = self.by_section(include_done=False)
        if not groups:
            return "Your shopping list is empty."
        n = sum(len(items) for _, items in groups)
        parts = [f"You have {n} thing{'s' if n != 1 else ''} on your shopping list."]
        for section, items in groups:
            names = [_with_qty(i["name"].lower(), i.get("qty", "")) for i in items]
            listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
            parts.append(f"{section.replace('&', 'and')}: {listed}.")
        return " ".join(parts)
