# ᛒᛏ·ᛞᚱᚨᚷᛟᚾ  BT Dragon

**A Bluetooth-eating Viking dragon for a Raspberry Pi Zero 2 W.**

BT Dragon turns a Raspberry Pi Zero 2 W (on its own, or as part of an old Pwnagotchi with its e-ink screen) into a different kind of pocket pet: a cartoon Viking dragon who snacks on the Bluetooth gadgets around you, treats himself to Wi-Fi networks, goes on walks with you (with the use of an external battery), makes friends with other dragons, and engages in a virtual butterfly cultivation hobby. He's called **Harald** unless you rename him in the Den (his control panel), in which case the new name is used everywhere the old one was. The rest of this document assumes the default name. The default artwork is purposely gender-neutral so your dragon can rock any name of choice.

Optional GPS integration unlocks the ability to "conquer" squares on a real-world map by traveling through them with Harald, "visiting" real public-access historic landmarks and green spaces (major parks, etc.) by passing near them, and participating in the Wigle.net wireless access point discovery "point-scoring" leaderboards and rankings. If connected to the sensors of a user's smartphone, Harald can pass on interesting information about the types and numbers of navigational satellites he can see (using the phone's GPS) which are added to his "star" collection, changes in weather (detected via the phone's air pressure sensor), and other features. There is even an included way to connect him to an old 2nd Gen Echo Dot that has been unlocked and rooted, giving the user a way to ask Harald some basic questions and issue certain commands, either by pressing the action button or by using a hands-free wake word (with lots of room for additional development).

**Why Harald?** He's named after **Harald "Bluetooth" Gormsson**, a Viking king of Denmark who died around 986. He's remembered for uniting Denmark's tribes under one crown, for bringing Christianity to the Danes, and for the great runestone he raised at Jelling, which Danes still call their country's birth certificate. Nobody knows for sure where his nickname came from: perhaps a dead, dark tooth, or an older word meaning "dark chieftain". In 1997, engineers from Intel, Ericsson and Nokia were looking for a working name for a new short-range radio standard that would unite phones and computers, the way Harald had united the Danes. They called it Bluetooth, and the name stuck. The Bluetooth logo is Harald's initials in runes: ᚼ (H) and ᛒ (B), joined together. Thus, this Bluetooth-eating dragon is Viking-themed and named Harald in honor of that legacy.

![Harald's screen](docs/screen.png)

> **Prototype release.** Everything here is being tested on the author's own hardware, but it hasn't been tried on many setups yet. Expect rough edges, and please open an issue when you find one.
>
> **Placeholder art.** Harald's current pixel art is an AI-generated placeholder, made only so the prototype could be designed and tuned. It will be replaced with the author's own original, hand-drawn artwork before the first release. The Den also allows an individual user to easily upload their own artwork or artwork they have permission to use. AI-generated placeholder art is also currently used throughout the insect collection for the prototype testing phase. The insect art is purposely general and makes no effort to replicate individual species; it consists of a simple mock-up with the word "TEMP" in large letters across it. It is the author's intention to replace all of the insect art with human art that reflects each individual species, though this process will likely take some time.
>
> ### 🤖 AI disclaimer
> **The project author's personal ethics on AI use and the author's intentions.**
> The project author's educational backgrounds are in traditional art, biology, and psychology - not computer science, therefore AI was heavily used to code this project. The project author is aware of the risks and environmental consequences associated with AI use, therefore their personal stance on anything they create with mostly or wholly AI-generated code is that the code must be free and open source (FOSS) to all and the end product must benefit human users in a long-term, tangible manner that also respects user's privacy at every turn. Harald was created as a way to re-use old hardware (reducing potential e-waste) inexpensively and in a fun way that promotes curiosity and education about the invisible signals that surround us. Harald also encourages the physical activity of the user towards finding real new and novel signals to "feed" their dragon (which a GPS link enhances by adding "lands" to conquer by real-world exploration with Harald and the WiGLE account upload feature). There is also an insect collection feature which teaches the user (using verified facts from educational public bodies and charities) about the insects present in their country. It is the project author's sincere hope that their intentions behind the creation of Harald are understood and respected even if their choice to use AI for this project is ultimately not.
>
> **BT Dragon was written with Claude, Anthropic's AI assistant.** Claude wrote essentially all of the code, the dragon's current placeholder pixel art and the original documentation, working from detailed conversations with the project's author over multiple sessions. This document was originally written by Claude but then heavily reviewed and edited by the project author for content and accuracy before being uploaded to GitHub.
>
>The author came up with the idea for Harald and directed the work: the features, how Harald's food, joy and leveling should feel, the privacy rules (passive only, no following other people's devices), and every design decision along the way. The author also tested it on real hardware, found the bugs, and experimented with Harald to tune him. Bugs and ideas for improvement were reported to Claude, who performed troubleshooting and bugfixing in the code itself. Claude's own testing was limited to simulations and automated checks; anything marked "tested" in this README was genuinely tested by the author on their real devices (which are named).
>
> **If you're uncomfortable using AI-assisted code for any reason, please don't use this program.** That is your choice, it is perfectly reasonable, and this disclaimer is here so you can make it before downloading (if you're reading this on GitHub) or installing anything. That being said, please respect that the project author has been completely open and honest about the contents of this disclaimer and the fact of its inclusion, especially in a world where more and more individuals are attempting to pass off partially or completely AI-generated work as their own, either through direct deceit or by omission of fact.
>
>If you're still interested in learning about Harald after all that, let's move on...



---

## Contents

This guide grows with your setup. Start with the bare minimum, a Pi on your home network, and add the next level only when you want what it brings.

| Level | You add | He gains |
|---|---|---|
| [1. The basics](#level-1-the-basics) | A Raspberry Pi Zero 2 W, a microSD card, your home Wi-Fi and a computer | Bluetooth snacks, Wi-Fi treats, types of gadget, friends, finding your own gadgets, tracker warnings, the moon, a shopping list and calendar, kitchen timers, typed questions, the weather and local weather news from his Lair, a Butterfly Garden (from level 5), the Den |
| [2. Out and about](#level-2-out-and-about) | Your smartphone's hotspot and a USB power bank | Walks together: more to eat, dragons to meet, the Den in your pocket. Optionally, much of Level 3 without phone apps: a USB GPS receiver, or claiming land by Wi-Fi |
| [3. Your phone's senses](#level-3-your-phones-senses) | An Android phone sharing its sensors | Walks tracked and logged, wardriving, conquering the map, landmarks, parks, stars, weather, sunshine, his voice through your phone |
| [4. A voice and ears](#level-4-a-voice-and-ears-echo-dot) | A rooted Echo Dot (2nd generation) | Spoken news, a mood ring, using your own voice to ask questions and set timers, verbally add to your calendar and shopping list, the "Hey dragon" wake word for hands-free use |

Then:

- [Privacy: what stays where](#privacy-what-stays-where)
- [Responsible use](#responsible-use)
- [How it works](#how-it-works)
- [License](#license)

---

## Level 1: The basics

A Raspberry Pi Zero 2 W on your home Wi-Fi, with no screen, no phone and nothing else. You see him and look after him through the **Den**, an HTML page he serves directly to your computer's browser.

### What he does at this level

- **Snacks and treats.** He eats the Bluetooth gadgets around him (snacks) and treats himself to Wi-Fi networks he hasn't seen before. Networks he already knows regrow like berry bushes.
- **Types.** Every type of gadget he eats ("AirPods Pro", "JBL speaker") goes in his life list. A new type is a feast. (On his screen, **TYPES** is how many he knows. They used to be called "species", but now that the Butterfly Garden has real insect species, gadgets are "types".)
- **Moods and meters.** Joy, belly and pack, his level and XP, and a face that shows how he feels (see [his meters](#his-meters) below).
- **Dragon friends.** He meets other BT Dragons (and recognizes Pwnagotchis) by Bluetooth.
- **Finding your own gadgets.** Mark your headphones, speakers and so on as **pals**, and the Den's **Find** meter plays "hot and cold" with them.
- **Unknown-tracker warning.** If an AirTag-style tracker away from its owner keeps showing up with him, he raises the alarm.
- **A diary** of everything he did, kept on the Pi, downloadable as spreadsheet files.
- **The moon.** He knows the moon phases without having to check anything online besides the current date and time: they're worked out on the Pi from the date, with the formulas astronomers use. On the day of each new moon, first quarter, full moon and last quarter he gets a burst of joy (the full moon is the biggest) and announces it, Norse style: in the old myths the moon is the god Máni, chased across the sky by the wolf Hati (**"MANI SHINES! FULL MOON TONIGHT"**). The Den shows tonight's moon and when the next phases are.

- **A shopping list and a calendar.** Each has its own page in the Den (*Shopping list and calendar*). A calendar reminder shows on his screen (and the Den's copy of it) only as **"REMINDER: EVENT IN 1 HOUR!"**, so anyone glancing at him can't read your plans. Asking about them out loud needs ears (Level 4), but adding things, ticking them off and reminders all work now.
- **Ask Harald: typed questions and kitchen timers.** In the Den's **Ask Harald** section, type a question and his answer appears underneath: the time here or in a big city, the date, the shopping list, what's on the calendar, or the weather. "Set a pasta timer for twelve minutes" works too: when it ends, his screen says **TIMER DONE!** and the Den shows a **Stop** button. If the answer is short enough for his screen, it shows there too, as **"ANSWER: IT'S 14°C (57°F) AT THE LAIR"**; a longer one shows **"ANSWER: A LONG RESPONSE. CHECK THE DEN."** (that's for the screen only: if he has a voice, he says the whole answer as usual). He only knows a set range of questions (the full list is under [Asking him questions](#what-he-gains-1) in Level 4), and his answers don't come from a search engine: for anything else, use a real search engine (DuckDuckGo, for example) or an assistant that uses one (Hey Google, Siri, Alexa and so on).
- **Harald's Lair: the weather at home.** In the Den's **Harald's Lair** section, enter a place (a city, "city, state", or a zip or postcode) and its country. That's home, as far as the weather is concerned: ask him "What's the temperature at home?", or about the humidity, air pressure, pollen count (Europe only), UV index, air quality, sunrise or sunset there. The country matters because there's more than one London and Toronto in the world. He keeps the Lair only to within about 10 km, and a postcode is cut down to its area before it's looked up, so your full postcode never leaves the Pi (how, exactly, is in [the privacy section](#the-lair-and-your-postcode)). Both need the internet.
- **Local announcements** (in the Lair section). While he's online, he keeps an eye on the weather at home, each kind of news at its own time so they never pile up:
  - **on the hour:** how warm it is, **"It's 14°C (57°F) outside at the Lair."** on the screen, and out loud **"At the Lair, the current temperature is 14 degrees Celsius, that's 57 Fahrenheit."** (the place comes first, so there's time to start listening before the number; no joy for this one, and not during quiet hours);
  - **a quarter past:** when the air pressure there is falling or rising fast, **"There's a storm coming at the Lair!"** or **"The weather is changing at the Lair!"**, with the same joy as when he feels a storm himself through your phone's barometer (Level 3);
  - **half past:** when the pollen count is high, he sneezes: **"Achoo! The grass pollen is high at the Lair."**, or, if it was already high and has gone up since the hour before, **"Achoo! The grass pollen is higher at the Lair! It's very high now."** (Europe only: see [pollen outside Europe](#pollen-outside-europe));
  - **a quarter to:** when the UV index is high, he puts his sunglasses on: **"Sunglasses on! The UV index at the Lair is 7, that's high."** (or **"…is higher! It's 8 now"**);
  - **half past, too:** when the air quality is poor or worse, he sneezes again: **"The air quality at the Lair is poor, with a European air quality index of 65."** (in the US, from "unhealthy for sensitive groups" on the US index);
  - **sunrise and sunset**, as they happen, with a little joy: **"The sun is rising at the Lair!"**
  - **official weather warnings**, checked every 15 minutes (at 5, 20, 35 and 50 past) and announced once each, with his alarmed face: **"AMBER WARNING: WIND AT THE LAIR"**. In the United Kingdom they come from the Met Office, for the Lair's region (worked out from the county; the Den lets you change it if the guess is wrong). In the United States they come from the National Weather Service, for the Lair's forecast zone and county. Other countries aren't covered yet, as each publishes its warnings its own way. Ask him **"Are there any weather warnings at home?"** for the ones in force.

  High pollen and high UV show on his screen every hour they're high. **What he says out loud is up to you**: if he has a voice (the phone, or the Dot at Level 4), the Den's *Voice and light ring* section has **Weather information: Lair**, with a tick box for each kind of news (Temperature, Storm or change, Weather warnings, Poor air quality, High pollen, High UV, Sunrise/sunset). A ticked box is said even in *Big moments* mode. Poor air quality, High pollen and High UV each have a choice of **Increased readings only** (the default: said when the reading goes up, so a long sunny day isn't a reminder every hour) or **All high readings**. There's a matching **Weather information: Phone sensors** for the storms and sunshine his phone's barometer and light sensor notice (Level 3). Untick anything and he still shows it on his screen, just quietly.

  **Testing so far:** setting the Lair, sunset, official warnings (announced once, with the alarmed face) and the Den's Lair section are confirmed. The hourly temperature wasn't heard in testing, because *Big moments* mode skipped it; ticked boxes are now said in that mode too, but this hasn't been re-tested yet. Storms, high pollen, high UV and poor air quality haven't happened yet to test, and sunrise hasn't been watched for.
- **Language (untested): British, American or Canadian English.** Also in the Lair section. Everything written on his screen, in the Den and on its other pages (the map, the shopping list, the calendar, the artwork page, the Garden Collection) follows the English you choose: "metres" or "meters", "colour" or "color", "grey" or "gray", "organise" or "organize", "autumn" or "fall". Canadian English keeps British spellings with "-ize" endings and North American words. The rules come from Bookworm, so Harald and the Butterfly Garden spell alike. **Language matches Lair location automatically** is ticked to start with: a Lair in the US gets American English, Canada Canadian, and the UK or Ireland British. With no Lair, or a Lair elsewhere, it's the Pi's own country (the Wi-Fi country you chose in Raspberry Pi Imager), and British English if that isn't one of these. Untick it to choose for yourself; for example, an American living in the UK can keep American English with a UK Lair. When you move the Lair to the UK, Ireland, the US or Canada, a small question asks whether to change the language and the Butterfly Garden to match: either, both or neither. Not changed: what he says out loud, the names of networks, gadgets and places, your own list items and calendar events, the diary, the README and the code. Numbers stay metric either way (with °F next to °C, as before).
- **Optional: his voice, through an Android phone.** It needs none of the phone's sensors, only the phone on the same Wi-Fi as him: see [His voice through your phone](#his-voice-through-your-phone-partly-tested).

What he can't do yet: anything that needs to know where he is (walks, wardriving, the map). That's Level 3, or Level 2 with a [USB GPS receiver](#optional-a-usb-gps-receiver-untested) or [finding him by Wi-Fi](#no-gps-at-all-finding-him-by-wi-fi-untested).

### What you need

- A **Raspberry Pi Zero 2 W** (the "2" matters: the older Pi Zero W is much slower and untested).
- A **microSD card of 8 GB or more.** Everything installed, including the extras for the higher levels, takes roughly 4 GB. The tested card is 16 GB, which leaves plenty of room. If your computer has no card slot, you'll also need a USB card reader.
- A **micro-USB power supply**, 5 V and at least 2.5 A (an official Raspberry Pi supply is the safe choice).
- Your **home Wi-Fi**: a private network that you control, broadcasting on **2.4 GHz**. The Pi Zero 2 W's radio can't see 5 GHz networks. Most home routers broadcast both, often under the same name, which works fine.
- A **computer** (Windows, macOS or Linux) on the same home network.

### Before installing or updating: pause your VPN

If your computer (or your router) runs a VPN, pause it for the install and for every update. A VPN can send your computer's traffic somewhere else, so it can't find the Pi on your home network, and it can block or slow down the Pi's downloads. Turn it back on when you're done.

### Install, step by step

> **Testing so far:** updating an existing install with `update-bt-dragon.bat` (Windows) is confirmed. A fresh install from a blank card hasn't been re-run since this version's changes, and `update-bt-dragon.sh` (macOS and Linux) hasn't been tested yet.

You don't need any Linux experience. You'll copy files onto the card, plug in the Pi, and type two commands.

**Step 1: Write Raspberry Pi OS to the card.**

1. On your computer, install **Raspberry Pi Imager** from [raspberrypi.com/software](https://www.raspberrypi.com/software/) and open it.
2. **Device:** Raspberry Pi Zero 2 W.
3. **Operating system:** Raspberry Pi OS (other) → **Raspberry Pi OS Lite (64-bit)**. ("Lite" means no desktop, which a pet doesn't need.)
4. **Storage:** your microSD card. Everything on the card will be erased.
5. When it asks about OS customization, choose **Edit settings**:
   - **Hostname:** `bt-dragon` (the rest of this guide assumes this name).
   - **Username and password:** pick your own and write them down. You'll need them to log in to the Pi.
   - **Wireless LAN:** your home Wi-Fi's name and password, and your country.
   - **Locale settings:** your time zone and keyboard layout.
   - **Services** tab: tick **Enable SSH** and **Use password authentication**.
6. Save, then **Write**. It takes a few minutes.

**Step 2: Copy BT Dragon onto the card.**

1. When writing finishes, take the card out of your computer and put it back in. A drive called **bootfs** appears.
2. Download this project (the green **Code** button on GitHub → **Download ZIP**) and extract it.
3. Copy the whole `pi` folder onto **bootfs** and rename the copy to `bt-dragon`. Check: there should now be a file at `bootfs/bt-dragon/install.sh`.
4. Also copy `pi/bt-dragon.toml` to the top level of **bootfs** (next to the `bt-dragon` folder, not inside it). This is his settings file.

**Step 3: Fill in the settings file.**

Open `bt-dragon.toml` on **bootfs** in a plain text editor (Notepad on Windows, TextEdit on macOS). Under `[home_wifi]`, put your home Wi-Fi's name and password between the quotes:

```
ssid = "YourNetworkName"
password = "YourNetworkPassword"
```

On his first start, he replaces the password with a scrambled key, so it isn't left in the file as plain text. Everything else in the file can stay as it is; each setting is explained in the file itself. Save, then eject the card.

**Step 4: First start.**

1. Put the card in the Pi and plug the power supply into the port marked **PWR** (the one nearest the end of the board; the middle one is for data).
2. Wait about 3 minutes. The first start is slow, and there's no screen to watch, so be patient.

**Step 5: Log in and install.**

1. On your computer, open a terminal: on Windows, **PowerShell** (search for it in the Start menu); on macOS, **Terminal**.
2. Type this, using the username you chose in Step 1, and press Enter:
   ```
   ssh yourusername@bt-dragon.local
   ```
   - If it asks whether to continue connecting, type `yes`.
   - Type your password when asked. Nothing appears while you type it; that's normal.
   - If `bt-dragon.local` isn't found, find the Pi's IP address in your router's list of connected devices (usually on a page called "Devices", "Attached devices" or "DHCP clients", reached by typing your router's address into a browser), and use it instead, for example `ssh yourusername@192.168.1.42`.
3. Then type:
   ```
   sudo bash /boot/firmware/bt-dragon/install.sh
   ```
   This downloads and installs everything he needs. Expect 10 to 20 minutes on a Pi Zero (longer on a slow connection). When it's done, the Pi restarts by itself, and about a minute later Harald is awake.

**Step 6: Say hello.** Open the Den (next section).

### The Den: his local HTML page

Open a browser on your computer and go to:

**http://bt-dragon.local:8080**

If that doesn't load, use the Pi's IP address instead (the same one as in Step 5), followed by `:8080`, for example `http://192.168.1.42:8080`. Bookmark it.

Without a screen on the Pi, the Den *is* how you see him: a live copy of his screen sits at the top, with *No e-ink screen: this is his screen* underneath. The Den also gives you far more than any screen could:

- **His meters and today's news:** joy, belly, pack, XP, what he's eaten, recent treats, his life list and his diary (also downloadable as daily spreadsheet files).
- **Gadgets nearby and pals:** tap **It's mine** on your own headphones or speakers, then use **Find my pals** to track them down. **Search for my gadgets** finds classic-Bluetooth gadgets in pairing mode.
- **Tracker alerts**, with a button to dismiss them.
- **Dragon friends** he's met.
- **Care and Accessibility:** rename him, restart him, **Nap** (as good as switched off, but wakeable from the Den), **Put to sleep** (safe to unplug), **Artwork** (see below), the **Sleep screen** tick boxes, and **Color Blindness Mode** (both below).
- **Backup:** download a small file with everything that's his, and restore it later.
- **Developer Tools:** every number that drives him (how fast he gets hungry, how much each snack is worth...), adjustable while he runs.

> **The Den lives on the Pi, not on the internet.** The Den and its pages (the shopping list, the calendar, the map and the artwork page) only open while your computer or phone can reach the Pi over the same network. They aren't an online service or an app on your phone. For example, you can only tick things off the shopping list while you shop if Harald is in your bag, on your phone's hotspot (Level 2). At home with him, you can read it out or write it down before you go.

**The order of the Den.** Below his meters, the Den starts with what a dragon at Levels 1 and 2 (no GPS, no Echo Dot) does most: **Find my pals**, **Dragon friends**, **Gadgets nearby**, **Recent treats**, his **Life list** and **Diary**, then looking after him: **Network**, **Care and Accessibility**, **Backup** and **Developer Tools**. After that come the parts that are still useful without GPS or a Dot (**The moon**, the **Butterfly Garden**, then the **Shopping list and calendar**, **Ask Harald** for typed questions and kitchen timers, **Harald's Lair** for the weather at home, then **Voice and light ring**), and last the ones that need GPS (**Adventures today**, **Conquests**, **WiGLE**). **Voice and light ring** is folded away until you open it. To change the order, press **Arrange the den** at the bottom of the page and move sections up or down; **Back to the usual order** undoes it. The order is remembered by each phone or computer's browser, so your phone and your computer can each have their own.

**Always put him to sleep before unplugging.** Use **Put to sleep** in the Den and wait about 30 seconds (with a screen: until the **SLEEP** screen appears, or *SAFE TO UNPLUG* if you've turned the sleep screen off), then pull the plug. Cutting the power while the Pi is writing to the card can corrupt it.

### Keep him on a private network

> ⚠️ **The Den has no password.** Anyone on the same network who knows (or guesses) his address can open it and:
> - see your pals (your own gadgets) and their Bluetooth addresses, your diary, and (at higher levels) the map of everywhere you've taken him, your walks, your calendar and your shopping list
> - **download a backup, which contains your Wi-Fi passwords and WiGLE token**
> - download your wardriving data
> - rename him, put him to sleep, restart him, or change any of his settings
>
> On a network you control (your own home Wi-Fi, your own phone's hotspot), only your own devices are connected, so that's fine. **Never connect him to public or shared Wi-Fi**: cafés, hotels, libraries, school, work or a neighbor's network. Anyone else on those could reach the Den.
>
> With an e-ink screen, a tiny ⚓ anchor appears at the bottom right of his screen whenever a Den page is open anywhere, so you can tell if someone else is looking.

### Optional: an e-ink screen (Pwnagotchi hardware)

If your Pi is part of an old **Pwnagotchi** with a **Waveshare 2.13" e-ink screen**, Harald uses the screen by himself: no setting to change.

| Screen | Status |
|---|---|
| Waveshare 2.13" e-ink **V4** | ✅ Tested. Not yet: your own artwork on the panel, and the faces that need a particular moment (sleepy, sneezing, sunglasses, dazzled) |
| Waveshare 2.13" e-ink **V3** / **V2** | ❓ Supported but untested. Set `model = "V3"` or `"V2"` under `[display]` |
| Other Pwnagotchi screens (Inky, 2.7", etc.) | ❌ Not supported |
| No screen ("headless") | ❓ Supported but untested. Noticed by Harald himself at start-up |

- The version is printed on the back of the screen's circuit board. Pwnagotchi cases usually mount it upside down, so the picture is turned 180° by default; set `rotate = 0` under `[display]` if yours appears upside down.
- **Your Pwnagotchi card stays untouched** if you install BT Dragon on a spare card: swap cards to switch between the two. If you do install it on a card that still has Pwnagotchi's software, the installer switches Pwnagotchi's services off (without deleting them) so they don't fight over the screen and radio.
- **The screen flashing black and white now and then is normal, not a fault.** E-ink pixels are tiny capsules of black and white particles, moved by an electric charge. For everyday changes Harald uses a quick *partial* refresh that only nudges the pixels that changed, which is fast and calm but slowly leaves faint "ghosts" of earlier pictures behind. So every 20 minutes (and when he starts, naps or goes to sleep) he does a *full* refresh instead: every pixel is driven through black and white a few times to shake the particles back into place, which is the flash you see. It cleans the screen; nothing is wrong. To change how often, set `full_refresh_minutes` under `[display]` in the settings file (less often means more ghosting in between).
- **How he knows there's no screen:** the panel has a "busy" wire that it holds up while it's working, and a full refresh keeps it busy for a second or two. The Pi's pin for that wire is pulled down inside the Pi, so with nothing attached it never reads busy. If his first refresh "finishes" without the panel ever being busy, there's no panel. If the pin reads busy forever instead (a loose connection), every wait gives up after a while (10 s at start-up, 30 s later), so he carries on without the screen instead of freezing. He checks at every start, so a screen added while he's off is used the next time he starts.

### His meters

Harald has separate meters, so he can be **hungry and happy** after a long walk through a quiet park, or **stuffed and bored** after a day at home with the same old devices.

- **JOY** drops slowly when nothing's happening (a full meter lasts about 16 hours). New things, friends and walks raise it.
- **BELLY** (food) empties in about 2½ hours with nothing to eat. Bluetooth snacks and Wi-Fi treats fill it.
- **PACK.** Berries and treats he finds while his belly is already full go into his pack (up to 50). When his belly drops to 25%, he eats half of what's in it, never more than fills his belly back up.
- **Time switched off counts too.** When he starts up with a correct clock, he works out how long he was off and drops his meters as if he'd been awake with nothing to eat or do. **XP never drops.**

| | What it is | Food | Joy | XP |
|---|---|---|---|---|
| **Snack** | A new arrival: a fixed-address gadget he hasn't eaten today, or one more phone/watch/earbud of a kind than were already around. Phones change their address every ~15 minutes, so he counts heads, not addresses: the phone on your couch is one snack, not four an hour | +2 | +0.3 | +1 |
| **Feast** | A kind of device he has never eaten before (it goes in his life list) | +12 | +8 | +20 |
| **Treat** | A Wi-Fi network he has never seen before. WPA2 +4, WPA3 and office networks +5, open and WEP +6 | +4 to +6 | +2 | +5 to +15 |
| **Berries** | A network he already knows. Like a berry bush, it regrows 1 point per day since he last picked it, up to its full treat value | up to +6 | small | small |
| **Friends** | Meeting a new dragon, a returning friend, spotting one of your own gadgets | | +15 / +8 / +3 | +50 / +10 / 0 |
| *Level 3:* **Adventure** | Walking or running with him switched on | | +3 per 100 m | +2 per 100 m |
| | Cycling with him | | +1.5 per 100 m | +1 per 100 m |
| | Riding in a car or bus with him | | +1 per km | +1 per km |
| | Finishing a walk of 200 m or more ("You took Harald on an adventure!") | | +8 | +5 |
| *Level 3:* **Story** | Steps your phone counted while he wasn't with you ("You told Harald about your adventure!") | | +1 per 100 m (max 30) | +1 per 100 m |
| *Level 3:* **New land** | A square of the map about 250 m across that he's never been to. A whole new realm (about 1 km across) is a big one. A quarter as much while riding in a vehicle | +3 / realm +3 | +4 / realm +10 | +10 / realm +15 |
| *Level 3:* **Stars** | A navigation satellite he's never seen. His first of a new constellation is a big one | +3 / +6 | +2 / +12 | +5 / +25 |
| | A known satellite rising again | | +1 each | |
| *Level 3:* **Weather** | A storm coming (pressure falling 3 hPa in 3 hours): the first of the day, or a later one | | +15 / +4 | +5 |
| | Pressure rising fast: "Looks like a weather change soon!" | | +3 | +5 |
| *Level 3:* **Landmarks** | Coming within about 250 m of a famous place: the first time ever, or again (once per place per day) | | +6 / +2 | +10 / 0 |
| *Level 3:* **Green spaces** | A park or wood he's never been in; a walk, run or ride in one (once per place per day) | | +5 / +6 | +8 / +5 |
| **Moon** | The day of a full moon, or of a new or quarter moon (worked out on the Pi, no internet needed) | | +12 / +4 | +5 |
| *Level 3:* **Climbing** | Stairs and hills while you're out walking, running or cycling, measured by your phone's barometer | | +2 per 10 m | +1 per 10 m |
| *Level 3:* **Sunshine** | "Wow! It's sunny out today!": your phone's light sensor reads 30,000 lux or more for 30 seconds (at most once every 3 hours) | | +3 | |
| **Butterfly Garden** | From level 5: an egg hatching or a larva pupating; an adult emerging (fed by food that fits in neither his belly nor his pack) | | +3 / +10 | +10 for an adult |

Every one of these numbers can be changed while he runs, from **Developer Tools** in the Den. Living somewhere rural with few devices around? Make his belly last longer or make each catch more filling.

**Levels:** level = 1 + √(XP ÷ 50), so level 2 at 50 XP, 3 at 200, 5 at 800 and 10 at 4,050.

**His face:** joy picks the eyes (happy, content, bored, sad), and his belly can change the mouth (drooling when hungry, a contented wobble when stuffed). Short reactions, like a feast, an adventure or riding with the wind in his face, take over for a moment. A small joy boost gets his **excited** face; a big one (8 joy or more, adjustable) gets his **ecstatic** face, with big starry eyes and sparkles. High pollen or poor air at home makes him **sneeze**, sunshine gets his **sunglasses** on (round ones, so they're never mistaken for a Pwnagotchi's square ones), and a high UV index gets the sunglasses with a startled "oh!" (**dazzled**). His **sleepy** face shows between 1 and 6 in the morning when his joy is under 70.

![Harald's moods](docs/moods.png)

### Dragon friends

Like Pwnagotchis, dragons make friends. Each BT Dragon sends a small Bluetooth beacon carrying a random dragon ID, its name, level and mood. When another dragon comes near, the two meet: a first meeting is a big XP bonus and the newcomer joins his friends list; coming back after half an hour or more is a happy reunion. He also recognizes a real **Pwnagotchi** nearby (they all beacon from Wi-Fi address `DE:AD:BE:EF:DE:AD`) and gets excited about his distant cousin.

**Two dragons on one network:** give the second one a different hostname in Raspberry Pi Imager (say `bt-dragon2`), and if you use an Echo Dot (Level 4), set `enabled = false` under `[dot]` in the second one's settings, or both will try to use it. They'll meet each other as friends.

### The Butterfly Garden (from level 5, untested)

Once Harald reaches **level 5**, a **Butterfly Garden** opens in the Den. It comes from **Bookworm**, the project author's own (unfinished) reading tracker project, where each book you read raises an insect. Here, instead of pages, the larvae grow on Harald's **spare food**.

- **Spare food:** treats and berries go into his BELLY first, then his PACK. Anything that fits in neither used to go to waste; now it goes to the garden, shared evenly between the larvae growing there. So the garden only grows while his belly **and** his pack are both full: the Den's garden section shows both, and how much spare food the garden has had today. His screen says so too, at most every 30 seconds (*FED 2.5 FOOD TO THE BUTTERFLY GARDEN*). Snacks and feasts fill his belly but are never spare, so they don't feed the garden. So a well-fed dragon on a busy walk feeds the garden, and three larvae at once each grow at a third of the speed of one.
- **Spots:** one at first, and one more for each level he gains after the garden opens, up to three. The first spot always holds an **egg** (a new one as soon as its adult emerges). Any other spot stays **empty** until you press **Put an egg here** in the Den, both when it first opens and after its adult emerges, so you can raise just one or two at a time if you'd rather (spare food is only shared between spots with an egg or a larva in them). An egg that hasn't hatched can be taken away again (**Leave this spot empty**). The first food that reaches an egg hatches it, and only then is its species chosen.
- **Which species:** Bookworm's own rules. Its rarity is rolled (**Common** 60%, **Uncommon** 30%, **Rare** 10%), and a rarer one needs more food to raise (40, 80 or 120 food). Then it's one you haven't raised yet, with species that are in season this month three times as likely. Every egg starts out as a butterfly; raising butterflies unlocks the other categories one at a time (moths after 2, then bees and wasps, beetles, flies, ants and other insects), as in Bookworm.
- **Growing:** the progress bar is Bookworm's. Each species pupates (a chrysalis, for butterflies) at its own point, worked out from how many days it really spends as a larva and as a pupa, and the adult emerges at 100%. Each one is drawn with Bookworm's own art, crawling as it grows, then its pupa gently swaying (Bookworm's hand-drawn artwork where it has some, its placeholder drawings for the rest), and an empty spot shows its egg. Larvae go **hungry** with Harald: when his belly is under 30% no spare food is reaching them, and a thought bubble with a leaf appears (with a "!" under 10%). Hatching and pupating give him a little joy; an adult emerging is a big joy (his ecstatic face), +10 XP and a line in his diary. **Tap a larva** in the Den to open its field notes, with its picture at the top.
- **Queens and workers:** a female of a social species (bumblebees, wasps, ants) becomes a **queen** if his belly never runs low (under 30%) while she's growing, and a **worker** if it does, as in Bookworm.
- **The Collection:** **See Collection** opens the Garden Collection: Bookworm's own collection page, in the Den's colors, with every species, its card, artwork, facts, **I've Seen It!** sightings and the search. Raising one adds it there, may unlock a **habitat** (**See Habitats** at the bottom of the collection; **Go back to Collection** at the top of the habitats), and earns points towards a **title**: 100 for Common, 200 for Uncommon and 300 for Rare. The points needed are Bookworm's, but the titles are Harald's own: Egg Explorer, Bluetooth Beetle (500), Wi-Fi Wasp (1,500), Berry-picking Bumblebee, Snack-seeking Sawfly, Treat-hunting Hoverfly, Beacon Butterfly, Signal-sniffing Hawk-moth, Land-claiming Leafcutter, Satellite Stag Beetle, Hotspot Hornet, Runestone Rhinoceros Beetle and, at 75,000, Monarch of the Lair. Bookworm's achievements aren't included yet; they'll come later, as a Den section of their own for Harald's milestones.
- **Country:** Bookworm's countries are the United Kingdom, Ireland, the United States and Canada. To start with, the garden uses the Pi's own country (the Wi-Fi country you chose in Raspberry Pi Imager) if it's one of those, and the United Kingdom if not. Change it with the menu in the garden at any time. When you move the Lair to one of those countries, the Den asks whether to move the garden there too (and the language, below). Each country has its own collection; the score counts them all.
- **No spiders.** Spiders aren't included at the moment. If they're ever added, there will be an "arachnophobia" tick box in the garden to keep them from hatching.

To try it before level 5, tick **Unlock now (prototype testing)** in the garden (the box disappears once he's level 5). Unticking it locks the garden again (anything raised is kept). The food each rarity needs and the joy each step brings are in **Developer Tools**.

### Looking after him

**Updating.** Pause your VPN first. Download the new version and extract it, then run the updater from the extracted folder:

- **Windows:** double-click **`update-bt-dragon.bat`**.
- **macOS / Linux:** open Terminal in the folder and run `bash update-bt-dragon.sh`.

It asks for your **login name** on the Pi (the username you chose in Raspberry Pi Imager) and the Pi's **address** (`bt-dragon.local`, or its IP address), and remembers both for next time. Type the Pi's password when asked (up to twice). The updater swaps in the new code and restarts him in a few seconds. His memory and settings are kept, and your settings file is never overwritten.

<details><summary>Updating by hand</summary>

From the extracted folder (the one containing `pi`):

```
scp -r pi yourusername@bt-dragon.local:bt-dragon-new
ssh yourusername@bt-dragon.local
sudo bash ~/bt-dragon-new/update.sh
rm -rf ~/bt-dragon-new
```
</details>

**Backups.** A full image of the card works, but it's the size of the whole card. A **mini backup** is just what's his, usually a few megabytes at most: in the Den, under **Backup**, press **Download backup**. You get `harald-backup-<date>.tar.gz` with his database (Harald himself, his diary, species, pals, and everything from the higher levels: lands, walks, voice profiles, calendar, shopping list, your Den settings and Developer Tools numbers), his diary and wardriving files, your artwork, the settings file and the Pi's key for the Echo Dot. Not included: Raspberry Pi OS, the program and the downloadable extras; installing and updating put those back. **The backup holds your Wi-Fi passwords and WiGLE token: keep it private.**

He makes it while he runs. His database keeps its newest changes in a side file until they're merged in, so copying the database file alone could catch it half written. Instead, SQLite's own backup feature copies it page by page into a clean, complete snapshot, straight into memory.

To restore, use **Restore from a backup…** in the Den and pick the file. It's checked first (it must be one of his backups, with only the expected files in it, and a database that passes SQLite's own check), then he restarts and puts it in place. On a freshly set-up card, you can instead copy the backup onto **bootfs** named `harald-restore.tar.gz`; he restores it the next time he starts, then renames it so it only happens once. Either way, what was there before is kept on the Pi in `/var/lib/bt-dragon/before-restore/`.

**Customizing your dragon's artwork.** The Harald in this repository for purposes of testing the prototype is an AI-generated placeholder, drawn by code from simple shapes. To use your own art or art you have permission to use, open **Artwork** in the Den's *Care and Accessibility* section. Each mood is shown as it will look on the screen, with buttons to **Upload** a picture, download a **Template** (the placeholder at actual size, to draw over) or **Remove** yours again.

- **96 × 86 pixels, black and white, PNG.** The screen is two-colour, so each pixel ends up ink or paper: transparent counts as paper, and grey becomes black if darker than half way, white if lighter. The page shows the result and points out grey pixels and wrong sizes. (JPEG blurs every edge into grey: use PNG.)
- **One picture per mood**, named after it: `content`, `happy`, `bored`, `lonely`, `sleepy`, `asleep`, `eating`, `treat`, `stuffed`, `hungry`, `starving`, `excited`, `ecstatic`, `proud`, `alarmed`, `uploading`, `adventure`, `riding`, `sneezing`, `sunglasses`, `dazzled` (`happy.png` and so on). Optionally a second frame (`happy_1.png`), which he alternates with the first on screen updates, and, for the five everyday moods, versions for an empty or full belly (`happy-hungry.png`, `happy-stuffed.png`). Anything the placeholder adds on top (Zzz, sparkles, sweat drops, speed lines) belongs in your picture.
- **Moods without a picture keep the placeholder**, so you can replace them one at a time. Pictures are kept in a `harald-art` folder on **bootfs**, so you can also copy them there from your computer.

From pencil to pixels, if you prefer traditional art methods (like the project author does): sketch the drawing in pencil, carefully go over the drawing in black pen and then erase as much of the pencil as you can (pencil turns patchy when forced to black and white), photograph or scan it to make it digital, then in GIMP, Paint.NET or Photopea raise the contrast, scale it down to 96 × 86 with no smoothing, and switch to a 1-bit black and white palette without dithering. At this size the best final results usually come from the addition of pixel art tracing: use the faded photo on a layer underneath and draw your pixels on top using your computer mouse with a 1-pixel pencil (LibreSprite is specifically made for this if you want to give it a try!). Look up online tutorials for additional guidance.

**Sleep screens (untested).** E-ink keeps its last picture even with the power off, so a dragon asleep in your bag would otherwise go on showing whatever was on his screen: his diary line, a network's name, a reminder. Like an e-reader's sleep screen, BT Dragon can show a plain picture instead: his sleeping face, alone in a white circle on black, with **NAP** or **SLEEP** in the bottom right corner. Two tick boxes under **Care and Accessibility** in the Den, **Nap** and **Sleep**, choose when it's used (both are on to start with; untick either or both for his usual screen with *NAPPING. WAKE ME IN MY DEN* or *ZZZ... SAFE TO UNPLUG*). A restart still shows the usual screen, since he's straight back. The two pictures are placeholders too: replace them on the **Artwork** page with your own, **250 × 122** pixels (the whole screen), named `nap-screen.png` and `sleep-screen.png`. Transparent counts as white, as with the moods.

![The nap and sleep screens](docs/sleep-screens.png)

**Color Blindness Mode (untested).** At the bottom of **Care and Accessibility** in the Den, a menu sets the colours of the Den and all its pages (the map, the shopping list, the calendar, the artwork page and the Garden Collection) for each kind of colour blindness. The Den's colours have three meanings: **gold** for headings and buttons, **red** for danger (alerts, *Put to sleep*, *Forget...*) and **green** for good things (meters, progress, raised insects).

Your eyes have three kinds of cone cell, most sensitive to red, green and blue light; in each kind of colour blindness one of them is missing or shifted:

| Option | Which cones | What runs together | How common (with its milder form) | The Den's colours |
|---|---|---|---|---|
| **Full color vision** | all three | | | gold, red, green |
| **Protanopia** | red | red, orange, yellow and green; reds look dark | about 1 in 50 men | gold, **pink**, **blue** |
| **Deuteranopia** | green | red and green (the most common kind) | about 1 in 16 men | gold, **pink**, **blue** |
| **Tritanopia** | blue | blue and green, yellow and pink | about 1 in 10,000 people | **lavender**, red, **teal** |

Each option suits the milder form too (protanomaly, deuteranomaly, tritanomaly: the cones are there but shifted). Protanopia and deuteranopia lose the same difference (red against green) and keep the other one (blue against yellow), so one set of colours serves both. Each kind is still listed by name, so you can choose your own and learn what it means. With any of them on, buttons that do something drastic also show a ⚠, so they never depend on colour alone (alerts always have one). Each set was chosen by simulating that kind of colour blindness on the actual pages and checking that the three meanings stay clearly apart and that every colour is readable on the dark background; the tests repeat both checks. The e-ink screen is black and white, so it's the same for everyone.

The same checks found the old red too dark to read comfortably on the dark background (a contrast of 3.5:1, where 4.5:1 is the accessibility guideline), so it's a little brighter for everyone now, and tick boxes and menus are drawn in the Den's dark style whether your browser is set to light or dark mode.

---

## Level 2: Out and about

Take him with you: a **USB power bank** for power, and **your smartphone's hotspot** as his network. Any smartphone with a hotspot works (Android or iPhone).

**What you gain:** he eats wherever you go. A walk through town is a feast compared with the same devices at home: new types of gadget, new Wi-Fi treats, and other dragons to meet. With the Den open on your phone, you can see what he's eating as it happens, find your own gadgets, and put him to sleep before you unplug him.

### What you need

- A **USB power bank** and a micro-USB cable to the Pi's **PWR** port.
- **Your own phone's hotspot**, set to 2.4 GHz:
  - **iPhone:** Settings → Personal Hotspot → turn on **Maximize Compatibility**.
  - **Android:** Hotspot settings → **AP band** → 2.4 GHz (the wording varies by phone). A Pixel has no 2.4 GHz-only choice: **2.4 and 5 GHz** works (tested), as he simply uses the 2.4 GHz half.

### Adding your hotspot 

**(THE BACKUP WI-FI FEATURE DIDN'T WORK IN TESTING. A FIX IS IN THIS VERSION BUT HASN'T BEEN CONFIRMED YET. Until it is, put your hotspot as his home Wi-Fi if you want to take him on walks. That has been tested and works.)** If a backup network won't join, the Den's **Network** section now shows whether each of his networks is in range, its security, and the reason the last attempt failed.

He can know several networks and joins the best one in range. Put your home Wi-Fi under `[home_wifi]` and your hotspot as a backup, below it in `bt-dragon.toml`:

```
[[backup_wifi]]
ssid = "YourHotspotName"
password = "YourHotspotPassword"
```

(Or the other way round, if he spends more time out than at home.) Add one block per network; the first listed is preferred, and so on. To edit the file later, either take the card out and edit it on your computer, or edit it over SSH with `sudo nano /boot/firmware/bt-dragon.toml`, then restart him from the Den.

- **When he starts up, or loses his network,** he joins the highest-priority network that's in range.
- **When he's on a backup and a better one comes back in range,** he moves back by himself. Come home and he's back on your home Wi-Fi within about a minute. Set `return_to_better = false` under `[network]` if you'd rather he stayed put.
- **The Den's Network section** shows which network he's on, with a **Disconnect and find the best network** button.
- If someone else sometimes takes him out, add their hotspot as another backup.

Your own networks are never eaten as treats.

### The Den on your phone

Your phone runs the network, so it's already connected. Open its browser and go to `http://bt-dragon.local:8080`. iPhones usually manage that name; many Android phones can't, and need his IP address instead, followed by `:8080`.

- **With an e-ink screen,** he shows the Den's address on his screen every few minutes.
- **Without one,** look up his address in the Den's **Network** section while you're at home, then try it on the hotspot: phones usually give the same device the same address each time. Some Android phones don't show connected devices' addresses at all; a network scanner app can find him (look for `bt-dragon`).

Add the Den to your phone's home screen for quick access. It only works while he's with you on the hotspot: the home-screen icon is a bookmark to his page, not an app.

### Power

- **Put him to sleep before unplugging** (Den → *Care and Accessibility* → **Put to sleep**), so the card isn't being written to when the power goes.
- **Nap** is the gentler option: as good as switched off (no Bluetooth or Wi-Fi feeding, meters frozen until he wakes (then they drop by however long he napped, just as after sleeping), nothing written to the card), but he stays on the network so you can wake him from the Den. He's safe to unplug mid-nap, and keeps napping through a restart until you wake him.

### Optional: a USB GPS receiver (untested)

A small USB GPS receiver gives him most of [Level 3](#level-3-your-phones-senses) without any phone apps: a "G-mouse" receiver with a u-blox chip (the VK-162 and VK-172 are common), plugged into the Pi's **data** port (the middle micro-USB, marked USB) with a micro-USB OTG adapter. He finds it by himself. It needs to be outdoors. Receivers like these can generally hear the satellites through a bag or backpack, so it can travel tucked away with him, but your experience may vary depending on the make and model you try. Indoors they struggle, and the first fix after switching on can take a minute or two.

- **What it brings:** walks (tracked and logged), conquering the map, landmarks, green spaces (walks, runs and rides in them included), wardriving, stars and the better tracker warning, all as described in Level 3.
- **What still needs the phone:** stories (its step counter), weather and climbing (its barometer) and sunshine (its light sensor).
- **With both** it and the phone sending positions, `prefer` under `[gps]` in the settings file decides which wins, and the other fills in while the preferred one has no fix.

### No GPS at all: finding him by Wi-Fi (untested)

Level 3 brings **conquering the map**: the world is cut into squares about 250 m across ("lands"), grouped into squares about 1 km across ("realms"), and he claims each one you take him into. Normally that uses a GPS: your phone's, or [a USB receiver](#optional-a-usb-gps-receiver-untested). If you can't, or would rather not, give him one, he can still claim land from Level 2, by working out roughly where he is from the Wi-Fi networks around him. It's off unless you switch it on in the Den: **Conquests → Find him by Wi-Fi**.

**How it works.** Every Wi-Fi router announces itself about ten times a second with a unique hardware address, and he already hears those announcements. Routers almost never move, so a service that knows roughly where millions of them are can turn "I can hear these networks, this loudly" into "then you're about here". It takes the known positions of the routers he hears and averages them, counting the louder ones for more, because a loud router is usually a near one. In a town that's usually within 20 to 50 m. In the countryside, with only one or two networks about, it often can't tell at all. The service is [beaconDB](https://beacondb.net), free and community-built. He only *asks* it: he never sends it sightings of his own.

> ⚠️ **This is less private.** The list of networks around you *is* where you are, so every lookup tells beaconDB where he is, to within tens of meters. Its [privacy notice](https://beacondb.net/privacy) says it doesn't keep the networks asked about or the answer, but its server logs keep your internet address and the time for 28 days. To keep this to a minimum, he only asks while there's **no GPS at all** (a phone or USB GPS always wins), only while he's on your hotspot, at most once every two minutes, and not again while the same networks are still around. Your own hotspots, phones' hotspots (they move around with their owners) and networks ending in `_nomap` are never sent.

**What a Wi-Fi position does:** claims lands and realms (only the square he's in, since it's too rough to tell you're passing a square's edge), points out landmarks and discovers green spaces (both described in [Level 3](#level-3-your-phones-senses)), answers "where is...?" questions, and shows where he is on the Den's map, with a circle for how rough it is.

**What it doesn't:**

- **No walks, runs or rides in green spaces, and no walk distances.** A Wi-Fi position wanders by tens of meters even while you sit still, so he'd count walks you never took.
- **No WiGLE uploads.** A position worked out from beaconDB is an estimate built from other people's reports, not a sighting, so passing it to WiGLE would muddy the map everyone shares. Networks he hears still feed him, as always.

How precise a Wi-Fi position must be to claim land is **Lands: ignore Wi-Fi positions less precise than** in **Developer Tools → Detection** (75 m).

---

## Level 3: Your phone's senses

Your phone has a GPS, a step counter, a barometer and a light sensor. Shared with Harald over the hotspot, they let him know where he is, how you're moving, how high you've climbed and when the sun is out.

> ⚠️ **Tested with Android only:** a **Google Pixel 7 Pro** running **Android 17**, with the apps below, all from **F-Droid** (an app store for free, open-source Android apps). Other Android phones with the same sensors should work. iPhone options are listed further down, untested.
>
> **Google's developer verification may affect this.** Google has announced that, during 2027, apps on certified Android phones will have to come from developers who have registered their identity with Google, including apps installed from outside the Play Store. Some F-Droid developers have said they won't register (SherpaTTS, used below, already shows a notice saying so). Google has described a one-time "advanced" setting for installing apps from unverified developers, and installing over `adb` from a computer isn't affected, but details may change. Apps you've already installed may or may not keep working. Check the current situation before relying on this level.

### What he gains

- **Walks.** He knows when you're walking, running, cycling or riding, and how far. Each outing goes in his diary when it ends: **"Walk: 4.57 km (2.84 mi) in 1 h 24 min, from 15:20"**. The Den shows the walk in progress and today's walks under *Adventures today*. Walks are also kept for good in his database.
- **Stories.** Steps your phone counted while he wasn't with you become a story you tell him when you're back.
- **Conquests: new land.** The map is cut into squares about 250 m across ("lands"), grouped into squares about 1 km across ("realms"). He claims the square he's in, and any neighboring square whose edge you pass within about 40 m of. The squares are deliberately big, so nearly every one has a public road or path in it: **you never need to go onto private property to claim land.** The Den's **Conquests** section counts them, and **Open the map** shows them with a fog of war over everywhere you haven't been yet. **Forget my map** in the Den erases the lot. (No GPS? He can still claim land by [finding himself by Wi-Fi](#no-gps-at-all-finding-him-by-wi-fi-untested), back in Level 2.)
- **Landmarks.** The first time he enters a realm, he asks Wikipedia which famous places are in and around it. "Famous" means Wikipedia has an article about it in at least 10 languages: the Tower of London passes easily, the pub on the corner doesn't. When you come within about 250 m of one, he points it out: **"LOOK! TOWER BRIDGE!"** The map marks them.
  **In the countryside, lower the bar.** 10 languages suits a city, but a rural area may have few places that famous, or none. The number is **Landmarks: how famous** in **Developer Tools → Detection**, and lowering it is highly recommended for rural areas. If you don't see any landmarks on the map within a reasonable distance, lower it by 1 and look at the map again, and repeat until your area feels as full of landmarks as you'd like. The change shows straight away, since he keeps every place Wikipedia told him about along with how many languages it's written about in.
- **Green spaces.** Public parks, woods, nature reserves, commons, village greens and gardens, from OpenStreetMap (the same map the Den draws, so the outlines match its green areas). Going into one for the first time finds it: **"A NEW GREEN SPACE: FERNHILL VALE!"** Ten minutes on foot in one (with at least 150 m of actual walking) earns **"Took a walk in Oakfield Country Park!"**; five minutes running or cycling, **"Went for a run in..."** or **"Biked through..."**. Time in a vehicle never counts. "Inside" means within the outline or 20 m of it: from your position, picture a line heading due east and count how many times it crosses the outline; an odd number means inside. The Den's **Conquests** section lists them under **Green spaces**: the ones he's discovered, with how many visits, walks, runs and rides each, and the ones nearby he hasn't been in yet.
- **Wardriving.** Every network he hears is logged with a location and uploaded to [WiGLE](https://wigle.net) under **your own account**, if you add your WiGLE **API Name** and **API Token** under `[wigle]` in the settings file (wigle.net → Account → "Show my token"; these are not your login password). WiGLE limits uploads per day, so he batches them: at most every 4 hours, once at least 50 sightings are waiting. Networks whose name ends in `_nomap`, and hidden networks, are never uploaded. The Den has **Upload now** and **Download CSV**.
- **Weather and climbing.** Air pressure drops about 0.12 hPa for every meter you go up. A quick change over a minute or two is you climbing stairs or a hill; a slow change over hours is the weather. **Climbing only counts while you're on the move:** walking, running or cycling by the GPS, or at least 40 steps in the last 2 minutes by the phone's step counter. Sitting at home, the pressure can still jump by a metre's worth (a door or window, a draught, the weather, the phone being picked up), and that used to count; now it doesn't. A fall of about 3 hPa in 3 hours usually means wind and rain on the way. He only judges the weather while you've stayed in roughly the same place, so a hill can't fool him.
- **Sunshine.** When your phone's light sensor reads 30,000 lux or more for 30 seconds (indoors is 100 to 500), he puts on his round sunglasses and cheers: **"Wow! It's sunny out today!"**
- **Stars.** Your phone's GPS chip hears navigation satellites from GPS (USA), Galileo (EU), GLONASS (Russia), BeiDou (China), QZSS (Japan), NavIC (India) and others. Each one is a star he collects in the Den's **Star chart**, and his first of a new constellation is a big one. After that, a star cheers him up again whenever it *rises*: heard low over the horizon after an hour or more out of earshot (**"A STAR RISES! GALILEO 19"**). Satellites you simply lose indoors don't count when you step back outside, because they come back at whatever height they happen to be. This needs **GPSd Forwarder** (set up below) or a [USB GPS receiver](#optional-a-usb-gps-receiver-untested): SensorServer doesn't pass satellite details on.
- **A better tracker warning.** With GPS, an unknown tracker only raises the alarm once it has stayed with you while you've moved 250 m.

Every distance, time and reward here is adjustable in **Developer Tools**. Each feature can be switched off under `[sky]` in the settings file (`lands`, `landmarks`, `greens`, `stars`, `barometer`, `moon`).

### Setting up SensorServer (partly tested)

**Testing so far:** GPS, staying connected with the phone's screen off, reconnecting after the hotspot drops, and stories (steps while apart) are confirmed. Climbing registers but hasn't been checked against a known height; weather changes are confirmed but a storm hasn't happened yet. Walks were confirmed on an earlier build and are being re-checked. Walking without a GPS fix (counted from steps) and sunshine haven't been tested yet.

One free app supplies GPS, steps, the barometer and the light sensor: **SensorServer**, on F-Droid.

1. Install SensorServer and open it.
2. In its settings, turn on **Listen on 0.0.0.0** (so it listens on every network, including your phone's own hotspot). Leave the separate **HotSpot** option off; on some phones it listens on the wrong address. Allow **Precise location** and **Physical activity** when Android asks.
3. Press **Start**. The app says "No connections" until your dragon connects. He dials in by himself within about 15 seconds.
4. Keep it running in the background: set its location permission to **Allow all the time**, and its battery usage to **Unrestricted** (long-press the app icon → App info → Battery).

On his screen (or the Den's copy of it), `GPS WAIT` means data is arriving but there's no satellite fix yet, and `GPS FIX` means it's working.

### Setting up GPSd Forwarder, for stars (tested)

**Testing so far:** collecting stars and rising stars are confirmed. The bigger joy for a new constellation hasn't come up yet: each constellation counts only once, ever.

**GPSd Forwarder** (free, on F-Droid) sends your phone's GPS readings to Harald in the standard format GPS receivers use, satellite reports included, which is what lets him collect stars. It runs alongside SensorServer: keep both.

1. Find Harald's address: the Den's **Network** section shows it while you're connected (for example `10.42.0.17`). Phones usually give him the same address each time on the same hotspot.
2. Install GPSd Forwarder and open it.
3. Enter Harald's address as the host and **`29998`** as the port.
4. Tap **Start**, and allow location access when Android asks (**Allow all the time**, so it keeps working with the screen off).
5. Set its battery usage to **Unrestricted** (long-press the app icon → App info → Battery).

Within a minute of a GPS fix outdoors, the Den's **Star chart** under *Conquests* starts filling up. If his address ever changes, enter the new one.

### Other ways to share a position (untested)

- **iPhone, GPS only: GPS2IP** (App Store). Turn on Socket Mode (TCP) on port `11123`. iOS limits what apps can do in the background, so it may stop when the screen locks. There's no step counting on iPhone yet.
- **A USB GPS receiver** needs no phone app at all: see [Level 2](#optional-a-usb-gps-receiver-untested).

### His voice through your phone (partly tested)

**Testing so far:** speaking through Termux, SherpaTTS with his Piper voice, the phone in a pocket with the screen off, and *Big moments* mode are confirmed. Quiet hours worked on an earlier build. Bluetooth earphones, the phone as a backup for the Dot, *Welcome-home recap only* mode and using it at Level 1 (the phone on the same Wi-Fi rather than its own hotspot) haven't been tested yet.

Harald can talk through your phone's speaker (or Bluetooth earphones), with the screen off and the phone in your pocket. This works at **any level**, even Level 1: none of the phone's sensors are used, it only needs to be on the same network as him (your home Wi-Fi, or its own hotspot). Tested on the Pixel 7 Pro with **Termux** and **Termux:API** (both from F-Droid; the Play Store versions don't work together), and with **SherpaTTS** (F-Droid) to give the phone his own Piper voice.

1. In Termux: `pkg install -y python termux-api`
2. Then the line shown in the Den under *Voice and light ring → Set up the phone voice* (it has your dragon's address filled in). He says hello through the phone when it's working.
3. Android settings → Apps → Termux → Battery: **Unrestricted**.
4. In the Den, tick **Use the phone**.
5. Optional: install SherpaTTS, choose his voice in it (his tested voice is `en_GB-northern_english_male-medium`), and make it the preferred engine in Android's *Text-to-speech output* settings. Without it, he speaks in your phone's usual voice.

Next time, open Termux and type `python harald_voice.py`. How it works: a web page can't keep talking with the screen off (Android pauses it), so a small program in Termux keeps one question open to Harald ("anything to say?"). He answers the moment he has something to say, and the phone's text-to-speech reads it out. Only the words go to the phone, and nothing is kept. Without an Echo Dot, what he says follows the Den's *How chatty* setting; with one, see Level 4 for using both.

---

## Level 4: A voice and ears (Echo Dot)

> ⚠️ **EXPERIMENTAL PHASE, and only for an Echo Dot which is already unlocked and rooted.** Tested on one unlocked and rooted **Echo Dot 2nd generation** ("biscuit", Fire OS) running Fire OS 6 on the phone hotspot of a Google Pixel 7 Pro (Android 17). Most of what's below was confirmed on an earlier build of this prototype and is being re-checked on this one; the welcome-home recap, "how far have we gone?", the color balance settings and telling two voice profiles apart haven't been tested yet. How to root a Dot is outside the scope of this project, and rooting may be impossible on some units. **Do not ask the project author for help with rooting your Dot.** The project author used a UK Echo Dot, specifically the 2nd gen Echo Dot (biscuit) released in 2016 (RS03QR) and [this guide on XDA](https://xdaforums.com/t/unlock-root-twrp-unbrick-amazon-echo-dot-2nd-gen-2016-biscuit.4761416/)

With a rooted Echo Dot that he controls on the same network, Harald speaks, listens and shows his moods on the Dot's light ring. The Dot can stay at home or travel with you using a suitable power bank and data/power cable (use the one the Dot came with, if possible). You can see a brief video of Harald connecting to his Dot and responding to wake word questions and commands [at this YouTube link](https://youtu.be/Rvm9zZaws60?is=vN3Kk3ljDANmPETG)

### What he gains

- **He speaks his news** ("Treat! Coffee shop guest!", "A storm is coming!") through the Dot, in an offline voice ([Piper](https://github.com/rhasspy/piper)). In the Den you choose how chatty he is: *Everything*, *Big moments*, *Welcome-home recap only*, *No announcements* (he still answers your questions out loud, and the Dot's ring still shows his moods) or *Adventure mode*.
- **Adventure mode**, for taking the Dot out on a power bank: only adventure news, at its own quieter volume. How far you've walked today, how high you've climbed, new lands and realms, landmarks, green spaces, sunshine, stars, level-ups, and "Smashing! My pack is full up!". Never anything about Bluetooth or Wi-Fi.
- **Welcome-home recap.** When you take Harald out and the Dot stays home, he tells you what he did once he's back in range.
- **Mood ring.** The ring glows in his mood's color and plays a short animation when something happens: lightning for a storm, twinkles for a satellite, a gold sweep for a level-up, the moon's phase on moon days.
- **Quiet hours** (22:00 to 08:00 by default): no talking, and the ring glows a dim night blue.
- **The phone too.** In the Den, **Use the Dot** and **Use the phone** (Level 3) can be ticked in any combination. **Phone as a backup** makes him talk through the phone while the Dot is out of reach.

**Asking him questions.** Press the Dot's action button (the one with the dot), or say **"Hey dragon"** (see below), and ask. The ring turns cyan while he listens. He understands:

- **the time**, here or in a big city, country or US state ("What time is it in Tokyo?"), and **the date** or **the day**;
- **the weather** now, later today, tomorrow or on a named day, in °C with °F alongside, here, in a big city, or at home ("What's the temperature at home?", using [Harald's Lair](#what-he-does-at-this-level));
- **more about the weather**, here or at home: the humidity, the air pressure, the pollen count (Europe only, in season), the UV index, the air quality, and sunrise or sunset ("When is sunset tomorrow?");
- **weather warnings** at home (UK and US): "Are there any weather warnings at home?";
- **kitchen timers**: "Set a pasta timer for twelve minutes", "How long left?", "Cancel the timer". Say "stop" while one rings;
- **the shopping list**: "Add eggs and milk to the shopping list", "Take bread off the list", "What's on the shopping list?" It has its own page in the Den, sorted into supermarket sections, with how many to buy and which shop;
- **the calendar**: "What events do I have today?" Events and reminders live on the Den's calendar page. A reminder shows only "REMINDER: EVENT IN 1 HOUR!" on his screen (anyone can see the screen), while the Dot says the event's name;
- **voice profiles**: "Set a voice profile" teaches him the speaker's voice. After that, he recognizes you and sometimes uses your name: "It's 7:30 at night, Sam." Asking "Who am I?" checks his guess of who is asking the question. What's kept is a voice print (128 numbers describing how a voice sounds), never a recording;
- *with a position (Level 3, or Level 2 with a USB GPS or Wi-Fi):* **which way is it**: "What direction is East Harbour Railway in?", "Where is the closest park?", "How far is it?", with the straight-line distance and compass direction: "East Harbour Railway is 900 meters to the southeast, about half a mile.";
- *with a GPS (Level 3, or a USB GPS):* **how far have we gone**: "How far have we gone on this walk?";
- **going to sleep**: "Go to sleep" or "Take a nap". He checks first ("Shall I go to sleep now?") and only a clear "yes" counts.

The questions about home (humidity, air pressure, pollen, UV, air quality, sunrise and sunset, and weather warnings) are tested typed in the Den but not yet asked out loud. You can also **type** these questions in the Den, from Level 1 (all except voice profiles and going to sleep, which need him to hear you). The answer appears under the box, and he also says it out loud if he has a voice: the Dot, or the phone.

**"Hey dragon."** Tick the wake word in the Den and choose the hours. A tiny speech recognizer on the Dot listens only for "hey dragon"; when it hears it, the ring changes to cyan and your question is recorded. **Wake word: how strict** in Developer Tools trades false alarms against missed wake word calls, and the Den shows how sure he was each time to help you choose.

### Choosing a different voice (untested)

Harald speaks with a [Piper](https://github.com/rhasspy/piper) voice. You can hear them all on the [Piper voice samples](https://rhasspy.github.io/piper-samples/) page. Each voice name looks like `en_GB-alan-medium`: language, name, quality. "medium" is the best balance on this hardware; "high" voices are slower to speak.

1. On the Pi (pause your VPN first), download the voice you want (this example uses `en_GB-alan-medium`):
   ```
   sudo bash /opt/bt-dragon/install-voice.sh en_GB-alan-medium
   ```
2. In `bt-dragon.toml`, under `[dot]`, set `voice = "en_GB-alan-medium"`.
3. Every voice in `/opt/bt-dragon/voices` is copied to the Dot, each about 60 MB, and the Dot doesn't have much room. So remove any voice you no longer want. For example, to remove his default voice:
   ```
   sudo rm /opt/bt-dragon/voices/en_GB-northern_english_male-medium.onnx*
   ```
4. If you set up listening on the Dot, rebuild and copy his Debian so the Dot gets the new voice too. This is much quicker than the first time, because only the changed parts are redone:
   ```
   sudo bash /opt/bt-dragon/bt_dragon/dot_debian/build.sh
   bash /opt/bt-dragon/bt_dragon/dot_debian/push.sh
   ```
5. Restart him from the Den (*Care and Accessibility → Restart*).

If you use his voice through your phone with SherpaTTS, you can choose the same Piper voice in SherpaTTS too.

### What you need

1. **A rooted Echo Dot (2nd gen)** that accepts `adb` over Wi-Fi on port 5555.
2. **The Dot on Harald's network.** With the Dot plugged into a computer by USB, use the helper in [`tools/echo-dot`](tools/echo-dot): put the network's name and password in `wifi.txt`, then run `dot-wifi.bat` (Windows) or `dot-wifi.command` (macOS/Linux). Delete `wifi.txt` afterwards, since it holds your password.
3. **His voice and ears on the Pi.** The installer sets these up; after updating from an older version, run `sudo bash /opt/bt-dragon/install-voice.sh` (pause your VPN first). It installs `adb`, Piper with a northern English male voice, and the [Vosk](https://alphacephei.com/vosk/) speech recognizer with its small English model.
4. **Recommended: listening on the Dot itself.** This puts a small 32-bit Debian (about 330 MB) in a folder on the Dot, so the Dot records, understands and speaks by itself, about twice as fast, and the sound of your voice never leaves the Dot. Once only, on the Pi:
   ```
   sudo bash /opt/bt-dragon/bt_dragon/dot_debian/build.sh     # builds it (15-30 minutes)
   bash /opt/bt-dragon/bt_dragon/dot_debian/push.sh           # copies it to the Dot and times it
   ```
   It's also what the wake word needs to run well.

Harald finds the Dot on his network by himself within a minute, and from then on uses only that Dot (by its serial number) until you press **Forget this Dot** in the Den.

### After the Dot restarts

An Echo that was never set up in the Alexa app comes back from every restart (a power cut, unplugging it) in **setup mode**: a spinning orange ring, its saved networks switched off, and an **open** network of its own (named like `Amazon-XY7`). Anyone nearby can join that network and reach `adb`, which has no password.

Harald is designed to be able to fix this himself. Look up your Dot's setup network name in your phone's Wi-Fi list while the ring is orange, and enter it in the Den under *Voice and light ring → Setup-mode rescue*. From then on, when the Dot has been missing for a minute and he can see its setup network, he hops onto it for a moment, checks the device there has your Dot's serial number (otherwise he leaves it alone), switches your saved network back on, and hops home. The Den can't reach him for up to a minute while he does this. By hand: plug the Dot into a computer by USB and run `dot-reconnect.bat` (or `dot-reconnect.command`) from `tools/echo-dot`.

### What he does to the Dot

Every time he connects, he pauses Alexa's services and Amazon's light program, and copies his small player, his light ring animations and (if you built it) his listening program to `/data/local/tmp` on the Dot. Nothing is installed permanently: **unplugging or restarting the Dot puts Amazon's software back exactly as it was**, and he sets it up again when he next finds it. **Forget this Dot** starts Amazon's services again straight away. The services he pauses are listed under `[dot]` in the settings file.

> ⚠️ **A rooted Dot has an open door.** `adb` has no password: anyone on the same network gets a full root shell on it, and through its microphones could listen in. Keep the Dot on the same private network as Harald, and only use one you own.

### How the Dot side works

- **The ring** is 12 RGB lights on an IS31FL3236 LED chip. Linux exposes the chip as a text file: writing 72 hex digits (`RRGGBB` for each light) to it shows that picture straight away. The player is a shell script that plays animation files (one frame per line, about 14 frames a second).
- **Speech:** Piper turns his words into sound (on the Dot, or on the Pi without the Dot's Debian), converted to the 48 kHz stereo the Dot's speaker takes, and played by the Dot's own `tinyplay` on the speaker chip (a TLV320AIC3204). Amazon's `mixer` service holds that output open, so it's paused while Harald uses the Dot. The amplifier only switches on while sound is actually playing, so there's no hiss or click between remarks.
- **Recording:** a tiny program on the Dot (`micgrab`, its source `micgrab.c` is in `pi/bt_dragon/dot_files`) mixes the Dot's 7 microphones into one channel and stops when you stop talking. The recording is deleted as soon as it's been understood.
- **Understanding:** Vosk turns speech into text offline, limited to the few hundred words he knows (plus the items on your shopping list and the names of places he knows), which makes it fast and accurate on small hardware. For shopping items and place names, the same recording is listened to a second time with every word Vosk knows.
- **The wake word** has three layers, each stricter as the knob goes up: decoy words for the recognizer to choose instead of "hey dragon" (a cough or the telly is more likely to match "they drag on" than the real thing), a second, careful listen of the last 2.5 seconds with a confidence score for each word, and, at the strictest, a pause before "hey".

---

## Privacy: what stays where

BT Dragon has no accounts, no cloud and no analytics. **Nothing about you is uploaded or shared with anyone**, with one exception you opt into: wardriving uploads to *your own* WiGLE account.

### What stays on the Pi

Everything he knows lives on the Pi's memory card, in `/var/lib/bt-dragon/` and the settings file on **bootfs**:

- his meters, diary, life list of gadget types, Wi-Fi networks he's seen, and your pals' Bluetooth addresses;
- *Level 3:* the lands he's claimed (a rough map of where you've taken him, which **Forget my map** erases), landmarks and green spaces seen, your walks, and wardriving sightings (networks with locations);
- the calendar, the shopping list and Harald's Lair (the town or postcode area you typed, and its position rounded to about 10 km);
- the Butterfly Garden: what's growing, what's been raised, habitats and your **I've Seen It!** sightings (the Collection page is served by the Pi and loads nothing from the internet, not even fonts);
- *Level 4:* voice prints (128 numbers each, never recordings);
- the settings file, with your Wi-Fi details (passwords scrambled into keys on first start) and WiGLE token.

### What's on the Echo Dot (Level 4)

No personal data. The Dot holds Harald's programs, his light ring animations, the speech models, a key shared only with your Pi, and, like any device that joins a network, your network's Wi-Fi password in its own network settings. Recordings of your questions are deleted as soon as they're understood, and when listening happens on the Dot the sound never leaves it: only the words go to the Pi, over your network.

### Exactly what goes over the internet

| When | To | What's sent |
|---|---|---|
| Installing and updating | Debian and Raspberry Pi package servers, the Python package index, GitHub, Hugging Face, alphacephei.com | Ordinary software downloads, nothing about you |
| *Level 3:* the first time he enters a new 1 km square | Wikipedia and Wikidata (landmarks), OpenStreetMap's Overpass service (green spaces) | The square's corners (roughly which square kilometer you're in). Each square is asked about once, and again after half a year to look for any updates |
| *Level 3:* when the Den's map is open | OpenStreetMap's map tiles and the unpkg.com code library, loaded by your phone's browser, not by Harald | Which area you're looking at, as with any web map |
| *Level 2 and up:* only if you switch on **Find him by Wi-Fi**, and only while there's no GPS | beaconDB | The Wi-Fi networks he can hear (their hardware addresses and signal strengths), which shows where he is to within tens of meters. Its server logs keep your internet address and the time for 28 days |
| *Level 3:* wardriving, if you've added your WiGLE token | WiGLE, your own account | The networks he heard, with where and when |
| When you ask about the weather (any level), and every hour with the Lair's **Local announcements** on | Open-Meteo | A position rounded to about 10 km, or the city you named. Setting **Harald's Lair** looks up the place you typed once, with its country; a postcode is cut to its area first (`SW1A` of `SW1A 1AA`, the first three characters of a Canadian code, the five-digit ZIP of a ZIP+4), so a full postcode never leaves the Pi |
| With the Lair's **Local announcements** on, every 15 minutes (UK) | The Met Office | Nothing about you: he downloads the public warnings feed for the Lair's region, the same file anyone can open |
| Setting the Lair (US), once; then every 15 minutes with **Local announcements** on | The National Weather Service (api.weather.gov) | Once: the town's (or ZIP area's) own middle, to find its forecast zone and county. After that, only those two names (like `TXZ192` and `TXC453`) |
| Before each WiGLE upload | api.wigle.net | A connection check, nothing else |

The Pi also sets its clock from the internet, as every Raspberry Pi does. Nothing else leaves your network. Between your own devices, on your network: your phone sends its sensor readings to Harald (Level 3), the Pi and the Dot exchange his words and the text of your questions (Level 4), and the phone voice receives the words he says.

### The Lair and your postcode

Setting **Harald's Lair** sends the place you typed, and its country, to Open-Meteo's place finder once. A full postcode can narrow things down to a street or two, so before it's sent, a postcode is cut down to its area:

| Country | You type | What's looked up |
|---|---|---|
| United Kingdom | `SW1A 1AA` | `SW1A` (the postcode district) |
| Canada | `K1A 0B1` | `K1A` (the forward sortation area) |
| United States | `20500-0003` | `20500` (the five-digit ZIP, which already covers a whole area) |
| Netherlands | `1012 AB` | `1012` |
| Ireland | `D02 X285` | `D02` (the Eircode routing key) |

**Warning areas.** US weather warnings are issued per forecast zone and county, and a position rounded to 10 km could land in the neighboring county near a boundary. So when you set the Lair, the town's (or ZIP area's) own middle, as the place finder returned it, is sent to the National Weather Service once to find the zone and county, and then forgotten; only the zone and county names are kept and used. In the UK, the Met Office's region is worked out on the Pi from the county name, and the public feed for that region is simply downloaded.

Other countries' postcodes are looked up as typed, so for those, typing the town is the more private choice. Whatever comes back, he keeps only its name and its position rounded to one decimal place of latitude and longitude, about 10 km. That rounded position is all that's ever sent for the weather, pollen and air quality at the Lair. What you typed stays on the Pi (so the Den can show it back to you), and **Forget the Lair** erases it.

#### Pollen outside Europe

The free pollen forecast Harald uses (Open-Meteo, from the EU's Copernicus atmosphere service) covers Europe only. The US services that offer pollen counts (Google's Pollen API, Ambee, Tomorrow.io, The Weather Company) all need an account and an API key, and most become paid beyond a small free allowance, so they aren't built in. Outside Europe he simply says he can't get the pollen count.

### What's visible on your network

The Den and his control link have **no password**. Anyone on the same network with his address can see everything above, including your pals, your diary, the map of where you've been, your walks, your calendar and shopping list, and can **download a backup containing your Wi-Fi passwords and WiGLE token**, or change his settings.

This is why he belongs on **a private network that you control**: your own home Wi-Fi or your own phone's hotspot, never public or shared Wi-Fi. A rooted Echo Dot is even more open (anyone on the network gets a root shell on it), so the same goes for it.

**Out in the world**, he only listens. His friend beacon broadcasts a random ID, his name, level and mood, so other dragons can recognize him (and so could anyone listening). Set `beacon = false` under `[friends]` to stop broadcasting; he still meets dragons that do broadcast.

---

## Responsible use

- **It's passive by design.** BT Dragon only listens to broadcasts that every phone already receives. It doesn't pair with other people's devices, capture handshakes, deauthenticate anyone or crack anything. The one thing it ever sends to a gadget is a single "are you there?" ping to one of *your own* pals, when you use **Find** on it.
- **Other people's devices stay anonymous.** Phones, watches and earbuds change their address every few minutes for privacy. Harald counts them as food and as a type of gadget and never lists or follows one. Fixed-address gadgets he's already eaten today are remembered only temporarily as scrambled codes so they don't count more than once a day, with a key that's thrown away at midnight. Only your own pals are remembered by address. DO NOT modify Harald to follow other people.
- **Stay on public ground.** "Land" map tiles are designed to be claimed via a very generous radius from your GPS position, reachable from public roads and paths. Never enter private property, gated communities, farms or closed sites to claim land. 
- **WiGLE uploads go to your own account, under [WiGLE's terms](https://wigle.net/terms).** You're responsible for what you upload.
- **Know your local rules.** Collecting Wi-Fi and Bluetooth broadcasts is legal in most places, but rules differ by country and state. Check yours, especially before uploading location data.
- **The tracker alert is a helpful extra, NOT a safety system.** It can miss trackers and can be wrong. If you're worried about being tracked, use your phone's built-in unknown-tracker alerts (many recent models have this feature) and contact local support services.

---

## How it works

```
 Bluetooth adverts ─┐                       ┌─► e-ink screen, if there is one (and the Den's copy)
 Wi-Fi beacons ─────┼─► dragon (asyncio) ───┼─► dragon.db (SQLite: gadget types, treats, pals, diary)
 Phone sensors ─────┘        │              ├─► WiGLE upload (with GPS and your token)
                             │              ├─► Echo Dot: voice, ears, light ring
                             │              └─► the Den, a web page on port 8080
                             └─► control link :5151  (for your own scripts and tools)
```

- **Bluetooth:** BlueZ through the `bleak` library. Each advert's manufacturer data and service IDs are matched against known patterns (publicly available) to name the type of gadget, for example Apple's "Continuity" messages, which say whether they come from AirPods, a phone or a Find My tag. Gadgets that only identify their maker are named from the Bluetooth SIG's public list of company identifiers (`pi/bt_dragon/companies.tsv`, about 4,000 companies). Codes that aren't real companies (unbranded bulbs, LED strips and toys put their own bytes there) all count as one species, "Unbranded gadget". Names gadgets broadcast become species too ("JBL Flip #": numbers are hidden as #, so no serial numbers are kept), but only if the name says something once the numbers are gone.
- **Wi-Fi:** `iw dev wlan0 scan` every 20 seconds, while staying connected to his network.
- **Storage:** everything lives in `/var/lib/bt-dragon/dragon.db`. WiGLE CSVs are also saved in `/var/lib/bt-dragon/wigle/` (the 20 newest), and diary spreadsheet files in `/var/lib/bt-dragon/diary/` (90 days by default, `keep_days` under `[diary]`).
- **Settings:** `bt-dragon.toml` on the boot partition. Each setting is explained in the file. If you change a network's name, type its password in again too: the stored key is tied to the network name.
- **Logs:** `sudo journalctl -u bt-dragon -f` over SSH.
- **The Butterfly Garden:** the Collection is Bookworm's own page (`pi/bt_dragon/garden/bookworm.html`, kept exactly as Bookworm ships it). When the Pi serves it, it adds a few small pieces: a script that writes Harald's garden into the browser's storage just before Bookworm reads it (Bookworm keeps its save there) and sends **I've Seen It!** ticks back to the Pi, a few hooks inside Bookworm's script (its species list and field notes), and the Den's colors with only the Collection and Habitats showing. The Den draws its larvae the same way: it loads a second, art-only copy of Bookworm's page unseen (`/garden/art`, which never touches the save) and asks Bookworm's own drawing code for each picture. That copy is the same until an update, so the browser keeps it rather than fetching 1.4 MB every time, and both pages are sent compressed. Bookworm's Google Fonts link is taken out. The garden's own rules run on the Pi from `garden/species.json`: each species' rarity, months, pupation point, forms and habitats for all four countries, read out of Bookworm's page. After replacing `bookworm.html` with a newer Bookworm, rebuild it with `python3 tools/garden/extract.py` (it needs Playwright). The same script writes `pi/bt_dragon/lang.json`, Bookworm's spelling and word lists, which `lang.py` uses for his screen and `lang.js` for the Den's pages.
- **Language:** the Pi's own country is read from the Pi itself (the Wi-Fi country on the kernel command line that Raspberry Pi Imager sets, else `wpa_supplicant.conf`, else the system's locale); nothing is looked up online. In the Den, every piece of text is converted as it appears, except inside anything marked `data-nolang` (network, gadget and place names, your list items, and the examples in the Lair section). As in Bookworm, insect names are never converted anywhere, on his screen or in the Den: every species' name from all four countries is set aside before converting and put back afterwards, so a Grey Hairstreak stays grey in American English and a Gray Hairstreak stays gray in British.

### Try it without the Pi (untested)

On any Linux or macOS machine with Python 3.11+ and Pillow:

```
cd pi
python3 -m bt_dragon --simulate --data /tmp/bt-dragon
```

This walks Harald through an imaginary town center with fake Bluetooth, Wi-Fi and GPS. Open http://localhost:8080 to see the Den.

### Control link protocol

Your dragon broadcasts `BTDRAGON 1 port=5151 web=8080 name=Harald` on UDP port 5150 every 5 seconds, so clients can find him without knowing his IP address. The name comes last because it may contain spaces: everything after `name=` up to the end of the line is the name.

On TCP port 5151 you send one command per line. Replies are either one `OK …` / `ERR …` line, or several lines ending in `END`. Fields inside a line are separated by `|`. Try it with `nc bt-dragon.local 5151` and type `STATUS`.

| Command | Reply |
|---|---|
| `HELLO` | `OK BTDRAGON <version> name=<name>` |
| `STATUS` | `key=value` lines (mood, hunger, level, counts, gps, message…) then `END` |
| `LOG [n]` | `ts\|kind\|text` lines, then `END` |
| `NEARBY` | Fixed-address devices: `mac\|rssi\|is_pal\|type\|name`, then `END` |
| `PALS` | `mac\|rssi\|seconds_since_seen\|name`, then `END` |
| `ADDPAL <mac> <name>` / `DELPAL <mac>` | `OK` |
| `TRACK <mac>` / `STOP` | Streams `RSSI <mac> <dBm>` lines (pals only) |
| `NETWORK` / `RECONNECT` | His saved networks (`rank\|ssid\|connected` lines, then `END`) / join the best one in range |
| `FIND <mac>` | Start a fresh Find: listen first, ask directly only if needed (pals only) |
| `RSSI <mac>` | One reading (pals only) |
| `SEARCH` | Look for classic-Bluetooth gadgets in pairing mode for 30 seconds |
| `ALERTS` / `DISMISS <id>` | `id\|since\|label` lines, then `END` |
| `SPECIES` / `TREATS [n]` | Life list of gadget types / recent networks, then `END` |
| `STARS` | Star chart: `key\|constellation\|number\|first_seen\|days_seen\|in_view_now` lines, then `END` |
| `LANDMARKS` | Famous places: `qid\|title\|languages\|first_seen (0 = not yet)\|visits` lines, then `END` |
| `LAIR` | Harald's Lair: `place=`, `country=`, `found=`, `announce=`, `complete=`, `now=`, `warn_source=`, `warn_area=`, `warn_region=`, `warn_active=` lines, then `END` |
| `LAIRSET place\|country` | Look up and set the Lair: `OK Found …` or `ERR` with why not |
| `LAIRREGION code` | The UK warning region, if the guess was wrong (`nw`, `se`, `st`… as in the Met Office's feeds) |
| `LAIRANNOUNCE on` / `off` | Local announcements on or off (needs the Lair set) |
| `LAIRFORGET` | Forget the Lair |
| `GREENS` | Green spaces: `id\|name\|kind\|first_seen (0 = not yet)\|visits\|walks\|runs\|rides` lines, then `END` |
| `WIFIPOS` | Finding him by Wi-Fi: `on=`, `status=`, `lookups=`, `fix_acc=` lines, then `END` |
| `WIFIPOSSET on` / `off` | Switch finding him by Wi-Fi on or off |
| `FORGETMAP` | Forget every claimed land and realm, and which landmarks and green spaces he's seen |
| `FRIENDS` / `UNFRIEND <id>` | `id\|name\|level\|here_now\|meetings\|last_met` lines, then `END` |
| `TUNE` / `TUNE <key> <value\|default>` / `TUNERESET food\|joy\|xp\|detect\|all` | Developer Tools: list or change the numbers live |
| `METER food\|joy <0-100>` / `METER pack <n>` / `METER xp <n>` | Set a meter or his XP, for testing |
| `DOT` / `DOTSET <setting> <value>` | The Echo Dot's state and settings (`key=value` lines, then `END`) / change one |
| `DOTSAY <text>` / `DOTRING <animation>` | Say something / play a ring animation now (e.g. `ev_storm`, `ev_test`) |
| `ASK <question>` | Answer a question in writing (and say it, if he has a voice) |
| `TIMERS` / `TIMERCANCEL <name\|all>` / `ALARMSTOP` | Kitchen timers / cancel / stop a ringing timer |
| `DOTRESCUE` | Hop onto the Dot's setup network now and switch its Wi-Fi back on |
| `DOTFIND` / `DOTFORGET` | Look for the Dot now / stop using it and hand it back to Alexa |
| `UPLOAD` | Upload to WiGLE now |
| `NAME <name>` | Rename him (up to 10 characters) |
| `NAP` / `WAKE` | Nap / wake from a nap |
| `SLEEP` / `REBOOT` | Clean shutdown or restart |

He also pushes `EVT kind|text` lines whenever something happens (new gadget type, treat, pal, friend, tracker, upload). A tool connected to the control link also shows the ⚓ anchor on his screen.

The friend beacon is BLE manufacturer data under company ID `0xFFFF`, which the Bluetooth SIG reserves for testing and unregistered projects. Its layout is `'H' 'D'`, version, 4-byte dragon ID, level, mood index, then up to 10 bytes of name. This format may change before a full release.

---

## License

Copyright (C) 2026 Tara Carter (sauvryn)

BT Dragon is free software: you can redistribute it and/or modify it under the terms of the **GNU General Public License** as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version. See [LICENSE](LICENSE) for the full text.

In plain words: you're welcome to use it, study it, change it, fork it and share it. If you pass it on, changed or not, you must include the source code and pass it on under this same license, so it stays free for everyone after you. It comes with no warranty.

The Waveshare e-ink driver isn't included in this repository; the installer downloads it from [Waveshare's own repository](https://github.com/waveshareteam/e-Paper) under its own license.
