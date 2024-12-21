import json as JSON
import pathlib as PTH

import wowsunpack as WUP
import polib as PO


class NamelessRecipientError(ValueError):
    pass


class PortraitlessRecipientError(ValueError):
    pass


class WowsIo:

    def __init__(self, wows_dir, wows_lang):
        self.language = wows_lang
        self.unpacker = WUP.WoWsUnpack(wows_dir)
        self.mo = PO.mofile(PTH.Path(wows_dir, "bin", self.unpacker._findLatestBinFolder(), "res", "texts",
                                     wows_lang, "LC_MESSAGES", "global.mo"))
        self.unpacker.unpackGameParams()
        self.unpacker.decodeGameParams()
        self.unpacker.unpack("gui/crew_commander/base/*/*.png")

    def fetch_recipients(self):
        recipients = []
        with open("GameParams-0.json") as game_params_json:
            game_params = JSON.load(game_params_json)
        for value in game_params.values():
            if value["typeinfo"]["type"] == "Crew" and value["CrewPersonality"]["isPerson"]:
                try:
                    recipient = RecipientCommander(value["CrewPersonality"]["personName"],
                                                   value["CrewPersonality"]["ships"]["nation"],
                                                   value["CrewPersonality"]["subnation"],
                                                   value["CrewPersonality"]["peculiarity"],
                                                   value["CrewPersonality"]["hasOverlay"],
                                                   self.mo)
                except NamelessRecipientError:
                    print(f"Skipping recipient commander without name in language {self.language}:",
                          f"{value["CrewPersonality"]["personName"]}.")
                except PortraitlessRecipientError:
                    print(f"Skipping recipient commander without portrait: {value["CrewPersonality"]["personName"]}.")
                else:
                    recipients.append(recipient)
        return recipients

class RecipientCommander:

    def __init__(self, code_name, nations, subnation, peculiarity, has_overlay, mo):
        if not subnation and nations:
            subnation = nations[0]
        self.portrait_path = PTH.Path("gui", "crew_commander", "base", subnation, f"{code_name}.png")
        if not self.portrait_path.is_file():
            raise PortraitlessRecipientError()
        self.translation_id = f"IDS_{code_name.upper()}"
        for entry in mo:
            if entry.msgid == self.translation_id:
                self.name = entry.msgstr
                break
        else:
            raise NamelessRecipientError()
        self.peculiarity = peculiarity
        self.has_overlay = has_overlay

    def __str__(self):
        return f"(Recipient) {self.name}"


def main():
    with open("../session.json") as session_json:
        session = JSON.load(session_json)
    io = WowsIo(session["wows_dir"], session["wows_lang"])
    for recipient in io.fetch_recipients():
        print(str(recipient))


if __name__ == "__main__":
    main()
