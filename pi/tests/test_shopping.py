"""The shopping list: sections, adding and crossing off, learning sections, reading it out,
understanding spoken requests, and the den's commands."""
import os
import tempfile

from bt_dragon import ask
from bt_dragon import shopping as sh
from bt_dragon.store import Store

tmp = tempfile.mkdtemp()
store = Store(os.path.join(tmp, "dragon.db"))

# sections
G = sh.guess_section
assert G("eggs") == "Dairy & eggs" and G("Free range eggs") == "Dairy & eggs"
assert G("tomatoes") == G("tomato") == "Produce" and G("frozen pizza") == "Frozen"
assert G("washing up liquid") == "Household" and G("cheddar cheese") == "Dairy & eggs"
assert G("salmon fillets") == "Meat & fish" and G("sumac") == "Other" and G("toilet roll") == "Household"
assert sh.tidy("some free range eggs please") == "Free range eggs" and sh.tidy("a tin of tomatoes") == "Tomatoes"

# the list
sl = sh.ShoppingList(store)
assert sl.add("eggs")[0] == "added" and sl.add("Eggs")[0] == "already" and sl.add("egg")[0] == "already"
assert sl.add("some milk")[1]["name"] == "Milk"
r, sumac = sl.add("sumac")
assert sumac["section"] == "Other"
sl.toggle(sumac["id"])
assert sl.get(sumac["id"])["done"] and sl.add("sumac")[0] == "back" and not sl.get(sumac["id"])["done"]
sl.move(sumac["id"], "Cupboard")                         # remembered for next time
sl.remove("sumac")
assert sl.add("Sumac")[1]["section"] == "Cupboard"
assert "sumac" in sl.words() and "eggs" in sl.words()
sl.toggle(sl.find("milk")["id"])
assert sl.clear_done() == 1 and not sl.find("milk")
assert [s for s, _ in sl.by_section()] == ["Dairy & eggs", "Cupboard"]
assert sl.spoken() == "You have 2 things on your shopping list. Dairy and eggs: eggs. Cupboard: sumac.", sl.spoken()
assert sh.ShoppingList(store).items == sl.items           # kept in the database
assert not sl.remove("bananas")

# understanding requests
P = ask.parse
assert P("add eggs to the shopping list") == {"intent": "shop_add", "items": ["eggs"]}
assert P("add eggs and milk to the shopping list")["items"] == ["eggs", "milk"]
assert P("add salt and vinegar crisps to the list")["items"] == ["salt and vinegar crisps"]
assert P("put some bread on my shopping list")["items"] == ["some bread"]
assert P("add to the shopping list")["items"] == [] and P("add unk to the shopping list")["items"] == []
assert P("take the milk off the shopping list") == {"intent": "shop_remove", "items": ["the milk"]}
assert P("remove eggs from the list")["intent"] == "shop_remove" and P("cross bread off the list")["intent"] == "shop_remove"
assert P("what's on the shopping list")["intent"] == "shop_read" and P("what do we need")["intent"] == "shop_read"
assert P("read out the shopping list")["intent"] == "shop_read"
assert P("what time is it")["intent"] == "time"                     # nothing else changed
assert all(w in ask.VOCABULARY for p in ask.PHRASES for w in p.split())
assert "courgette" in ask.VOCABULARY and "shopping" in ask.VOCABULARY

# the den's commands
from bt_dragon.app import Dragon as App  # noqa: E402


class Fake:
    pass


app = Fake()
app.dot = Fake()
app.dot.shopping = sh.ShoppingList(Store(os.path.join(tmp, "den.db")))
cmd = lambda c, a="": App.shopping_command(app, c, a)  # noqa: E731
assert cmd("SHOPADD", "Bananas")[0].startswith("OK added")
iid = app.dot.shopping.find("bananas")["id"]
assert cmd("SHOPTOGGLE", str(iid)) == ["OK"] and app.dot.shopping.get(iid)["done"]
assert cmd("SHOPMOVE", f"{iid} Frozen") == ["OK"] and app.dot.shopping.get(iid)["section"] == "Frozen"
assert cmd("SHOPMOVE", f"{iid} Nowhere")[0].startswith("ERR")
assert cmd("SHOPCLEAR") == ["OK 1"] and cmd("SHOPDEL", str(iid))[0].startswith("ERR")
assert cmd("SHOPADD", "")[0].startswith("ERR") and cmd("SHOPTOGGLE", "x")[0].startswith("ERR")
# how many, and which shop: shown, read out, and the shop remembered for next time
iid = int(cmd("SHOPADD", "eggs")[0].split()[2])
assert cmd("SHOPEDIT", f'{iid} {{"qty": "12", "store": "Farm Shop"}}') == ["OK"]
it = app.dot.shopping.get(iid)
assert it["qty"] == "12" and it["store"] == "Farm Shop"
mid = int(cmd("SHOPADD", "mince")[0].split()[2])
cmd("SHOPEDIT", f'{mid} {{"qty": "500 g", "store": "Corner Shop"}}')
assert "12 eggs" in app.dot.shopping.spoken() and "500 g of mince" in app.dot.shopping.spoken()
cmd("SHOPDEL", str(iid))
iid = int(cmd("SHOPADD", "Eggs")[0].split()[2])
assert app.dot.shopping.get(iid)["store"] == "Farm Shop" and app.dot.shopping.get(iid)["qty"] == ""
assert cmd("SHOPEDIT", f"{iid} nonsense")[0].startswith("ERR") and cmd("SHOPEDIT", "999 {}")[0].startswith("ERR")
assert App.shopping_data(app)["stores"][:2] == ["Corner Shop", "Farm Shop"] and "Costco" in App.shopping_data(app)["stores"]
for x in list(app.dot.shopping.items):
    app.dot.shopping.remove(item_id=x["id"])
d = App.shopping_data(app)
assert d["sections"] == sh.SECTIONS and d["items"] == []
print("shopping ok")
